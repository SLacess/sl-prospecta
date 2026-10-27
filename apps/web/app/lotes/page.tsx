"use client";

import { useEffect, useState } from "react";

import { apiFetch, ErroApi, lerToken, type LoteResumo } from "@/lib/api";

function data(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** Lotes enviados por planilha (CONSTITUICAO §7.2, entrada 2), do mais recente para o mais antigo. */
export default function Lotes() {
  const [lotes, setLotes] = useState<LoteResumo[] | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    apiFetch<LoteResumo[]>("/lotes")
      .then(setLotes)
      .catch((e) => setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar os lotes."));
  }, []);

  return (
    <>
      <h1>Lotes</h1>
      <p className="lead">
        Planilhas enviadas para prospecção em lote. Para enviar uma nova, use a área de envio no{" "}
        <a href="/">Painel de Prospecção</a>.
      </p>
      <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>
      {lotes && lotes.length === 0 && <p>Nenhum lote enviado ainda.</p>}
      {lotes && lotes.length > 0 && (
        <div className="tabela-rolavel" role="region" aria-labelledby="legenda-lotes" tabIndex={0}>
          <table>
            <caption id="legenda-lotes">Lotes enviados</caption>
            <thead>
              <tr>
                <th scope="col">Arquivo</th>
                <th scope="col">Enviado em</th>
                <th scope="col">Linhas</th>
                <th scope="col">Situação</th>
              </tr>
            </thead>
            <tbody>
              {lotes.map((l) => (
                <tr key={l.id}>
                  <th scope="row">
                    <a href={`/lotes/${l.id}`}>{l.nome_arquivo}</a>
                  </th>
                  <td>{data(l.criado_em)}</td>
                  <td>{l.total_linhas}</td>
                  <td>{l.rotulo_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
