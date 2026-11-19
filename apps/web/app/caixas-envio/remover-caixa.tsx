"use client";

import { useEffect, useRef, useState } from "react";

import { apiFetch, type CaixaEnvio, ErroApi } from "@/lib/api";

interface Props {
  caixa: CaixaEnvio;
  aoRemover: (id: string) => void;
  aoFechar: () => void;
}

/**
 * Confirmação antes de remover uma caixa conectada (ADR 0016): pouco reversível — perde o token e precisa
 * reconectar pelo Google de novo. Mesmo padrão acessível de `rejeitar-toque.tsx` (foco preso, Esc fecha).
 */
export function RemoverCaixa({ caixa, aoRemover, aoFechar }: Props) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [erro, setErro] = useState("");
  const [removendo, setRemovendo] = useState(false);

  useEffect(() => {
    const d = dialogo.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);

  async function confirmar() {
    if (removendo) return;
    setRemovendo(true);
    setErro("");
    try {
      await apiFetch<void>(`/caixas-envio/${caixa.id}`, { method: "DELETE" });
      aoRemover(caixa.id);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível remover a caixa.");
      setRemovendo(false);
    }
  }

  return (
    <dialog
      ref={dialogo}
      className="dialogo"
      aria-labelledby="titulo-remover-caixa"
      onCancel={(e) => {
        e.preventDefault();
        aoFechar();
      }}
    >
      <h2 id="titulo-remover-caixa" style={{ marginTop: 0 }}>
        Remover {caixa.email}?
      </h2>
      <p>
        O Mensageiro para de usar esta caixa no rodízio de envio. Para voltar a usá-la é preciso conectar de
        novo pelo Google.
      </p>
      <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>
      <div className="row" style={{ marginTop: "1rem" }}>
        <button type="button" aria-disabled={removendo} onClick={confirmar}>
          Remover
        </button>
        <button type="button" className="secundario" onClick={aoFechar}>
          Cancelar
        </button>
      </div>
    </dialog>
  );
}
