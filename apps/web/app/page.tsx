"use client";

import { useState } from "react";

/**
 * Painel de Prospecção (CONSTITUICAO §12.1, tela 1).
 * Fase 0: interface pronta e acessível; o processamento real entra na Fase 1.
 */
export default function PainelProspeccao() {
  const [mensagem, setMensagem] = useState("");

  function aoProspectar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const valor = new FormData(e.currentTarget).get("alvo")?.toString().trim();
    if (!valor) {
      setMensagem("Digite o nome da empresa ou o endereço do site.");
      return;
    }
    setMensagem(`Recebido: "${valor}". A prospecção automática será ativada na Fase 1.`);
  }

  return (
    <>
      <h1>Painel de Prospecção</h1>
      <p className="lead">
        Informe uma empresa e a SL Prospecta pesquisa, audita a acessibilidade do site, qualifica e prepara a
        abordagem.
      </p>

      <section className="card" aria-labelledby="titulo-individual">
        <h2 id="titulo-individual" style={{ marginTop: 0 }}>Prospecção individual</h2>
        <form onSubmit={aoProspectar} noValidate>
          <div className="row">
            <div className="grow">
              <label htmlFor="alvo">Nome da empresa ou site</label>
              <input
                id="alvo"
                name="alvo"
                type="text"
                autoComplete="off"
                placeholder="ex.: hospitalexemplo.com.br"
                aria-describedby="alvo-dica"
              />
              <p id="alvo-dica" className="hint">
                Pode ser o nome (ex.: Hospital Exemplo) ou o endereço do site.
              </p>
            </div>
            <button type="submit">Prospectar</button>
          </div>
        </form>
        <div role="status" aria-live="polite" className={mensagem ? "status" : undefined}>
          {mensagem}
        </div>
      </section>

      <section className="card" aria-labelledby="titulo-lote" style={{ marginTop: "1.5rem" }}>
        <h2 id="titulo-lote" style={{ marginTop: 0 }}>Prospecção em lote</h2>
        <label htmlFor="planilha">Planilha de empresas (.xlsx ou .csv)</label>
        <input id="planilha" type="file" accept=".xlsx,.csv" aria-describedby="planilha-dica" disabled />
        <p id="planilha-dica" className="hint">
          Disponível na Fase 2. A IA vai identificar as colunas sozinha e mostrar uma prévia antes de processar.
        </p>
      </section>

      <h2>Funil</h2>
      <div className="grid" role="list" aria-label="Indicadores do funil">
        {["Prospects", "Qualificados", "Abordados", "Reuniões"].map((rotulo) => (
          <div key={rotulo} className="card" role="listitem">
            <div className="hint">{rotulo}</div>
            <div style={{ fontSize: "1.6rem", fontWeight: 700 }}>0</div>
          </div>
        ))}
      </div>
    </>
  );
}
