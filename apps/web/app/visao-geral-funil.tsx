import { type FunilDetalhado } from "@/lib/api";

interface Fase {
  chave: string;
  rotulo: string;
  legenda: string;
  total: number;
  faixa: "neutro" | "morno" | "quente" | "verde";
}

function montarFases(funil: FunilDetalhado): Fase[] {
  return [
    { chave: "pesquisando", rotulo: "Pesquisando", legenda: "Montando o dossiê", faixa: "neutro",
      total: funil.NOVO + funil.PESQUISANDO },
    { chave: "auditando", rotulo: "Auditando", legenda: "Rodando a auditoria técnica", faixa: "neutro",
      total: funil.AUDITANDO },
    { chave: "qualificando", rotulo: "Qualificando", legenda: "Calculando o score", faixa: "neutro",
      total: funil.QUALIFICANDO },
    { chave: "mapeando_decisores", rotulo: "Mapeando decisores", legenda: "Buscando quem decide", faixa: "morno",
      total: funil.MAPEANDO_DECISORES },
    { chave: "preparando_abordagem", rotulo: "Preparando abordagem", legenda: "Decisor com e-mail válido",
      faixa: "quente", total: funil.PREPARANDO_ABORDAGEM },
    { chave: "em_sequencia", rotulo: "Em sequência", legenda: "Mensagem aprovada", faixa: "verde",
      total: funil.EM_SEQUENCIA },
    { chave: "respondeu", rotulo: "Respondeu", legenda: "Aguardando triagem", faixa: "verde",
      total: funil.RESPONDEU },
    { chave: "reuniao", rotulo: "Reunião agendada", legenda: "Compromisso no calendário", faixa: "verde",
      total: funil.REUNIAO_AGENDADA },
    { chave: "proposta", rotulo: "Proposta / Ganho", legenda: "Negócio em fechamento", faixa: "verde",
      total: funil.PROPOSTA_ENVIADA + funil.NEGOCIACAO + funil.GANHO },
  ];
}

/**
 * Visão geral do funil (CONSTITUICAO §12.1, §7.1): uma fase por etapa, com o total de empresas e, quando
 * há algo a fazer, um cartão de ação logo abaixo. Nunca mostra uma ação para um total zerado.
 */
export function VisaoGeralFunil({ funil }: { funil: FunilDetalhado | null }) {
  if (!funil) return null;
  const fases = montarFases(funil);
  const semDecisorValido = funil.MAPEANDO_DECISORES;
  const prontasParaSequencia = funil.PREPARANDO_ABORDAGEM;
  const foraDoFunil = funil.ARQUIVADO + funil.SEM_RESPOSTA + funil.NAO_INTERESSADO + funil.PERDIDO;

  return (
    <section aria-labelledby="titulo-funil-fases" style={{ marginTop: "1.5rem" }}>
      <h2 id="titulo-funil-fases">Visão geral do funil</h2>
      <p className="hint">
        Onde cada prospect está na jornada (§7.1). Clique numa fase para abrir essa coluna no CRM.
      </p>
      <ol className="funil-fases" role="list" aria-label="Fases do funil">
        {fases.map((f, i) => (
          <li key={f.chave}>
            <a href="/crm" className={`fase fase-${f.faixa}`} style={{ textDecoration: "none" }}>
              <span className="fase-rotulo">{f.rotulo}</span>
              <span className="fase-total">{f.total}</span>
              <span className="fase-legenda">{f.legenda}</span>
            </a>
            {i < fases.length - 1 && (
              <span className="seta" aria-hidden="true">→</span>
            )}
          </li>
        ))}
      </ol>

      <div className="funil-insight">
        {semDecisorValido > 0 && (
          <div className="card">
            <span className="pill morno">Precisa de decisão</span>
            <p style={{ margin: 0 }}>
              <strong>{semDecisorValido}</strong> empresa(s) em <strong>Mapeando decisores</strong> já tiveram
              busca completa, sem nenhum e-mail validado. Ficam paradas até o vendedor decidir.
            </p>
            <a href="/crm">Ver no CRM →</a>
          </div>
        )}
        {prontasParaSequencia > 0 && (
          <div className="card">
            <span className="pill quente">Pronto para avançar</span>
            <p style={{ margin: 0 }}>
              <strong>{prontasParaSequencia}</strong> empresa(s) em <strong>Preparando abordagem</strong> já
              têm decisor com e-mail válido — candidatas a gerar a sequência.
            </p>
            <a href="/crm">Ver no CRM →</a>
          </div>
        )}
        {foraDoFunil > 0 && (
          <div className="card">
            <span className="pill neutro">Fora do funil principal</span>
            <p style={{ margin: 0 }}>
              <strong>{foraDoFunil}</strong> empresa(s) arquivada(s), sem resposta, não interessada(s) ou
              perdida(s) — não contam nas fases acima.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
