import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import { EMPRESA, FICHA, prepararPainel } from "./api-falsa";

const URL_FICHA = `/empresas/${EMPRESA.id}`;

async function semViolacoes(page: Page) {
  const resultado = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(resultado.violations, JSON.stringify(resultado.violations, null, 2)).toEqual([]);
}

// --- Ficha ---------------------------------------------------------------------

test("ficha mostra o score em número e a faixa em texto, com os 5 componentes", async ({ page }) => {
  await prepararPainel(page);
  await page.goto(URL_FICHA);
  const secao = page.getByRole("region", { name: "Qualificação" });
  await expect(secao.locator(".score-faixa")).toHaveText("Score 61 de 100 — Morno (abordagem padrão)");
  const tabela = secao.getByRole("table", { name: "De onde vem o score" });
  await expect(tabela.locator("tbody tr")).toHaveCount(5);
  await expect(tabela.getByRole("row", { name: /Pressão regulatória do setor/ })).toContainText("11,3");
  await expect(tabela.getByRole("row", { name: /Acesso ao decisor/ })).toContainText("Ainda sem contatos mapeados");
  await semViolacoes(page);
});

test("ficha sem qualificação não mostra a seção", async ({ page }) => {
  await prepararPainel(page, { ficha: { ...FICHA, qualificacao: null } });
  await page.goto(URL_FICHA);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Qualificação" })).toHaveCount(0);
});

// --- Configurações -------------------------------------------------------------

test("vendedor vê os valores em vigor, sem formulário", async ({ page }) => {
  await prepararPainel(page, { papel: "vendedor" });
  await page.goto("/configuracoes");
  const vigentes = page.getByRole("region", { name: "Valores em vigor" });
  await expect(vigentes).toContainText("Aderência ao perfil de cliente (ICP)30%");
  await expect(vigentes).toContainText("de 45 a 69");
  await expect(page.getByRole("button", { name: "Salvar pesos e faixas" })).toHaveCount(0);
  await semViolacoes(page);
});

test("admin altera pesos só com teclado e vê a soma ao vivo", async ({ page }) => {
  const { configs } = await prepararPainel(page, { papel: "admin" });
  await page.goto("/configuracoes");
  const fit = page.getByLabel(/Aderência ao perfil de cliente/);
  await expect(fit).toHaveValue("30");

  await fit.focus();
  await page.keyboard.press("Control+A");
  await page.keyboard.type("20");
  await expect(page.locator(".soma-pesos")).toHaveText("Soma dos pesos: 90% (precisa ser 100%)");
  await page.getByLabel(/Sinais de interesse/).fill("35");
  await expect(page.locator(".soma-pesos")).toHaveText("Soma dos pesos: 100% (ok)");

  await page.getByRole("button", { name: "Salvar pesos e faixas" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main").getByRole("status")).toContainText("Pesos e faixas salvos.");
  expect(configs).toEqual([
    {
      pesos: { fit_icp: 0.2, intencao: 0.35, gravidade_barreiras: 0.2, pressao_regulatoria: 0.15, acessibilidade_decisor: 0.1 },
      faixas: { quente: 70, morno: 45 },
    },
  ]);
});

test("soma diferente de 100% não é enviada e o foco vai para o problema", async ({ page }) => {
  const { configs } = await prepararPainel(page, { papel: "admin" });
  await page.goto("/configuracoes");
  await page.getByLabel(/Aderência ao perfil de cliente/).fill("50");
  await page.getByRole("button", { name: "Salvar pesos e faixas" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("Os pesos precisam somar 100% (hoje somam 120%).");
  expect(configs).toEqual([]);
});

test("faixas incoerentes mostram o erro junto do campo", async ({ page }) => {
  const { configs } = await prepararPainel(page, { papel: "admin" });
  await page.goto("/configuracoes");
  await page.getByLabel(/Morno a partir de/).fill("80");
  await page.getByRole("button", { name: "Salvar pesos e faixas" }).click();
  const morno = page.getByLabel(/Morno a partir de/);
  await expect(morno).toBeFocused();
  await expect(morno).toHaveAttribute("aria-invalid", "true");
  await expect(morno).toHaveAccessibleDescription("O início da faixa Morno precisa ser menor que o da faixa Quente.");
  expect(configs).toEqual([]);
  await semViolacoes(page);
});

test("erro da API aparece no alerta", async ({ page }) => {
  await prepararPainel(page, {
    papel: "admin",
    respostaConfigScore: { status: 403, corpo: { detail: "Permissão insuficiente." } },
  });
  await page.goto("/configuracoes");
  await page.getByRole("button", { name: "Salvar pesos e faixas" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("Permissão insuficiente.");
});
