import { Sparkles } from "lucide-react";

import { type FunilDetalhado } from "@/lib/api";

/**
 * Sugestões derivadas por regra das mesmas contagens do funil já carregadas — nenhuma chamada de IA
 * nova. O rótulo "pela IA" é só a mesma moldura visual da referência de design.
 */
function montarAcoes(funil: FunilDetalhado): string[] {
  const acoes: string[] = [];
  if (funil.MAPEANDO_DECISORES > 0) {
    acoes.push(
      `Validar e-mails de ${funil.MAPEANDO_DECISORES} empresa(s) em Mapeando decisores para destravar o funil.`,
    );
  }
  if (funil.PREPARANDO_ABORDAGEM > 0) {
    acoes.push(`Iniciar sequência de abordagem com as ${funil.PREPARANDO_ABORDAGEM} empresa(s) prontas.`);
  }
  if (funil.NOVO + funil.PESQUISANDO + funil.AUDITANDO + funil.QUALIFICANDO === 0) {
    acoes.push("Nenhum prospect em processamento — envie um novo lote para manter o funil abastecido.");
  }
  return acoes;
}

export function AcoesRecomendadas({ funil }: { funil: FunilDetalhado | null }) {
  if (!funil) return null;
  const acoes = montarAcoes(funil);
  if (acoes.length === 0) return null;

  return (
    <div className="card">
      <span className="pill quente">
        <Sparkles size={14} aria-hidden="true" /> Ações recomendadas
      </span>
      <ol>
        {acoes.map((acao, i) => (
          <li key={i}>{acao}</li>
        ))}
      </ol>
    </div>
  );
}
