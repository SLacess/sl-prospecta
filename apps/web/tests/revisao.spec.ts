import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import { EMPRESA, prepararPainel } from "./api-falsa";

const URL_FICHA = `/empresas/${EMPRESA.id}`;

async function semViolacoes(page: Page) {
  const resultado = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(resultado.violations, JSON.stringify(resultado.violations, null, 2)).toEqual([]);
}

test("só o admin vê a revisão na ficha", async ({ page }) => {
  await prepararPainel(page, { papel: "vendedor" });
  await page.goto(URL_FICHA);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Revisão da auditoria" })).toHaveCount(0);
});

test("admin revisa só com teclado: motivo obrigatório quando não está correto", async ({ page }) => {
  const { revisoes } = await prepararPainel(page, { papel: "admin" });
  await page.goto(URL_FICHA);
  const secao = page.getByRole("region", { name: "Revisão da auditoria" });
  await expect(secao).toBeVisible();

  // Primeiro achado: Correto; segundo: Parcialmente, sem motivo → erro
  const primeiro = secao.getByRole("group").nth(0);
  await primeiro.getByRole("radio", { name: "Correto", exact: true }).focus();
  await page.keyboard.press("Space");
  const segundo = secao.getByRole("group").nth(1);
  await segundo.getByRole("radio", { name: "Parcialmente" }).check();
  await secao.getByRole("button", { name: "Salvar revisão" }).click();
  await expect(secao.getByRole("alert")).toHaveText("Explique o motivo de cada item que não está correto.");
  expect(revisoes).toEqual([]);

  await segundo.getByLabel("O que está errado ou incompleto?").fill("A imagem decorativa não precisa de alt.");
  await secao.getByRole("button", { name: "Salvar revisão" }).click();
  await expect(secao.getByRole("status")).toHaveText("Revisão salva. O placar da Fase 1 foi atualizado.");
  expect(revisoes).toEqual([
    {
      achados: [
        { chave: "label", veredito: "correto", motivo: null },
        { chave: "image-alt", veredito: "parcial", motivo: "A imagem decorativa não precisa de alt." },
      ],
      tecnicos: [],
      textos_honestos: true,
    },
  ]);
});

test("achado sem marcação é avisado antes de enviar", async ({ page }) => {
  const { revisoes } = await prepararPainel(page, { papel: "admin" });
  await page.goto(URL_FICHA);
  const secao = page.getByRole("region", { name: "Revisão da auditoria" });
  await secao.getByRole("button", { name: "Salvar revisão" }).click();
  await expect(secao.getByRole("alert")).toContainText("Marque os 3 achados para leigos");
  expect(revisoes).toEqual([]);
});

test("revisão na ficha sem violações de acessibilidade", async ({ page }) => {
  await prepararPainel(page, { papel: "admin" });
  await page.goto(URL_FICHA);
  const secao = page.getByRole("region", { name: "Revisão da auditoria" });
  await secao.getByRole("group").nth(0).getByRole("radio", { name: "Incorreto" }).check();
  await secao.getByText("Problemas técnicos (opcional, 1)").click();
  await expect(secao.getByLabel("O que está errado ou incompleto?")).toBeVisible();
  await semViolacoes(page);
});

test("placar da Fase 1 mostra as pendências em texto e leva às fichas", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/revisao");
  await expect(page.getByRole("heading", { level: 1, name: "Revisão da Fase 1" })).toBeVisible();
  const placar = page.locator(".totais-auditoria");
  await expect(placar).toContainText("Auditorias revisadas1 de 20");
  await expect(placar).toContainText("Achados corretos83,3%");
  await expect(page.locator(".situacao")).toContainText("Critério ainda não atingido.");
  await expect(page.locator(".situacao")).toContainText("faltam 19 auditoria(s) revisada(s)");
  const tabela = page.getByRole("table", { name: "Auditorias analisadas e situação da revisão" });
  await expect(tabela.getByRole("row", { name: /Faculdade Y/ })).toContainText("pendente");
  await tabela.getByRole("link", { name: "Hospital Exemplo S.A." }).click();
  await expect(page).toHaveURL(new RegExp(`${URL_FICHA}$`));
});

test("placar sem violações de acessibilidade", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/revisao");
  await expect(page.getByRole("table")).toBeVisible();
  await semViolacoes(page);
});
