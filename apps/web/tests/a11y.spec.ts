import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// CONSTITUICAO §2.8: o próprio painel segue WCAG 2.2 AA. O CI falha se houver violações.
const paginas = ["/", "/login"];

for (const caminho of paginas) {
  test(`sem violações de acessibilidade em ${caminho}`, async ({ page }) => {
    await page.goto(caminho);
    const resultado = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(resultado.violations, JSON.stringify(resultado.violations, null, 2)).toEqual([]);
  });
}
