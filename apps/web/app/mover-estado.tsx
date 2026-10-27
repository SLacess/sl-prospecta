"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import { apiFetch, type CartaoCRM, type DestinoEstado, ErroApi, type EstadoProspect, ROTULO_ESTADO } from "@/lib/api";

interface Props {
  empresa: { id: string; nome: string; estado: EstadoProspect };
  destinos: DestinoEstado[];
  destinoInicial?: EstadoProspect | null;
  aoMover: (cartao: CartaoCRM) => void;
  aoConflito?: (mensagem: string) => void;
  aoFechar: () => void;
}

/**
 * Mudança manual de estado (CONSTITUICAO §12.1 e ADR 0011). Alternativa ao arrastar, para teclado e um
 * clique só (WCAG 2.5.7): diálogo nativo com só os destinos permitidos. Esc fecha; o foco fica preso no
 * diálogo enquanto ele está aberto e volta para quem o abriu.
 */
export function MoverEstado({ empresa, destinos, destinoInicial, aoMover, aoConflito, aoFechar }: Props) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [destino, setDestino] = useState<EstadoProspect | "">(destinoInicial ?? "");
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    const d = dialogo.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);

  const escolhido = destinos.find((d) => d.estado === destino);

  async function aoConfirmar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    if (!escolhido) {
      setErro("Escolha para onde mover.");
      return;
    }
    if (escolhido.motivo_obrigatorio && !motivo.trim()) {
      setErro(`Explique o motivo para mover para ${escolhido.rotulo}.`);
      document.getElementById("motivo-mudanca")?.focus();
      return;
    }
    setEnviando(true);
    setErro("");
    try {
      const cartao = await apiFetch<CartaoCRM>(`/empresas/${empresa.id}/estado`, {
        method: "POST",
        body: JSON.stringify({ origem: empresa.estado, destino: escolhido.estado, motivo: motivo.trim() || null }),
      });
      aoMover(cartao);
    } catch (e) {
      if (e instanceof ErroApi && e.status === 409 && aoConflito) {
        aoConflito(e.message);
        return;
      }
      setErro(e instanceof ErroApi ? e.message : "Não foi possível mudar o estado.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <dialog
      ref={dialogo}
      className="dialogo"
      aria-labelledby="titulo-mover"
      onCancel={(e) => {
        e.preventDefault();
        aoFechar();
      }}
    >
      <form onSubmit={aoConfirmar} noValidate>
        <h2 id="titulo-mover" style={{ marginTop: 0 }}>
          Mover {empresa.nome}
        </h2>
        <p className="hint">Hoje em: {ROTULO_ESTADO[empresa.estado] ?? empresa.estado}.</p>
        <fieldset className="destinos-mover">
          <legend>Para onde</legend>
          {destinos.map((d) => (
            <span className="opcao" key={d.estado}>
              <input
                type="radio"
                id={`destino-${d.estado}`}
                name="destino"
                value={d.estado}
                checked={destino === d.estado}
                onChange={() => {
                  setDestino(d.estado);
                  setErro("");
                }}
              />
              <label htmlFor={`destino-${d.estado}`}>
                {d.rotulo}
                {d.motivo_obrigatorio ? " (pede motivo)" : ""}
              </label>
            </span>
          ))}
        </fieldset>
        <label htmlFor="motivo-mudanca">
          Motivo{escolhido?.motivo_obrigatorio ? " (obrigatório)" : " (opcional)"}
        </label>
        <textarea
          id="motivo-mudanca"
          rows={3}
          maxLength={1000}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          aria-invalid={erro && escolhido?.motivo_obrigatorio && !motivo.trim() ? true : undefined}
          aria-describedby={erro ? "erro-mover" : undefined}
        />
        <div id="erro-mover" role="alert" className={erro ? "status error" : undefined}>{erro}</div>
        <div className="row" style={{ marginTop: "1rem" }}>
          <button type="submit" aria-disabled={enviando}>
            Mover
          </button>
          <button type="button" className="secundario" onClick={aoFechar}>
            Cancelar
          </button>
        </div>
      </form>
    </dialog>
  );
}
