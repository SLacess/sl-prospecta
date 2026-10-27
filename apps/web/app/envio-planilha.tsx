"use client";

import { type DragEvent, type FormEvent, useRef, useState } from "react";

import { enviarArquivo, ErroApi, type LoteDetalhe } from "@/lib/api";

const TIPOS = ".xlsx,.csv";

/**
 * Área de envio de planilha para prospecção em lote (CONSTITUICAO §12.1, item 1). Funciona arrastando o
 * arquivo ou pelo campo de escolher, que também é usável só com o teclado. A prévia abre em seguida.
 */
export function EnvioPlanilha() {
  const campoRef = useRef<HTMLInputElement>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [arrastando, setArrastando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [anuncio, setAnuncio] = useState("");

  function escolher(f: File | null) {
    setErro("");
    setArquivo(f);
    setAnuncio(f ? `Arquivo escolhido: ${f.name}.` : "");
  }

  function aoSoltar(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setArrastando(false);
    const f = e.dataTransfer.files?.[0];
    if (f) escolher(f);
  }

  async function aoEnviar(e: FormEvent) {
    e.preventDefault();
    if (enviando) return;
    if (!arquivo) {
      setErro("Escolha uma planilha .xlsx ou .csv.");
      campoRef.current?.focus();
      return;
    }
    setEnviando(true);
    setErro("");
    setAnuncio("Lendo a planilha…");
    try {
      const lote = await enviarArquivo<LoteDetalhe>("/lotes", "arquivo", arquivo);
      setAnuncio("Planilha lida. Abrindo a prévia…");
      window.location.assign(`/lotes/${lote.id}`);
    } catch (e) {
      setAnuncio("");
      setErro(e instanceof ErroApi ? e.message : "Não foi possível enviar a planilha.");
      campoRef.current?.focus();
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section className="card" aria-labelledby="titulo-lote" style={{ marginTop: "1.5rem" }}>
      <h2 id="titulo-lote" style={{ marginTop: 0 }}>Prospecção em lote</h2>
      <form onSubmit={aoEnviar} noValidate aria-busy={enviando}>
        <div
          className={arrastando ? "area-arquivo arrastando" : "area-arquivo"}
          onDragOver={(e) => {
            e.preventDefault();
            setArrastando(true);
          }}
          onDragLeave={() => setArrastando(false)}
          onDrop={aoSoltar}
        >
          <label htmlFor="planilha">Planilha de empresas (.xlsx ou .csv)</label>
          <input
            ref={campoRef}
            id="planilha"
            name="planilha"
            type="file"
            accept={TIPOS}
            aria-describedby={erro ? "planilha-dica planilha-erro" : "planilha-dica"}
            aria-invalid={erro ? true : undefined}
            onChange={(e) => escolher(e.target.files?.[0] ?? null)}
          />
          <p id="planilha-dica" className="hint">
            Arraste o arquivo para cá ou escolha pelo campo. Até 5 MB e 1.000 empresas; a primeira linha é o
            cabeçalho. Você confere as colunas antes de qualquer processamento.
          </p>
        </div>
        <div className="row" style={{ marginTop: "0.75rem" }}>
          <button type="submit" aria-disabled={enviando}>
            Enviar planilha
          </button>
          <a href="/lotes">Ver lotes enviados</a>
        </div>
      </form>
      <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>{anuncio}</div>
      <div id="planilha-erro" role="alert" className={erro ? "status error" : undefined}>{erro}</div>
    </section>
  );
}
