import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import { ANDAMENTO_CONFIRMACAO, EVENTOS_FINAIS, prepararPainel } from "./api-falsa";

// CONSTITUICAO §2.8: o próprio painel segue WCAG 2.2 AA. O CI falha se houver violações.
async function semViolacoes(page: Page) {
  const resultado = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(resultado.violations, JSON.stringify(resultado.violations, null, 2)).toEqual([]);
}

test("sem violações de acessibilidade em /login", async ({ page }) => {
  await page.goto("/login");
  await semViolacoes(page);
});

test("sem violações no painel inicial", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Painel de Prospecção" })).toBeVisible();
  await semViolacoes(page);
});

test("sem violações com o andamento ao vivo na tela", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("hospitalexemplo.com.br");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await expect(page.locator(".linha-do-tempo li")).toHaveCount(EVENTOS_FINAIS.length);
  await expect(page.locator(".resumo-dossie li")).toHaveCount(5);
  await semViolacoes(page);
});

test("sem violações com o aviso do disjuntor de custo", async ({ page }) => {
  await prepararPainel(page, { disjuntorAtingido: true });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Fila de IA pausada/ })).toBeVisible();
  await semViolacoes(page);
});

test("sem violações com mensagem de erro", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await expect(page.locator("#alvo-erro")).toContainText("Digite o nome da empresa");
  await semViolacoes(page);
});

test("sem violações com a confirmação do site na tela", async ({ page }) => {
  await prepararPainel(page, { andamento: ANDAMENTO_CONFIRMACAO });
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("Unimed");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await page.getByRole("radio", { name: "Outro site" }).check();
  await expect(page.getByLabel("Endereço do site oficial")).toBeVisible();
  await semViolacoes(page);
});
