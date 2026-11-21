import { CheckCircle2, CircleDollarSign, Coins, Loader2 } from "lucide-react";

import { type Disjuntores, type FunilDetalhado } from "@/lib/api";

interface Props {
  funil: FunilDetalhado | null;
  disjuntor: Disjuntores["custo"] | null;
  apollo: Disjuntores["apollo"] | null;
}

/**
 * Cartões de estatística do Painel de Prospecção — todos com dado real já buscado pela página (nada
 * aqui faz uma chamada própria): `/crm/funil-detalhado` e `/governanca/disjuntores`.
 */
export function EstatisticasPainel({ funil, disjuntor, apollo }: Props) {
  const emProcessamento = funil
    ? funil.NOVO + funil.PESQUISANDO + funil.AUDITANDO + funil.QUALIFICANDO
    : null;
  const creditosRestantes = apollo ? Math.max(apollo.teto - apollo.creditos_hoje, 0) : null;

  return (
    <div className="stat-grid">
      <div className="stat-card">
        <span className="fase-icone neutro" aria-hidden="true"><Loader2 size={20} /></span>
        <div>
          <p className="stat-card-rotulo">Prospects em processamento</p>
          <p className="stat-card-valor">{emProcessamento ?? "—"}</p>
        </div>
      </div>
      <div className="stat-card">
        <span className="fase-icone morno" aria-hidden="true"><Coins size={20} /></span>
        <div>
          <p className="stat-card-rotulo">Créditos do Apollo restantes</p>
          <p className="stat-card-valor">{creditosRestantes ?? "—"}</p>
        </div>
      </div>
      <div className="stat-card">
        <span className="fase-icone quente" aria-hidden="true"><CircleDollarSign size={20} /></span>
        <div>
          <p className="stat-card-rotulo">Custo de IA hoje</p>
          <p className="stat-card-valor">
            {disjuntor ? `R$ ${disjuntor.custo_hoje_brl}` : "—"}
          </p>
        </div>
      </div>
      <div className="stat-card">
        <span className="fase-icone verde" aria-hidden="true"><CheckCircle2 size={20} /></span>
        <div>
          <p className="stat-card-rotulo">Empresas prontas para avançar</p>
          <p className="stat-card-valor">{funil?.PREPARANDO_ABORDAGEM ?? "—"}</p>
        </div>
      </div>
    </div>
  );
}
