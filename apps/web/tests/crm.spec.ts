import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import { EMPRESA, prepararPainel } from "./api-falsa";

async function semViolacoes(page: Page) {
  const resultado = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(resultado.violations, JSON.stringify(resultado.violations, null, 2)).toEqual([]);
}

function coluna(page: Page, nome: string | RegExp) {
  return page.getByRole("region", { name: nome });
}

/** Arrasta disparando os eventos de arrastar e soltar com um DataTransfer real (o quadro rola na horizontal e o
 * mouse do teste não alcança colunas fora da área visível da rolagem). */
async function arrastar(page: Page, cartao: string, colunaDestino: string) {
  const dados = await page.evaluateHandle(() => new DataTransfer());
  const origem = page.getByRole("article", { name: cartao });
  const destino = coluna(page, colunaDestino);
  await origem.dispatchEvent("dragstart", { dataTransfer: dados });
  await destino.dispatchEvent("dragenter", { dataTransfer: dados });
  await destino.dispatchEvent("dragover", { dataTransfer: dados });
  await destino.dispatchEvent("drop", { dataTransfer: dados });
  await origem.dispatchEvent("dragend", { dataTransfer: dados });
}

test("quadro mostra colunas do funil e cartões com score em número e texto", async ({ page }) => {
  await prepararPainel(page, { papel: "vendedor" });
  await page.goto("/crm");
  await expect(page.getByRole("heading", { level: 2, name: "Qualificando (1)" })).toBeVisible();
  const frio = page.getByRole("article", { name: "Hospital Frio" });
  // Os ":" depois de cada rótulo vêm do CSS; o leitor de tela lê os pares termo/definição
  await expect(frio).toContainText("Score30 · Frio");
  await expect(frio).toContainText("Acessibilidade80/100");
  await expect(frio).toContainText("Próximo passoDecidir: seguir ou arquivar");
  await expect(frio).toContainText("ResponsávelMarcos");
  await expect(frio.getByRole("link", { name: "Hospital Frio" })).toHaveAttribute("href", "/empresas/c-frio");
  await expect(page.getByRole("article", { name: "Site Fora" })).toContainText(
    "Precisa de atenção: site não pôde ser lido",
  );
  await expect(coluna(page, "Em sequência (0)")).toContainText("Usada na Fase 3");
  await semViolacoes(page);
});

test("move só com teclado pelo diálogo, com motivo obrigatório, e o foco volta ao cartão", async ({ page }) => {
  const { mudancas } = await prepararPainel(page, { papel: "vendedor" });
  await page.goto("/crm");
  await page.getByRole("button", { name: "Mover… Hospital Frio" }).focus();
  await page.keyboard.press("Enter");
  const dialogo = page.getByRole("dialog", { name: "Mover Hospital Frio" });
  await expect(dialogo).toBeVisible();
  await semViolacoes(page);

  await dialogo.getByRole("radio", { name: "Arquivado (pede motivo)" }).check();
  await dialogo.getByRole("button", { name: "Mover" }).click();
  await expect(dialogo.getByRole("alert")).toHaveText("Explique o motivo para mover para Arquivado.");
  await expect(dialogo.getByLabel("Motivo (obrigatório)")).toBeFocused();
  await page.keyboard.type("Fora do perfil");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");

  await expect(dialogo).toHaveCount(0);
  await expect(page.getByRole("main").getByRole("status")).toHaveText("Hospital Frio movido para Arquivado.");
  expect(mudancas).toEqual([{ id: "c-frio", origem: "QUALIFICANDO", destino: "ARQUIVADO", motivo: "Fora do perfil" }]);
  await expect(page.getByRole("heading", { level: 2, name: "Arquivado (1)" })).toBeVisible();
});

test("Esc fecha o diálogo sem mover e devolve o foco", async ({ page }) => {
  const { mudancas } = await prepararPainel(page, { papel: "vendedor" });
  await page.goto("/crm");
  const botao = page.getByRole("button", { name: "Mover… Hospital Quente" });
  await botao.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(botao).toBeFocused();
  expect(mudancas).toEqual([]);
});

test("arrastar para uma coluna permitida move sem diálogo", async ({ page }) => {
  const { mudancas } = await prepararPainel(page, { papel: "vendedor" });
  await page.goto("/crm");
  await arrastar(page, "Hospital Quente", "Reunião agendada (0)");
  await expect(page.getByRole("main").getByRole("status")).toHaveText(
    "Hospital Quente movido para Reunião agendada.",
  );
  expect(mudancas).toEqual([{ id: "c-quente", origem: "PREPARANDO_ABORDAGEM", destino: "REUNIAO_AGENDADA", motivo: null }]);
});

