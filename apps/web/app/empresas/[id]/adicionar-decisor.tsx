"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import { apiFetch, ErroApi, type Ficha } from "@/lib/api";

const AREAS = ["TI", "RH", "D&I", "Marketing", "ESG", "Compliance"] as const;

interface Linha {
  nome: string;
  sobrenome: string;
  email: string;
  cargo: string;
  area: (typeof AREAS)[number];
}

function linhaVazia(): Linha {
  return { nome: "", sobrenome: "", email: "", cargo: "", area: "TI" };
}

interface Props {
  empresaId: string;
  aoAdicionar: (ficha: Ficha) => void;
  aoFechar: () => void;
}

/**
 * Cadastro manual de decisor (CONSTITUICAO §7.3, Etapa 4) — só aparece quando o Mapeador já tentou e não
 * achou ninguém (`ficha.permite_decisor_manual`). Mesmo padrão de diálogo de `mover-estado.tsx`: foco
 * preso enquanto aberto, Esc fecha.
 */
export function AdicionarDecisor({ empresaId, aoAdicionar, aoFechar }: Props) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [linhas, setLinhas] = useState<Linha[]>([linhaVazia()]);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    const d = dialogo.current;
    if (d && !d.open) d.showModal();
    return () => d?.close();
  }, []);

  function atualizar(indice: number, campo: keyof Linha, valor: string) {
    setLinhas((atual) =>
      atual.map((l, i) => (i === indice ? { ...l, [campo]: valor } : l)),
    );
  }

  function adicionarLinha() {
    setLinhas((atual) => [...atual, linhaVazia()]);
  }

  function removerLinha(indice: number) {
    setLinhas((atual) => atual.filter((_, i) => i !== indice));
  }

  async function aoConfirmar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    for (const l of linhas) {
      if (!l.nome.trim()) {
        setErro("Preencha pelo menos o nome de cada decisor.");
        return;
      }
    }
    setEnviando(true);
    setErro("");
    try {
      const ficha = await apiFetch<Ficha>(`/empresas/${empresaId}/decisores`, {
        method: "POST",
        body: JSON.stringify({
          decisores: linhas.map((l) => ({
            nome: l.nome.trim(),
            sobrenome: l.sobrenome.trim(),
            email: l.email.trim() || null,
            cargo: l.cargo.trim() || null,
            area: l.area,
          })),
        }),
      });
      aoAdicionar(ficha);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível salvar. Tente novamente.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <dialog ref={dialogo} aria-labelledby="titulo-decisor-manual" onClose={aoFechar}>
      <form onSubmit={aoConfirmar} noValidate aria-busy={enviando} style={{ minWidth: "min(32rem, 90vw)" }}>
        <h2 id="titulo-decisor-manual" style={{ marginTop: 0 }}>Adicionar decisor manualmente</h2>
        <p className="hint">
          Use quando a busca automática já rodou e não encontrou ninguém. Pode adicionar mais de um.
        </p>

        {linhas.map((l, i) => (
          <fieldset key={i} style={{ border: "1px solid var(--border)", borderRadius: "8px",
            padding: "0.75rem", marginBottom: "0.75rem" }}>
            <legend className="hint">Decisor {i + 1}</legend>
            <div className="row">
              <div className="grow">
                <label htmlFor={`nome-${i}`}>Nome</label>
                <input
                  id={`nome-${i}`}
                  type="text"
                  required
                  value={l.nome}
                  onChange={(e) => atualizar(i, "nome", e.target.value)}
                />
              </div>
              <div className="grow">
                <label htmlFor={`sobrenome-${i}`}>Sobrenome</label>
                <input
                  id={`sobrenome-${i}`}
                  type="text"
                  value={l.sobrenome}
                  onChange={(e) => atualizar(i, "sobrenome", e.target.value)}
                />
              </div>
            </div>
            <label htmlFor={`email-${i}`}>E-mail</label>
            <input
              id={`email-${i}`}
              type="email"
              value={l.email}
              onChange={(e) => atualizar(i, "email", e.target.value)}
            />
            <div className="row">
              <div className="grow">
                <label htmlFor={`cargo-${i}`}>Cargo</label>
                <input
                  id={`cargo-${i}`}
                  type="text"
                  value={l.cargo}
                  onChange={(e) => atualizar(i, "cargo", e.target.value)}
                />
              </div>
              <div className="grow">
                <label htmlFor={`area-${i}`}>Departamento</label>
                <select
                  id={`area-${i}`}
                  value={l.area}
                  onChange={(e) => atualizar(i, "area", e.target.value)}
                >
                  {AREAS.map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>
            </div>
            {linhas.length > 1 && (
              <button type="button" className="secundario" onClick={() => removerLinha(i)}>
                Remover este decisor
              </button>
            )}
          </fieldset>
        ))}

        <div className="row" style={{ marginBottom: "1rem" }}>
          <button type="button" className="secundario" onClick={adicionarLinha}>
            + Adicionar outro decisor
          </button>
        </div>

        <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>

        <div className="row">
          <button type="submit" aria-disabled={enviando}>
            {enviando ? "Salvando…" : "Salvar"}
          </button>
          <button type="button" className="secundario" onClick={aoFechar}>
            Cancelar
          </button>
        </div>
      </form>
    </dialog>
  );
}
