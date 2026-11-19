import type { Sequencia } from "@/lib/api";

const ROTULO_ANGULO: Record<string, string> = {
  experiencia_cliente: "Experiência do cliente",
  inclusao_colaboradores_pcd: "Inclusão de colaboradores PcD",
  esg_reputacao: "ESG / reputação",
  conformidade_legal: "Conformidade legal",
  conversao_alcance_mercado: "Conversão e alcance de mercado",
};

const ROTULO_STATUS_TOQUE: Record<string, string> = {
  planejada: "planejada",
  rascunho: "rascunho",
};

/**
 * Sequência de abordagem (CONSTITUICAO §7.3, Etapas 5-6, a partir da Fase 3): a decisão do Estrategista por
 * contato e os toques planejados. Só o toque de dia 0 tem texto; os demais ainda são plano (§9.3).
 */
export function SequenciaDaEmpresa({ sequencias }: { sequencias: Sequencia[] }) {
  return (
    <section className="card" aria-labelledby="titulo-sequencia" style={{ marginTop: "1.5rem" }}>
      <h2 id="titulo-sequencia" style={{ marginTop: 0 }}>Sequência</h2>
      <p className="hint">
        Nada é enviado pela plataforma nesta fase (ADR 0014) — o texto aprovado é para o vendedor enviar à mão.
      </p>
      {sequencias.map((seq) => {
        const dia0 = seq.toques.find((t) => t.dia === 0);
        const aprovado = dia0?.aprovado;
        return (
          <div key={seq.id} style={{ marginTop: "1.25rem" }}>
            <h3 style={{ marginBottom: "0.3rem" }}>
              {seq.contato_nome} <span className="hint" style={{ fontWeight: 400 }}>({seq.contato_area})</span>
            </h3>
            <p className="hint" style={{ margin: "0 0 0.6rem" }}>
              Ângulo: {ROTULO_ANGULO[seq.angulo] ?? seq.angulo} · Gancho: {seq.achado_titulo}
            </p>
            <ol className="linha-do-tempo" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {seq.toques.map((t) => (
                <li key={t.dia} style={{ display: "flex", gap: "0.9rem", marginBottom: "0.6rem" }}>
                  <span className="hint" style={{ minWidth: "3.2rem" }}>Dia {t.dia}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span className={`pill ${t.status === "rascunho" ? "verde" : "neutro"}`}>
                      {ROTULO_STATUS_TOQUE[t.status] ?? t.status}
                    </span>
                    {t.nota !== null && <span className="hint"> nota {t.nota}/10</span>}
                    {t.assunto ? (
                      <>
                        <p style={{ margin: "0.35rem 0 0", fontWeight: 600 }}>{t.assunto}</p>
                        <p style={{ margin: "0.2rem 0 0" }} className="hint">{t.corpo}</p>
                      </>
                    ) : (
                      <p style={{ margin: "0.35rem 0 0" }} className="hint">{t.conteudo_sugerido}</p>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            {dia0 && aprovado === false && (
              <p className="hint">
                O Crítico não aprovou depois de {dia0.tentativas} tentativa(s): {dia0.motivo_critico}
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}