test("arrastar para Arquivado pede o motivo no diálogo", async ({ page }) => {
  const { mudancas } = await prepararPainel(page, { papel: "vendedor" });
  await page.goto("/crm");
  await arrastar(page, "Hospital Quente", "Arquivado (0)");
  const dialogo = page.getByRole("dialog", { name: "Mover Hospital Quente" });
  await expect(dialogo.getByRole("radio", { name: "Arquivado (pede motivo)" })).toBeChecked();
  expect(mudancas).toEqual([]);
});

test("arrastar para coluna não permitida avisa e não chama a API", async ({ page }) => {
  const { mudancas } = await prepararPainel(page, { papel: "vendedor" });
  await page.goto("/crm");
  await arrastar(page, "Hospital Frio", "Ganho (0)");
  await expect(page.getByRole("main").getByRole("alert")).toHaveText(
    "Não é possível mover Hospital Frio para essa coluna à mão.",
  );
  expect(mudancas).toEqual([]);
});

test("conflito de estado avisa e recarrega o quadro", async ({ page }) => {
  const { consultasQuadro } = await prepararPainel(page, {
    papel: "vendedor",
    respostaMudancaEstado: {
      status: 409,
      corpo: { detail: "Esta empresa mudou de estado enquanto você olhava: agora está em Mapeando decisores." },
    },
  });
  await page.goto("/crm");
  await page.getByRole("button", { name: "Mover… Hospital Frio" }).click();
  const dialogo = page.getByRole("dialog");
  await dialogo.getByRole("radio", { name: "Mapeando decisores" }).check();
  await dialogo.getByRole("button", { name: "Mover" }).click();
  await expect(
    page.getByRole("main").getByRole("alert").filter({ hasText: "mudou de estado enquanto você olhava" }),
  ).toBeVisible();
  expect(consultasQuadro.length).toBeGreaterThanOrEqual(2);
});

test("filtros vão para a consulta do quadro", async ({ page }) => {
  const { consultasQuadro } = await prepararPainel(page);
  await page.goto("/crm");
  await page.getByLabel("Buscar").fill("quente");
  await page.getByLabel("Faixa do score").selectOption("quente");
  await page.getByLabel("Só as minhas").check();
  await page.getByRole("button", { name: "Filtrar" }).click();
  await expect(page.getByText("1 empresa(s) no quadro.")).toBeVisible();
  expect(consultasQuadro.at(-1)).toBe("?busca=quente&faixa=quente&minhas=true");
});

test("leitura vê o quadro sem botões de mover", async ({ page }) => {
  await prepararPainel(page, { papel: "leitura" });
  await page.goto("/crm");
  await expect(page.getByRole("article", { name: "Hospital Frio" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Mover…/ })).toHaveCount(0);
});

test("em tela de celular as colunas empilham sem rolagem lateral da página", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await prepararPainel(page, { papel: "vendedor" });
  await page.goto("/crm");
  await expect(page.getByRole("article", { name: "Hospital Frio" })).toBeVisible();
  const largura = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(largura).toBeLessThanOrEqual(320);
  await semViolacoes(page);
});

test("ficha muda o estado pelo mesmo diálogo", async ({ page }) => {
  const { mudancas } = await prepararPainel(page, { papel: "vendedor" });
  await page.goto(`/empresas/${EMPRESA.id}`);
  await page.getByRole("button", { name: "Mudar estado…" }).click();
  const dialogo = page.getByRole("dialog");
  await dialogo.getByRole("radio", { name: "Mapeando decisores" }).check();
  await dialogo.getByRole("button", { name: "Mover" }).click();
  await expect(page.locator(".acoes-ficha [role=status]")).toHaveText("Estado alterado para Mapeando decisores.");
  expect(mudancas).toEqual([
    { id: EMPRESA.id, origem: "QUALIFICANDO", destino: "MAPEANDO_DECISORES", motivo: null },
  ]);
});

test("funil da tela inicial mostra os números reais", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  const funil = page.getByRole("list", { name: "Indicadores do funil" });
  await expect(funil.getByRole("listitem").filter({ hasText: "Com decisores" })).toContainText("14");
  await expect(page.getByRole("link", { name: "Abrir o CRM" })).toHaveAttribute("href", "/crm");
});
