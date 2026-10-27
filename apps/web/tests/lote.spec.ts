import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import { LOTE_ID, LOTE_PROCESSANDO, prepararPainel } from "./api-falsa";

const URL_LOTE = `/lotes/${LOTE_ID}`;

async function semViolacoes(page: Page) {
  const resultado = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(resultado.violations, JSON.stringify(resultado.violations, null, 2)).toEqual([]);
}

test("envia a planilha só com teclado e abre a prévia", async ({ page }) => {
  const { envios } = await prepararPainel(page);
  await page.goto("/");
  const campo = page.getByLabel("Planilha de empresas (.xlsx ou .csv)");
  await campo.setInputFiles({ name: "hospitais.csv", mimeType: "text/csv", buffer: Buffer.from("Empresa;Site\nA;a.com.br\n") });
  await expect(page.getByRole("region", { name: "Prospecção em lote" }).getByRole("status")).toHaveText(
    "Arquivo escolhido: hospitais.csv.",
  );
  await page.getByRole("button", { name: "Enviar planilha" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`${URL_LOTE}$`));
  expect(envios[0]).toContain("multipart/form-data");
});

test("sem arquivo, o envio avisa e devolve o foco ao campo", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Enviar planilha" }).click();
  const regiao = page.getByRole("region", { name: "Prospecção em lote" });
  await expect(regiao.getByRole("alert")).toHaveText("Escolha uma planilha .xlsx ou .csv.");
  await expect(page.getByLabel("Planilha de empresas (.xlsx ou .csv)")).toBeFocused();
});

test("erro do servidor na planilha aparece no alerta", async ({ page }) => {
  await prepararPainel(page, {
    respostaEnvioLote: { status: 422, corpo: { detail: "A planilha tem 1200 linhas; o limite é 1000 por lote." } },
  });
  await page.goto("/");
  await page
    .getByLabel("Planilha de empresas (.xlsx ou .csv)")
    .setInputFiles({ name: "grande.csv", mimeType: "text/csv", buffer: Buffer.from("x") });
  await page.getByRole("button", { name: "Enviar planilha" }).click();
  await expect(page.getByRole("region", { name: "Prospecção em lote" }).getByRole("alert")).toHaveText(
    "A planilha tem 1200 linhas; o limite é 1000 por lote.",
  );
});

test("prévia mostra contagens, situação de cada linha em texto e estimativa", async ({ page }) => {
  await prepararPainel(page);
  await page.goto(URL_LOTE);
  const previa = page.getByRole("region", { name: "Prévia" });
  await expect(previa.locator(".totais-auditoria")).toContainText("Novas2");
  await expect(previa.locator(".totais-auditoria")).toContainText("Inválidas1");
  const tabela = previa.getByRole("table", { name: /Primeiras 4 linhas/ });
  await expect(tabela.getByRole("row", { name: /^4 / })).toContainText("Já cadastrada: já cadastrada como Já Existe");
  await expect(tabela.getByRole("row", { name: /^3 / })).toContainText("aviso: CNPJ com dígito verificador errado");
  await expect(previa).toContainText("cerca de R$ 2,00 de IA e até 8 crédito(s)");
  await expect(page.getByLabel("Empresa", { exact: true })).toHaveValue("0");
  await semViolacoes(page);
});

test("ajusta uma coluna e confirma o lote só com teclado", async ({ page }) => {
  const { acoesLote } = await prepararPainel(page, { papel: "vendedor" });
  await page.goto(URL_LOTE);
  await page.getByLabel("Cidade").selectOption({ label: "CNPJ" });
  await page.getByLabel("CNPJ", { exact: true }).selectOption({ label: "— não usar —" });
  await page.getByRole("button", { name: "Atualizar prévia" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main").getByRole("status")).toHaveText("Colunas atualizadas. A prévia abaixo foi refeita.");

  await page.getByRole("button", { name: "Confirmar e processar 2 empresa(s)" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main").getByRole("status")).toHaveText(
    "Lote confirmado: 2 empresa(s) na fila de processamento.",
  );
  expect(acoesLote).toEqual([
    {
      acao: "mapeamento",
      corpo: {
        mapeamento: {
          empresa: 0, site: 1, cnpj: null, cidade: 2, uf: null, contato_nome: null, contato_cargo: null,
          contato_email: null,
        },
      },
    },
    { acao: "confirmar" },
  ]);
  await expect(page.getByRole("region", { name: "Progresso" })).toBeVisible();
});

test("progresso mostra barra com texto, etapas e empresas com link para a ficha", async ({ page }) => {
  await prepararPainel(page, { lote: LOTE_PROCESSANDO });
  await page.goto(URL_LOTE);
  const progresso = page.getByRole("progressbar", { name: /1 de 2 empresa\(s\)/ });
  await expect(progresso).toHaveAttribute("value", "50");
  const regiao = page.getByRole("region", { name: "Progresso" });
  await expect(regiao.locator(".totais-auditoria")).toContainText("Com decisores1");
  await expect(regiao.getByRole("link", { name: "Hospital A" })).toHaveAttribute("href", "/empresas/e1");
  await expect(regiao.getByRole("row", { name: /Clínica B/ })).toContainText("a identificar");
  await page.getByText("Linhas que não viraram empresas novas (2)").click();
  await expect(page.getByText("Linha 5: sem nome da empresa nem site legível")).toBeVisible();
  await semViolacoes(page);
});

test("leitura vê a prévia sem poder confirmar", async ({ page }) => {
  await prepararPainel(page, { papel: "leitura" });
  await page.goto(URL_LOTE);
  await expect(page.getByRole("region", { name: "Prévia" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Confirmar e processar/ })).toHaveCount(0);
  await expect(page.getByLabel("Empresa", { exact: true })).toBeDisabled();
});

test("lista de lotes e área de envio sem violações", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/lotes");
  await expect(page.getByRole("link", { name: "hospitais.xlsx" })).toHaveAttribute("href", URL_LOTE);
  await semViolacoes(page);
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Prospecção em lote" })).toBeVisible();
  await semViolacoes(page);
});
