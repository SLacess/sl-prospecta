"use client";

import { useEffect, useState } from "react";

import { apiFetch, ErroApi, lerToken, type Placar, ROTULO_SETOR } from "@/lib/api";

function porcento(valor: number | null): string {
  return valor === null ? "—" : `${valor.toLocaleString("pt-BR")}%`;
}

/** Placar do critério da Fase 1 (CONSTITUICAO §19): 20 auditorias revisadas, ≥ 90% de achados corretos. */
export default function RevisaoFase1() {
  const [placar, setPlacar] = useState<Placar | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    apiFetch<Placar>("/revisao/fase1")
      .then(setPlacar)
      .catch((e) => setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar o placar."));
  }, []);

  return (
    <>
      <h1>Revisão da Fase 1</h1>
      <p className="lead">
        Para avançar à Fase 2, {placar?.meta_auditorias ?? 20} auditorias reais de pelo menos{" "}
        {placar?.meta_setores ?? 4} setores precisam ser revisadas, com {placar?.meta_percentual ?? 90}% ou mais de
        achados corretos e nenhum texto prometendo conformidade total.
      </p>
      <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>

      {placar && (
        <>
          <section className="card" aria-labelledby="titulo-placar">
            <h2 id="titulo-placar" style={{ marginTop: 0 }}>Placar</h2>
            <dl className="totais-auditoria">
              <div>
                <dt>Auditorias revisadas</dt>
                <dd>
                  {placar.auditorias_revisadas} de {placar.meta_auditorias}
                </dd>
              </div>
              <div>
                <dt>Setores diferentes</dt>
                <dd>
                  {placar.setores} de {placar.meta_setores}
                </dd>
              </div>
              <div>
                <dt>Achados corretos</dt>
                <dd>{porcento(placar.percentual_correto)}</dd>
              </div>
              <div>
                <dt>Textos com promessa</dt>
                <dd>{placar.promessas_encontradas}</dd>
              </div>
            </dl>
            <p className={placar.atingido ? "situacao atingido" : "situacao"}>
              <strong>{placar.atingido ? "Critério atingido." : "Critério ainda não atingido."}</strong>{" "}
              {placar.atingido ? "A Fase 1 pode ser encerrada." : `Pendências: ${placar.pendencias.join("; ")}.`}
            </p>
            <p className="hint">“Parcialmente correto” conta meio acerto.</p>
          </section>

          <section className="card" aria-labelledby="titulo-lista-revisao" style={{ marginTop: "1.5rem" }}>
            <h2 id="titulo-lista-revisao" style={{ marginTop: 0 }}>Auditorias analisadas</h2>
            <div className="tabela-rolavel" role="region" aria-labelledby="legenda-revisao" tabIndex={0}>
              <table>
                <caption id="legenda-revisao">Auditorias analisadas e situação da revisão</caption>
                <thead>
                  <tr>
                    <th scope="col">Empresa</th>
                    <th scope="col">Setor</th>
                    <th scope="col">Nota</th>
                    <th scope="col">Revisão</th>
                    <th scope="col">Corretos</th>
                  </tr>
                </thead>
                <tbody>
                  {placar.lista.map((linha) => (
                    <tr key={linha.empresa_id}>
                      <th scope="row">
                        <a href={`/empresas/${linha.empresa_id}`}>{linha.nome}</a>
                      </th>
                      <td>{linha.setor ? ROTULO_SETOR[linha.setor] ?? linha.setor : "—"}</td>
                      <td>{linha.nota ?? "—"}</td>
                      <td>{linha.revisada ? "revisada" : "pendente"}</td>
                      <td>{porcento(linha.percentual)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {placar.lista.length === 0 && <p className="hint">Nenhuma auditoria analisada ainda.</p>}
          </section>
        </>
      )}
    </>
  );
}
