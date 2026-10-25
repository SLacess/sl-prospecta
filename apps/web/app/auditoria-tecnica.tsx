import type { AuditoriaResumo, PaginaAuditada } from "@/lib/api";

const GRAVIDADES: [string, string][] = [
  ["critico", "Crítico"],
  ["grave", "Grave"],
  ["moderado", "Moderado"],
  ["leve", "Leve"],
];

function caminho(url: string): string {
  try {
    return new URL(url).pathname || "/";
  } catch {
    return url;
  }
}

function resumoTeclado(p: PaginaAuditada): string {
  const itens: string[] = [];
  if (p.armadilha_de_foco) itens.push("armadilha de foco");
  if (p.link_pular_conteudo === false) itens.push("sem link “pular para o conteúdo”");
  if (p.sem_indicador_de_foco > 0) itens.push(`${p.sem_indicador_de_foco} elemento(s) sem foco visível aparente`);
  return itens.length ? itens.join("; ") : "nenhum problema detectado";
}

/**
 * Resultado bruto do Auditor técnico (CONSTITUICAO §8.1). Gravidade sempre em texto, nunca só por cor;
 * aviso de honestidade técnica (§2.2) fixo no cartão.
 */
export function AuditoriaTecnica({ auditoria }: { auditoria: AuditoriaResumo }) {
  return (
    <section aria-labelledby="titulo-auditoria" className="auditoria">
      <h3 id="titulo-auditoria">Auditoria técnica</h3>
      <p className="hint">
        Testes automáticos (axe-core, navegação por teclado e tela de 320 px) encontram só parte das barreiras de
        acessibilidade. A nota e os achados explicados para leigos entram na próxima etapa.
      </p>

      <dl className="totais-auditoria">
        {GRAVIDADES.map(([chave, rotulo]) => (
          <div key={chave}>
            <dt>{rotulo}</dt>
            <dd>{auditoria.totais[chave] ?? 0}</dd>
          </div>
        ))}
      </dl>
      <p className="hint">Problemas automáticos por gravidade, somando as páginas testadas.</p>

      {auditoria.plugins.length > 0 && (
        <p>
          <strong>Plugin de acessibilidade já instalado:</strong> {auditoria.plugins.join(", ")}.
        </p>
      )}

      <div className="tabela-rolavel" role="region" aria-labelledby="legenda-paginas" tabIndex={0}>
        <table>
          <caption id="legenda-paginas">Páginas testadas</caption>
          <thead>
            <tr>
              <th scope="col">Página</th>
              <th scope="col">Problemas automáticos</th>
              <th scope="col">Teclado</th>
              <th scope="col">Tela de 320 px</th>
            </tr>
          </thead>
          <tbody>
            {auditoria.paginas.map((p) => (
              <tr key={p.url}>
                <th scope="row">{caminho(p.url)}</th>
                {p.status === "ok" ? (
                  <>
                    <td>{p.problemas}</td>
                    <td>{resumoTeclado(p)}</td>
                    <td>{p.rolagem_horizontal_320 ? "rolagem horizontal (conteúdo não cabe)" : "cabe na tela"}</td>
                  </>
                ) : (
                  <td colSpan={3}>Não testada: {p.erro ?? p.status}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
