import { expect, test } from "@playwright/test";

import { EMPRESA, EVENTOS_FINAIS, prepararPainel } from "./api-falsa";

test("prospecção só com teclado anuncia o andamento no status", async ({ page }) => {
  const { posts } = await prepararPainel(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Painel de Prospecção" })).toBeVisible();

  // Chega ao campo apenas com Tab
  for (let i = 0; i < 10; i++) {
    await page.keyboard.press("Tab");
    if (await page.evaluate(() => document.activeElement?.id === "alvo")) break;
  }
  await expect(page.locator("#alvo")).toBeFocused();

  await page.keyboard.type("hospitalexemplo.com.br");
  await page.keyboard.press("Enter");

  const status = page.getByRole("status");
  await expect(status).toHaveText("Empresa cadastrada. Processamento na fila.");
  expect(posts).toEqual([{ alvo: "hospitalexemplo.com.br" }]);

  // A consulta seguinte traz o fim do pipeline desta versão; só a novidade é anunciada
  await expect(status).toHaveText(EVENTOS_FINAIS[EVENTOS_FINAIS.length - 1].mensagem);
  await expect(page.locator(".linha-do-tempo li")).toHaveCount(4);
  await expect(page.getByText("Sem novidades no momento.")).toBeVisible();

  // Estado em texto, não só cor; o foco volta ao campo, vazio para a próxima empresa
  await expect(page.locator(".resumo")).toContainText("Novo");
  await expect(page.locator("#alvo")).toBeFocused();
  await expect(page.locator("#alvo")).toHaveValue("");
});

test("entrada duplicada avisa que a empresa já está cadastrada", async ({ page }) => {
  await prepararPainel(page, {
    respostaPost: {
      status: 200,
      corpo: {
        empresa: EMPRESA,
        duplicada: true,
        na_fila: true,
        fila_pausada: false,
        mensagem: "Esta empresa já está cadastrada. Processamento na fila.",
      },
    },
    linhasDoTempo: [EVENTOS_FINAIS],
  });
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("https://www.hospitalexemplo.com.br/contato");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await expect(page.getByRole("status")).toContainText("já está cadastrada");
  await expect(page.getByRole("heading", { name: `Andamento: ${EMPRESA.nome}` })).toBeVisible();
});

test("campo vazio mostra erro sem chamar a API", async ({ page }) => {
  const { posts } = await prepararPainel(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await expect(page.locator("#alvo-erro")).toHaveText("Digite o nome da empresa ou o endereço do site.");
  await expect(page.locator("#alvo")).toHaveAttribute("aria-invalid", "true");
  await expect(page.locator("#alvo")).toBeFocused();
  expect(posts).toEqual([]);
});

test("erro da API aparece no alerta com a mensagem do servidor", async ({ page }) => {
  await prepararPainel(page, {
    respostaPost: {
      status: 503,
      corpo: {
        detail:
          "A empresa foi registrada, mas a fila de processamento está indisponível. " +
          "Tente de novo em alguns minutos.",
      },
    },
  });
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("exemplo.com.br");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await expect(page.locator("#alvo-erro")).toContainText("fila de processamento está indisponível");
});

test("disjuntor atingido mostra aviso persistente com texto", async ({ page }) => {
  await prepararPainel(page, { disjuntorAtingido: true });
  await page.goto("/");
  const aviso = page.getByRole("region", { name: /Fila de IA pausada/ });
  await expect(aviso).toContainText("Teto diário de IA atingido");
});

test("sem login, o painel leva para a tela de entrada", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
});
