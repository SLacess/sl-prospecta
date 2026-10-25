import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { EMPRESA, FICHA, prepararPainel } from "./api-falsa";

const URL_FICHA = `/empresas/${EMPRESA.id}`;

test("andamento leva à ficha completa", async ({ page }) => {
  await prepararPainel(page);
  await page.goto("/");
  await page.getByLabel("Nome da empresa ou site").fill("hospitalexemplo.com.br");
  await page.getByRole("button", { name: "Prospectar" }).click();
  await page.getByRole("link", { name: /Abrir ficha completa/ }).click();
  await expect(page).toHaveURL(new RegExp(`${URL_FICHA}$`));
  await expect(page.getByRole("heading", { level: 1, name: "Hospital Exemplo S.A." })).toBeVisible();
});

test("ficha mostra dossiê, auditoria, evidências e linha do tempo", async ({ page }) => {
  await prepararPainel(page);
  await page.goto(URL_FICHA);

  await expect(page.locator(".resumo")).toContainText("Qualificando");
  await expect(page.locator(".resumo")).toContainText("Sorocaba / SP");
  await expect(page.getByRole("heading", { name: "Dossiê" })).toBeVisible();
  await expect(page.getByText("“Programa de inclusão de pessoas com deficiência.”")).toBeVisible();
  await expect(page.getByRole("link", { name: /fonte: \/esg/ })).toHaveAttribute(
    "href",
    "https://hospitalexemplo.com.br/esg",
  );
  await expect(page.getByText("o site não informa número de leitos")).toBeVisible();

  const auditoria = page.getByRole("region", { name: "Auditoria de acessibilidade" });
  await expect(auditoria.locator(".nota")).toHaveText("58 de 100");
  await expect(page.getByRole("img", { name: /com o problema 1 destacado/ })).toBeVisible();
  await expect(page.locator(".caixa-evidencia")).toHaveText("1");
  await expect(page.getByText("Print não disponível para esta página.")).toBeVisible();

  await expect(page.locator(".linha-do-tempo li")).toHaveCount(FICHA.eventos.length);
});

test("baixa o PDF só com teclado e anuncia no status", async ({ page }) => {
  await prepararPainel(page);
  await page.goto(URL_FICHA);
  await page.getByRole("button", { name: "Baixar relatório (PDF)" }).focus();
  const [download] = await Promise.all([page.waitForEvent("download"), page.keyboard.press("Enter")]);
  expect(download.suggestedFilename()).toBe("diagnostico-acessibilidade-hospitalexemplo-com-br.pdf");
  await expect(page.locator(".acoes-ficha [role=status]")).toHaveText("Download do relatório iniciado.");
});

test("versão web abre em nova aba", async ({ page, context }) => {
  await prepararPainel(page);
  await page.goto(URL_FICHA);
  const [aba] = await Promise.all([
    context.waitForEvent("page"),
    page.getByRole("button", { name: "Ver versão web" }).click(),
  ]);
  await aba.waitForLoadState();
  await expect(aba.getByRole("heading", { name: "Relatório" })).toBeVisible();
});

test("sem relatório, a ficha explica quando ele fica disponível", async ({ page }) => {
  await prepararPainel(page, { ficha: { ...FICHA, relatorio_disponivel: false } });
  await page.goto(URL_FICHA);
  await expect(page.getByText("O relatório fica disponível quando a análise da auditoria termina.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Baixar relatório (PDF)" })).toHaveCount(0);
});

test("ficha sem violações de acessibilidade", async ({ page }) => {
  await prepararPainel(page);
  await page.goto(URL_FICHA);
  await expect(page.getByRole("img", { name: /destacado/ })).toBeVisible();
  await page.getByText("Páginas lidas e tecnologia do site").click();
  const resultado = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(resultado.violations, JSON.stringify(resultado.violations, null, 2)).toEqual([]);
});
