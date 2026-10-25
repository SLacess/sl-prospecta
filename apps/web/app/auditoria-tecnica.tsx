import type { AnaliseAuditoria, AuditoriaResumo, PaginaAuditada } from "@/lib/api";

const GRAVIDADES: [string, string][] = [
  ["critico", "Crítico"],
  ["grave", "Grave"],
  ["moderado", "Moderado"],
  ["leve", "Leve"],
];

const TIPO_INDICIO: Record<string, string> = {
  texto_em_imagem: "Texto dentro de imagem",
  informacao_so_por_cor: "Informação só por cor",
  captcha_visual: "CAPTCHA visual",
  video_sem_legenda_aparente: "Vídeo sem legenda aparente",
  outro: "Outro",
};

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

function Analise({ nota, analise }: { nota: number; analise: AnaliseAuditoria }) {
  return (
    <>
      <p className="nota">
        <span className="nota-numero">{nota}</span> <span>de 100</span>
      </p>
      <p className="hint">
        Nota automática: parte de 100 e desconta pontos por problema encontrado, conforme a gravidade.
      </p>

      {analise.top3_para_leigos.length > 0 && (
        <>
          <h4>Principais achados</h4>
          <ol className="achados">
            {analise.top3_para_leigos.map((a) => (
              <li key={`${a.pagina}-${a.titulo}`}>
                <p className="achado-titulo">{a.titulo}</p>
                <p>{a.impacto_humano}</p>
                <p className="hint">
                  Quem é afetado: {a.quem_e_afetado.join(", ")} · Página: {a.pagina} · Critério WCAG{" "}
                  {a.criterio_wcag}
                </p>
                {a.trecho_html && (
                  <details>
                    <summary>Ver trecho do código</summary>
                    <pre>
                      <code>{a.trecho_html}</code>
                    </pre>
                  </details>
                )}
              </li>
            ))}
          </ol>
        </>
      )}

      <div className="duas-colunas">
        <div>
          <h4>O que o plugin ajuda a resolver</h4>
          {analise.plugin_resolve_parcialmente.length ? (
            <ul>
              {analise.plugin_resolve_parcialmente.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="hint">Nenhum dos problemas encontrados.</p>
          )}
          <p className="hint">Ajuda parcial: o plugin oferece recursos ao visitante, mas não corrige o site.</p>
        </div>
        <div>
          <h4>O que exige ajuste no código</h4>
          {analise.exige_ajuste_no_codigo.length ? (
            <ul>
              {analise.exige_ajuste_no_codigo.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="hint">Nenhum dos problemas encontrados.</p>
          )}
        </div>
      </div>

      {analise.indicios_visuais.length > 0 && (
        <>
          <h4>Indícios nos prints (a confirmar)</h4>
          <ul>
            {analise.indicios_visuais.map((i) => (
              <li key={`${i.pagina}-${i.descricao}`}>
                <strong>{TIPO_INDICIO[i.tipo] ?? i.tipo}:</strong> {i.descricao} ({caminho(i.pagina)})
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="observacao">{analise.observacao_honestidade}</p>
    </>
  );
}

/**
 * Auditoria de acessibilidade (CONSTITUICAO §8.1 e §8.2): nota, achados para leigos, plugin × código e o
 * resultado técnico. Gravidade sempre em texto, nunca só por cor; aviso de honestidade técnica (§2.2) fixo.
 */
export function AuditoriaTecnica({ auditoria }: { auditoria: AuditoriaResumo }) {
  const analisada = auditoria.nota !== null && auditoria.analise !== null;
  return (
    <section aria-labelledby="titulo-auditoria" className="auditoria">
      <h3 id="titulo-auditoria">Auditoria de acessibilidade</h3>
      {analisada ? (
        <Analise nota={auditoria.nota as number} analise={auditoria.analise as AnaliseAuditoria} />
      ) : (
        <p className="hint">
          Testes automáticos (axe-core, navegação por teclado e tela de 320 px) encontram só parte das barreiras de
          acessibilidade. A nota e os achados explicados para leigos vêm em seguida.
        </p>
      )}

      <h4>Resultado técnico</h4>
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
