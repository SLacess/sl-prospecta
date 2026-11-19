"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import { apiFetch, ErroApi, type ItemCaixaAprovacao } from "@/lib/api";

interface Props {
  item: ItemCaixaAprovacao;
  aoRejeitar: (item: ItemCaixaAprovacao) => void;
  aoFechar: () => void;
}

/**
 * Rejeitar com motivo (CONSTITUICAO §12.1, item 4): o motivo "treina o Analista" (futuro, §14.3) — aqui só
 * fica salvo. Mesmo padrão acessível de `mover-estado.tsx` (foco preso, Esc fecha, motivo obrigatório).
 */
export function RejeitarToque({ item, aoRejeitar, aoFechar }: Props) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    const d = dialogo.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);

  async function aoConfirmar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    if (!motivo.trim()) {
      setErro("Explique o motivo da rejeição.");
      document.getElementById("motivo-rejeicao")?.focus();
      return;
    }
    setEnviando(true);
    setErro("");
    try {
      const atualizado = await apiFetch<ItemCaixaAprovacao>(`/toques/${item.toque_id}/rejeitar`, {
        method: "POST",
        body: JSON.stringify({ motivo: motivo.trim() }),
      });
      aoRejeitar(atualizado);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível rejeitar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <dialog
      ref={dialogo}
      className="dialogo"
      aria-labelledby="titulo-rejeitar"
      onCancel={(e) => {
        e.preventDefault();
        aoFechar();
      }}
    >
      <form onSubmit={aoConfirmar} noValidate>
        <h2 id="titulo-rejeitar" style={{ marginTop: 0 }}>
          Rejeitar mensagem para {item.contato_nome}
        </h2>
        <label htmlFor="motivo-rejeicao">Motivo (obrigatório)</label>
        <textarea
          id="motivo-rejeicao"
          rows={3}
          maxLength={2000}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          aria-invalid={erro ? true : undefined}
          aria-describedby={erro ? "erro-rejeitar" : undefined}
        />
        <div id="erro-rejeitar" role="alert" className={erro ? "status error" : undefined}>{erro}</div>
        <div className="row" style={{ marginTop: "1rem" }}>
          <button type="submit" aria-disabled={enviando}>
            Rejeitar
          </button>
          <button type="button" className="secundario" onClick={aoFechar}>
            Cancelar
          </button>
        </div>
      </form>
    </dialog>
  );
}
