import type { Decisor } from "@/lib/api";

const ROTULO_FONTE: Record<string, string> = {
  apollo: "Apollo",
  "web+apollo": "Apollo",
  "web+apify": "Apify",
  planilha: "Planilha",
};
/** Quem verificou o e-mail quando o nome veio de fonte pública (ADR 0012). */
const ROTULO_EMAIL_POR: Record<string, string> = {
  "web+apify": "e-mail verificado no Apify",
};

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/**
 * Decisores da empresa (CONSTITUICAO §7.3, Etapa 4): até 3, um por área. A situação do e-mail aparece sempre
 * escrita (§2.8). O LinkedIn é só um link; a plataforma não lê perfis (CLAUDE.md, regra 7).
 */
export function DecisoresDaEmpresa({ decisores }: { decisores: Decisor[] }) {
  return (
    <section className="card" aria-labelledby="titulo-decisores" style={{ marginTop: "1.5rem" }}>
      <h2 id="titulo-decisores" style={{ marginTop: 0 }}>Decisores</h2>
      {decisores.length === 0 ? (
        <p className="hint">Nenhum decisor encontrado ainda.</p>
      ) : (
        <div className="tabela-rolavel" role="region" aria-labelledby="legenda-decisores" tabIndex={0}>
          <table>
            <caption id="legenda-decisores">Decisores encontrados, um por área</caption>
            <thead>
              <tr>
                <th scope="col">Nome</th>
                <th scope="col">Área</th>
                <th scope="col">Cargo</th>
                <th scope="col">E-mail</th>
                <th scope="col">Situação do e-mail</th>
                <th scope="col">Fonte</th>
              </tr>
            </thead>
            <tbody>
              {decisores.map((d) => (
                <tr key={d.id}>
                  <th scope="row">
                    {d.nome}
                    {d.linkedin_url && (
                      <>
                        {" "}
                        <a href={d.linkedin_url} target="_blank" rel="noopener noreferrer">
                          LinkedIn
                          <span className="visually-hidden"> de {d.nome} (abre em nova aba)</span>
                        </a>
                      </>
                    )}
                  </th>
                  <td>{d.area}</td>
                  <td>{d.cargo ?? "—"}</td>
                  <td>{d.email ?? "—"}</td>
                  <td className={`status-email email-${d.email_status}`}>{d.rotulo_email}</td>
                  <td>
                    {d.fonte_url ? (
                      <a href={d.fonte_url} target="_blank" rel="noopener noreferrer">
                        {host(d.fonte_url)}
                        <span className="visually-hidden"> (fonte pública, abre em nova aba)</span>
                      </a>
                    ) : (
                      ROTULO_FONTE[d.fonte] ?? d.fonte
                    )}
                    {d.fonte_url && d.fonte !== "web+apollo" && ROTULO_EMAIL_POR[d.fonte] && (
                      <span className="hint"> · {ROTULO_EMAIL_POR[d.fonte]}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="hint">
        Só e-mails verificados contam como contato válido. Nada é enviado nesta fase.
      </p>
    </section>
  );
}
