"use client";

import { type KeyboardEvent, useEffect, useState } from "react";

import { apiFetch, ErroApi, type ItemCaixaAprovacao } from "@/lib/api";

import { RejeitarToque } from "./rejeitar-toque";

const ROTULO_ANGULO: Record<string, string> = {
  experiencia_cliente: "Experiência do cliente",
  inclusao_colaboradores_pcd: "Inclusão de colaboradores PcD",
  esg_reputacao: "ESG / reputação",
  conformidade_legal: "Conformidade legal",
  conversao_alcance_mercado: "Conversão e alcance de mercado",
};

interface Props {
  item: ItemCaixaAprovacao;
  aoAtualizar: (item: ItemCaixaAprovacao) => void;
}

function campoDeTexto(alvo: EventTarget): boolean {
  return alvo instanceof HTMLInputElement || alvo instanceof HTMLTextAreaElement;
}

/**
 * Um cartão da Caixa de Aprovação (CONSTITUICAO §12.1, item 4): edição em linha do texto do Redator,
 * aprovar, rejeitar com motivo, e marcar como enviada manualmente (fallback para quando não há caixa
 * conectada, ou o Mensageiro ainda não rodou). Depois de aprovado, mostra o resultado do Guardião (ADR
 * 0016) — bloqueado, o Mensageiro não envia; aprovado, tenta enviar na próxima rodada do worker.
 */
export function ItemCaixa({ item, aoAtualizar }: Props) {
  const [assunto, setAssunto] = useState(item.assunto_final ?? item.assunto);
  const [corpo, setCorpo] = useState(item.corpo_final ?? item.corpo);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [rejeitando, setRejeitando] = useState(false);

  useEffect(() => {
    setAssunto(item.assunto_final ?? item.assunto);
    setCorpo(item.corpo_final ?? item.corpo);
  }, [item.toque_id, item.assunto_final, item.corpo_final]);

  const travado = item.enviado_em !== null;

  async function aprovar() {
    if (enviando || travado) return;
    setEnviando(true);
    setErro("");
    try {
      const atualizado = await apiFetch<ItemCaixaAprovacao>(`/toques/${item.toque_id}/aprovar`, {
        method: "POST",
        body: JSON.stringify({ assunto, corpo }),
      });
      aoAtualizar(atualizado);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível aprovar.");
    } finally {
      setEnviando(false);
    }
  }

  async function marcarEnviado() {
    if (enviando || travado || item.decisao_humana !== "aprovado") return;
    setEnviando(true);
    setErro("");
    try {
      const atualizado = await apiFetch<ItemCaixaAprovacao>(`/toques/${item.toque_id}/enviado`, {
        method: "POST",
      });
      aoAtualizar(atualizado);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível marcar como enviada.");
    } finally {
      setEnviando(false);
    }
  }

  function aoTeclar(e: KeyboardEvent<HTMLElement>) {
    if (campoDeTexto(e.target) || enviando) return;
    if (e.key === "a" || e.key === "A") {
      e.preventDefault();
      void aprovar();
    } else if ((e.key === "r" || e.key === "R") && !travado) {
      e.preventDefault();
      setRejeitando(true);
    } else if ((e.key === "s" || e.key === "S") && item.decisao_humana === "aprovado" && !travado) {
      e.preventDefault();
      void marcarEnviado();
    }
  }

  return (
    <article
      className="card cartao-caixa"
      aria-labelledby={`titulo-caixa-${item.toque_id}`}
      style={{ marginTop: "1.2rem" }}
      onKeyDown={aoTeclar}
    >
      <h3 id={`titulo-caixa-${item.toque_id}`} style={{ marginTop: 0 }}>
        {item.contato_nome}{" "}
        <span className="hint" style={{ fontWeight: 400 }}>
          ({item.contato_area}) · {item.empresa_nome}
        </span>
      </h3>
      <p className="hint" style={{ margin: "0 0 0.6rem" }}>
        Ângulo: {ROTULO_ANGULO[item.angulo] ?? item.angulo} · Gancho: {item.achado_titulo}
      </p>
      <p style={{ margin: "0 0 0.8rem" }}>
        <span className={`pill ${item.aprovado_critico ? "verde" : "morno"}`}>
          Crítico: nota {item.nota ?? "—"}/10{item.aprovado_critico ? "" : " · não aprovou"}
        </span>
        {!item.aprovado_critico && item.motivo_critico && (
          <span className="hint"> — {item.motivo_critico}</span>
        )}
      </p>
      {item.decisao_humana === "aprovado" && (
        <p style={{ margin: "0 0 0.8rem" }}>
          <span
            className={`pill ${
              item.guardiao_resultado === "bloqueado"
                ? "quente"
                : item.guardiao_resultado === "aprovado"
                  ? "verde"
                  : "neutro"
            }`}
          >
            Guardião:{" "}
            {item.guardiao_resultado === "bloqueado"
              ? "bloqueou o envio"
              : item.guardiao_resultado === "aprovado"
                ? "liberou o envio"
                : "ainda não avaliou"}
          </span>
          {item.guardiao_resultado && item.guardiao_motivo && (
            <span className="hint"> — {item.guardiao_motivo}</span>
          )}
        </p>
      )}

      <label htmlFor={`assunto-${item.toque_id}`}>Assunto</label>
      <input
        id={`assunto-${item.toque_id}`}
        type="text"
        maxLength={200}
        value={assunto}
        disabled={travado}
        onChange={(e) => setAssunto(e.target.value)}
      />
      <label htmlFor={`corpo-${item.toque_id}`}>Corpo</label>
      <textarea
        id={`corpo-${item.toque_id}`}
        rows={6}
        value={corpo}
        disabled={travado}
        onChange={(e) => setCorpo(e.target.value)}
      />

      <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>

      {item.decisao_humana === "rejeitado" && item.motivo_rejeicao && (
        <p className="hint">Rejeitada: {item.motivo_rejeicao}</p>
      )}
      {item.decisao_humana === "aprovado" && item.percentual_editado !== null && (
        <p className="hint">
          Aprovada por {item.decidido_por_nome} — editou {item.percentual_editado}% do texto original.
        </p>
      )}
      {travado && <p className="hint">Marcada como enviada por {item.enviado_por_nome}.</p>}

      <div className="row" style={{ marginTop: "0.6rem" }}>
        <button type="button" aria-keyshortcuts="a" aria-disabled={enviando || travado} onClick={aprovar}>
          Aprovar <kbd>A</kbd>
        </button>
        <button
          type="button"
          className="secundario"
          aria-keyshortcuts="r"
          aria-disabled={travado}
          onClick={() => setRejeitando(true)}
        >
          Rejeitar <kbd>R</kbd>
        </button>
        {item.decisao_humana === "aprovado" && !travado && (
          <button
            type="button"
            className="secundario"
            aria-keyshortcuts="s"
            aria-disabled={enviando}
            onClick={marcarEnviado}
          >
            Marcar como enviada <kbd>S</kbd>
          </button>
        )}
      </div>

      {rejeitando && (
        <RejeitarToque
          item={item}
          aoRejeitar={(atualizado) => {
            setRejeitando(false);
            aoAtualizar(atualizado);
          }}
          aoFechar={() => setRejeitando(false)}
        />
      )}
    </article>
  );
}
