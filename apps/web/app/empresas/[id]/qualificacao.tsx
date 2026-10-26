import type { Qualificacao } from "@/lib/api";

function pontos(valor: number): string {
  return valor.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

function porcento(peso: number): string {
  return `${Math.round(peso * 100)}%`;
}

/**
 * Score do Qualificador (CONSTITUICAO §7.3, Etapa 3). A faixa sempre aparece em texto, nunca só por cor (§2.8).
 * A tabela mostra de onde vem cada ponto, para o vendedor confiar no número e contestar quando discordar.
 */
export function QualificacaoDaEmpresa({ qualificacao }: { qualificacao: Qualificacao }) {
  const q = qualificacao;
  return (
    <section className="card" aria-labelledby="titulo-qualificacao" style={{ marginTop: "1.5rem" }}>
      <h2 id="titulo-qualificacao" style={{ marginTop: 0 }}>Qualificação</h2>
      <p className={`score-faixa faixa-${q.faixa}`}>
        <strong>
          Score {q.score} de 100 — {q.rotulo_faixa}
        </strong>{" "}
        <span>({q.proximo_passo})</span>
      </p>
      <div className="tabela-rolavel" role="region" aria-labelledby="legenda-score" tabIndex={0}>
        <table>
          <caption id="legenda-score">De onde vem o score</caption>
          <thead>
            <tr>
              <th scope="col">Componente</th>
              <th scope="col">Valor (0 a 100)</th>
              <th scope="col">Peso</th>
              <th scope="col">Pontos no score</th>
              <th scope="col">Por quê</th>
            </tr>
          </thead>
          <tbody>
            {q.componentes.map((c) => (
              <tr key={c.chave}>
                <th scope="row">{c.rotulo}</th>
                <td>{c.valor}</td>
                <td>{porcento(c.peso)}</td>
                <td>{pontos(c.contribuicao)}</td>
                <td>{c.justificativa}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Calculado em {new Date(q.criado_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })} pela{" "}
        {q.regra_versao}, sem IA. Os pesos ficam em Configurações.
      </p>
    </section>
  );
}
