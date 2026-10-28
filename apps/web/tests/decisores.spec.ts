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

test("ficha mostra os decisores com a situação do e-mail em texto", async ({ page }) => {
  await prepararPainel(page);
  await page.goto(URL_FICHA);
  const tabela = page.getByRole("table", { name: "Decisores encontrados, um por área" });
  await expect(tabela.locator("tbody tr")).toHaveCount(3);
  const ana = tabela.getByRole("row", { name: /Ana Souza/ });
  await expect(ana).toContainText("TI");
  await expect(ana).toContainText("ana@hospitalexemplo.com.br");
  await expect(ana).toContainText("e-mail verificado");
  await expect(ana.getByRole("link", { name: "LinkedIn de Ana Souza (abre em nova aba)" })).toHaveAttribute(
    "href",
    "http://www.linkedin.com/in/ana-souza",
  );
  const carla = tabela.getByRole("row", { name: /Carla Dias/ });
  await expect(carla).toContainText("sem e-mail");
  await expect(carla.getByRole("link", { name: /hospitalexemplo\.com\.br/ })).toHaveAttribute(
    "href",
    "https://hospitalexemplo.com.br/diretoria",
  );
  const davi = tabela.getByRole("row", { name: /Davi Reis/ });
  await expect(davi).toContainText("e-mail verificado no Apify");
  await semViolacoes(page);
});

test("sem decisores, a ficha explica", async ({ page }) => {
  await prepararPainel(page, { ficha: { ...FICHA, decisores: [] } });
  await page.goto(URL_FICHA);
  await expect(page.getByRole("region", { name: "Decisores" })).toContainText("Nenhum decisor encontrado ainda.");
});

test("tabela de decisores rola pelo teclado em tela estreita", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await prepararPainel(page);
  await page.goto(URL_FICHA);
  const regiao = page.getByRole("region", { name: "Decisores encontrados, um por área" });
  await regiao.focus();
  await expect(regiao).toBeFocused();
  await semViolacoes(page);
});

test("painel mostra os créditos do Apollo do dia", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await expect(page.locator(".creditos-dia")).toHaveText("Créditos do Apollo hoje: 8 de 60.");
  await expect(page.locator(".apify-dia")).toHaveText("Apify hoje: US$ 0,07 de US$ 2,00.");
});
