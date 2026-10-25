"use client";

import { useState } from "react";

import { apiFetch, type CandidatoDominio, type Empresa, ErroApi } from "@/lib/api";

const OUTRO = "__outro__";

interface Props {
  empresaId: string;
  nome: string;
  mensagem: string;
  candidatos: CandidatoDominio[];
  aoConfirmar: (dominio: string) => void;
}

/**
 * Confirmação do site oficial quando o Pesquisador não acha um único candidato claro (CONSTITUICAO §7.2).
 * Grupo de opções com legenda; "Outro site" abre um campo de texto com rótulo próprio.
 */
export function ConfirmarSite({ empresaId, nome, mensagem, candidatos, aoConfirmar }: Props) {
  const [escolha, setEscolha] = useState(candidatos.length ? candidatos[0].dominio : OUTRO);
  const [outro, setOutro] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function aoEnviar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (enviando) return;
    const dominio = escolha === OUTRO ? outro.trim() : escolha;
    if (!dominio) {
      setErro("Digite o endereço do site oficial.");
      document.getElementById("outro-site")?.focus();
      return;
    }
    setErro("");
    setEnviando(true);
    try {
      const r = await apiFetch<Empresa>(`/empresas/${empresaId}/dominio`, {
        method: "POST",
        body: JSON.stringify({ dominio }),
      });
      aoConfirmar(r.dominio ?? dominio);
    } catch (err) {
      setErro(err instanceof ErroApi ? err.message : "Não foi possível confirmar o site.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={aoEnviar} noValidate aria-busy={enviando} className="confirmar-site">
      <fieldset>
        <legend>Qual é o site oficial de {nome}?</legend>
        <p className="hint" id="confirmar-site-dica">
          {mensagem}
        </p>
        {candidatos.map((c) => (
          <div className="opcao" key={c.dominio}>
            <input
              type="radio"
              id={`site-${c.dominio}`}
              name="site"
              value={c.dominio}
              checked={escolha === c.dominio}
              onChange={() => setEscolha(c.dominio)}
              aria-describedby="confirmar-site-dica"
            />
            <label htmlFor={`site-${c.dominio}`}>
              {c.dominio} <span className="hint">({c.nome_oficial})</span>
            </label>
            <a href={c.evidencia_url} target="_blank" rel="noopener noreferrer" className="evidencia">
              Ver fonte<span className="visually-hidden"> de {c.dominio} (abre em nova aba)</span>
            </a>
          </div>
        ))}
        <div className="opcao">
          <input
            type="radio"
            id="site-outro"
            name="site"
            value={OUTRO}
            checked={escolha === OUTRO}
            onChange={() => setEscolha(OUTRO)}
          />
          <label htmlFor="site-outro">Outro site</label>
        </div>
        {escolha === OUTRO && (
          <div className="outro-site">
            <label htmlFor="outro-site">Endereço do site oficial</label>
            <input
              id="outro-site"
              type="text"
              value={outro}
              onChange={(e) => setOutro(e.target.value)}
              placeholder="ex.: hospitalexemplo.com.br"
              autoComplete="off"
              aria-invalid={erro ? true : undefined}
              aria-describedby={erro ? "confirmar-site-erro" : undefined}
            />
          </div>
        )}
      </fieldset>
      <button type="submit" aria-disabled={enviando}>
        Confirmar site
      </button>
      <div id="confirmar-site-erro" role="alert" className={erro ? "status error" : undefined}>
        {erro}
      </div>
    </form>
  );
}
