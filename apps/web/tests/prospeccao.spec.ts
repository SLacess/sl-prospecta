import { expect, test } from "@playwright/test";

import {
  ANDAMENTO_CONFIRMACAO,
  ANDAMENTO_PADRAO,
  DOSSIE,
  EMPRESA,
  EVENTOS_FINAIS,
  prepararPainel,
} from "./api-falsa";

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

  const status = page.getByRole("region", { name: "Prospecção individual" }).getByRole("status");
  await expect(status).toHaveText("Empresa cadastrada. Processamento na fila.");
  expect(posts).toEqual([{ alvo: "hospitalexemplo.com.br" }]);

  // A consulta seguinte traz o dossiê pronto; só a novidade mais recente é anunciada
  await expect(status).toHaveText(EVENTOS_FINAIS[EVENTOS_FINAIS.length - 1].mensagem);
  await expect(page.locator(".linha-do-tempo li")).toHaveCount(EVENTOS_FINAIS.length);
  await expect(page.getByText("Sem novidades no momento.")).toBeVisible();

  // Resumo de 5 linhas e setor em texto
  await expect(page.getByRole("heading", { name: "Resumo da pesquisa" })).toBeVisible();
  await expect(page.locator(".resumo-dossie li")).toHaveText(DOSSIE.resumo);
  await expect(page.locator(".resumo")).toContainText("Saúde");

  // Estado em texto, não só cor; o foco volta ao campo, vazio para a próxima empresa
  await expect(page.locator(".resumo")).toContainText("Qualificando");
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
    andamento: [ANDAMENTO_PADRAO[1]],
  });
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("https://www.hospitalexemplo.com.br/contato");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await expect(page.getByRole("region", { name: "Prospecção individual" }).getByRole("status")).toContainText(
    "já está cadastrada",
  );
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

test("vendedor confirma o site oficial só com teclado e a pesquisa continua", async ({ page }) => {
  const { confirmacoes } = await prepararPainel(page, {
    andamento: ANDAMENTO_CONFIRMACAO,
    andamentoDepoisDaConfirmacao: [{ ...ANDAMENTO_PADRAO[1], nome: "Unimed", dominio: "unimed-b.com.br" }],
  });
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("Unimed");
  await page.keyboard.press("Enter");

  const grupo = page.getByRole("group", { name: "Qual é o site oficial de Unimed?" });
  await expect(grupo).toBeVisible();
  await expect(page.getByRole("radio", { name: /unimed-a\.com\.br/ })).toBeChecked();

  // Setas trocam a opção dentro do grupo, como em qualquer grupo de botões de opção
  await page.getByRole("radio", { name: /unimed-a\.com\.br/ }).focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("radio", { name: /unimed-b\.com\.br/ })).toBeChecked();
  await page.getByRole("button", { name: "Confirmar site" }).focus();
  await page.keyboard.press("Enter");

  await expect.poll(() => confirmacoes).toEqual([{ dominio: "unimed-b.com.br" }]);
  await expect(page.locator(".resumo-dossie li")).toHaveCount(5);
  await expect(grupo).toHaveCount(0);
  await expect(page.locator(".resumo")).toContainText("unimed-b.com.br");
});

test("outro site vazio mostra erro e o site digitado é enviado", async ({ page }) => {
  const { confirmacoes } = await prepararPainel(page, { andamento: ANDAMENTO_CONFIRMACAO });
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("Unimed");
  await page.getByRole("button", { name: "Prospectar" }).click();

  await page.getByRole("radio", { name: "Outro site" }).check();
  await page.getByRole("button", { name: "Confirmar site" }).click();
  await expect(page.locator("#confirmar-site-erro")).toHaveText("Digite o endereço do site oficial.");
  await expect(page.getByLabel("Endereço do site oficial")).toBeFocused();
  expect(confirmacoes).toEqual([]);

  await page.getByLabel("Endereço do site oficial").fill("unimedsorocaba.coop.br");
  await page.getByRole("button", { name: "Confirmar site" }).click();
  await expect.poll(() => confirmacoes).toEqual([{ dominio: "unimedsorocaba.coop.br" }]);
});

test("site de outra empresa aparece como erro na confirmação", async ({ page }) => {
  await prepararPainel(page, {
    andamento: ANDAMENTO_CONFIRMACAO,
    respostaConfirmacao: { status: 409, corpo: { detail: "O site unimed-a.com.br já pertence à empresa Unimed A." } },
  });
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("Unimed");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await page.getByRole("button", { name: "Confirmar site" }).click();
  await expect(page.locator("#confirmar-site-erro")).toHaveText("O site unimed-a.com.br já pertence à empresa Unimed A.");
});

test("custo de IA do dia aparece abaixo do formulário", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await expect(page.locator(".custo-dia")).toHaveText("Custo de IA hoje: R$ 4,10 de R$ 30,00.");
});

test("cartão da auditoria técnica mostra gravidade em texto e as páginas testadas", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("hospitalexemplo.com.br");
  await page.getByRole("button", { name: "Prospectar" }).click();

  const cartao = page.getByRole("region", { name: "Auditoria de acessibilidade" });
  await expect(cartao).toBeVisible();
  await expect(cartao.locator(".totais-auditoria")).toContainText("Crítico2");
  await expect(cartao.locator(".totais-auditoria")).toContainText("Grave1");
  await expect(cartao).toContainText("Plugin de acessibilidade já instalado: UserWay.");
  await expect(cartao).toContainText("encontram só parte");

  const tabela = cartao.getByRole("table", { name: "Páginas testadas" });
  await expect(tabela.getByRole("row")).toHaveCount(4);
  await expect(tabela.getByRole("row", { name: /^\/ / })).toContainText("sem link “pular para o conteúdo”");
  await expect(tabela.getByRole("row", { name: /^\/ / })).toContainText("rolagem horizontal");
  await expect(tabela.getByRole("row", { name: /contato/ })).toContainText("armadilha de foco");
  await expect(tabela.getByRole("row", { name: /trabalhe-conosco/ })).toContainText("Não testada: o robots.txt");
});

test("análise mostra nota, achados para leigos e plugin separado do código", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("hospitalexemplo.com.br");
  await page.getByRole("button", { name: "Prospectar" }).click();

  const cartao = page.getByRole("region", { name: "Auditoria de acessibilidade" });
  await expect(cartao.locator(".nota")).toHaveText("58 de 100");
  const achados = cartao.locator(".achados > li");
  await expect(achados).toHaveCount(2);
  await expect(achados.first()).toContainText("Formulário de contato não diz");
  await expect(achados.first()).toContainText("Quem é afetado: pessoas cegas, pessoas com baixa visão");
  await expect(achados.first()).toContainText("Critério WCAG 1.3.1 / 4.1.2");

  // O trecho de código fica recolhido e abre pelo teclado
  await achados.first().getByText("Ver trecho do código").focus();
  await page.keyboard.press("Enter");
  await expect(achados.first().locator("code")).toHaveText('<input type="text" id="nome">');

  await expect(cartao.getByRole("heading", { name: "O que o plugin ajuda a resolver" })).toBeVisible();
  await expect(cartao).toContainText("contraste de cores");
  await expect(cartao.getByRole("heading", { name: "O que exige ajuste no código" })).toBeVisible();
  await expect(cartao).toContainText("campos de formulário sem rótulo");
  await expect(cartao).toContainText("Indícios nos prints (a confirmar)");
  await expect(cartao.locator(".observacao")).toContainText("encontram só parte das barreiras");
});
