"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, ErroApi, lerToken, type LoteDetalhe, ROTULO_ESTADO, type UsuarioAtual } from "@/lib/api";

const INTERVALO_MAPEANDO_MS = 2000;
const INTERVALO_PROCESSANDO_MS = 5000;

const ORIGEM: Record<string, string> = {
  regras: "pelo nome das colunas",
  ia: "pela IA, a partir dos cabeçalhos e de alguns exemplos",
  humano: "por você",
};

/**
 * Lote por planilha (CONSTITUICAO §7.2 e §12.1): prévia com o mapeamento de colunas e a deduplicação,
 * confirmação e, depois, o progresso das empresas. Nada é processado antes da confirmação.
 */
export default function DetalheDoLote() {
  const { id } = useParams<{ id: string }>();
  const [lote, setLote] = useState<LoteDetalhe | null>(null);
  const [usuario, setUsuario] = useState<UsuarioAtual | null>(null);
  const [mapa, setMapa] = useState<Record<string, string>>({});
  const [erro, setErro] = useState("");
  const [anuncio, setAnuncio] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const statusAnterior = useRef<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const l = await apiFetch<LoteDetalhe>(`/lotes/${id}`);
      setLote(l);
      if (statusAnterior.current !== l.status) {
        setMapa(Object.fromEntries(l.campos.map((c) => [c.campo, c.coluna === null ? "" : String(c.coluna)])));
        if (statusAnterior.current === "mapeando" && l.status === "aguardando_confirmacao") {
          setAnuncio("Colunas identificadas. Confira a prévia antes de confirmar.");
        }
        statusAnterior.current = l.status;
      }
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar o lote.");
    }
  }, [id]);

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    void carregar();
    apiFetch<UsuarioAtual>("/auth/me")
      .then(setUsuario)
      .catch(() => setUsuario(null));
  }, [carregar]);

  // Consulta periódica enquanto há algo acontecendo (mesma abordagem do andamento individual, ADR 0002)
  useEffect(() => {
    if (!lote || (lote.status !== "mapeando" && lote.status !== "processando")) return;
    const espera = lote.status === "mapeando" ? INTERVALO_MAPEANDO_MS : INTERVALO_PROCESSANDO_MS;
    const t = setTimeout(() => void carregar(), espera);
    return () => clearTimeout(t);
  }, [lote, carregar]);

  const podeEditar = usuario?.papel === "admin" || usuario?.papel === "vendedor";

  async function aplicarColunas() {
    if (!lote || ocupado) return;
    setOcupado(true);
    setErro("");
    try {
      const mapeamento = Object.fromEntries(
        Object.entries(mapa).map(([campo, v]) => [campo, v === "" ? null : Number(v)]),
      );
      const l = await apiFetch<LoteDetalhe>(`/lotes/${id}/mapeamento`, {
        method: "PUT",
        body: JSON.stringify({ mapeamento }),
      });
      setLote(l);
      statusAnterior.current = l.status;
      setAnuncio("Colunas atualizadas. A prévia abaixo foi refeita.");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível atualizar as colunas.");
    } finally {
      setOcupado(false);
    }
  }

  async function acao(caminho: "confirmar" | "cancelar", mensagem: string) {
    if (ocupado) return;
    setOcupado(true);
    setErro("");
    try {
      const l = await apiFetch<LoteDetalhe>(`/lotes/${id}/${caminho}`, { method: "POST" });
      setLote(l);
      statusAnterior.current = l.status;
      setAnuncio(mensagem);
      document.getElementById("titulo-lote")?.focus();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível concluir a ação.");
      void carregar();
    } finally {
      setOcupado(false);
    }
  }

  if (!lote) {
    return (
      <>
        <h1>Lote</h1>
        <div role="status" aria-live="polite">{erro ? "" : "Carregando…"}</div>
        <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>
      </>
    );
  }

  const r = lote.resumo;
  return (
    <>
      <p>
        <a href="/lotes">← Voltar aos lotes</a>
      </p>
      <h1 id="titulo-lote" tabIndex={-1}>
        Lote: {lote.nome_arquivo}
      </h1>
      <p className="situacao">
        <strong>{lote.rotulo_status}.</strong> {lote.total_linhas} linha(s) com dados.
      </p>
      <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>{anuncio}</div>
      <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>

      {lote.status === "mapeando" && (
        <p aria-busy="true">Identificando as colunas da planilha… A prévia aparece aqui em instantes.</p>
      )}

      {lote.status === "aguardando_confirmacao" && (
        <>
          <section className="card" aria-labelledby="titulo-colunas" style={{ marginTop: "1.5rem" }}>
            <h2 id="titulo-colunas" style={{ marginTop: 0 }}>Colunas</h2>
            <p className="hint">
              Identificadas {ORIGEM[lote.mapeamento_origem] ?? lote.mapeamento_origem}. Ajuste o que estiver
              errado; é preciso pelo menos a coluna da empresa ou a do site.
            </p>
            {lote.aviso_mapeamento && <p className="situacao">{lote.aviso_mapeamento}</p>}
            <div className="campos-lote">
              {lote.campos.map((c) => (
                <div key={c.campo}>
                  <label htmlFor={`campo-${c.campo}`}>{c.rotulo}</label>
                  <select
                    id={`campo-${c.campo}`}
                    value={mapa[c.campo] ?? ""}
                    disabled={!podeEditar}
                    onChange={(e) => setMapa({ ...mapa, [c.campo]: e.target.value })}
                  >
                    <option value="">— não usar —</option>
                    {lote.colunas.map((col) => (
                      <option key={col.indice} value={String(col.indice)}>
                        {col.cabecalho}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
            {podeEditar && (
              <div className="row" style={{ marginTop: "1rem" }}>
                <button type="button" className="secundario" onClick={aplicarColunas} aria-disabled={ocupado}>
                  Atualizar prévia
                </button>
              </div>
            )}
          </section>

          {r && (
            <section className="card" aria-labelledby="titulo-previa" style={{ marginTop: "1.5rem" }}>
              <h2 id="titulo-previa" style={{ marginTop: 0 }}>Prévia</h2>
              <dl className="totais-auditoria">
                <div>
                  <dt>Novas</dt>
                  <dd>{r.novas}</dd>
                </div>
                <div>
                  <dt>Já cadastradas</dt>
                  <dd>{r.ja_cadastradas}</dd>
                </div>
                <div>
                  <dt>Repetidas na planilha</dt>
                  <dd>{r.repetidas}</dd>
                </div>
                <div>
                  <dt>Inválidas</dt>
                  <dd>{r.invalidas}</dd>
                </div>
              </dl>
              {r.com_avisos > 0 && (
                <p className="hint">
                  {r.com_avisos} linha(s) com aviso: o dado com problema é ignorado e a empresa entra assim mesmo.
                </p>
              )}
              <div className="tabela-rolavel" role="region" aria-labelledby="legenda-previa" tabIndex={0}>
                <table>
                  <caption id="legenda-previa">Primeiras {lote.previa.length} linhas como vão entrar</caption>
                  <thead>
                    <tr>
                      <th scope="col">Linha</th>
                      <th scope="col">Empresa</th>
                      <th scope="col">Site</th>
                      <th scope="col">CNPJ</th>
                      <th scope="col">Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lote.previa.map((p) => (
                      <tr key={p.numero}>
                        <th scope="row">{p.numero}</th>
                        <td>{p.empresa ?? "—"}</td>
                        <td>{p.site ?? "—"}</td>
                        <td>{p.cnpj ?? "—"}</td>
                        <td className={`situacao-linha situacao-${p.situacao}`}>
                          {p.rotulo_situacao}
                          {p.motivo ? `: ${p.motivo}` : ""}
                          {p.avisos.length > 0 ? ` (aviso: ${p.avisos.join("; ")})` : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {lote.estimativa && <p>{lote.estimativa.texto}</p>}
              {podeEditar && (
                <div className="row" style={{ marginTop: "1rem" }}>
                  <button
                    type="button"
                    onClick={() =>
                      acao("confirmar", `Lote confirmado: ${r.novas} empresa(s) na fila de processamento.`)
                    }
                    aria-disabled={ocupado || r.novas === 0}
                    disabled={r.novas === 0}
                  >
                    Confirmar e processar {r.novas} empresa(s)
                  </button>
                  <button
                    type="button"
                    className="secundario"
                    onClick={() => acao("cancelar", "Lote cancelado. Nenhuma empresa foi cadastrada.")}
                    aria-disabled={ocupado}
                  >
                    Cancelar lote
                  </button>
                </div>
              )}
            </section>
          )}
        </>
      )}

      {lote.progresso && (
        <section className="card" aria-labelledby="titulo-progresso" style={{ marginTop: "1.5rem" }}>
          <h2 id="titulo-progresso" style={{ marginTop: 0 }}>Progresso</h2>
          <label htmlFor="progresso-lote">{lote.progresso.texto}</label>
          <progress
            id="progresso-lote"
            className="progresso-lote"
            max={100}
            value={lote.progresso.percentual}
          >
            {lote.progresso.percentual}%
          </progress>
          <dl className="totais-auditoria">
            {lote.progresso.etapas.map((e) => (
              <div key={e.chave}>
                <dt>{e.rotulo}</dt>
                <dd>{e.quantidade}</dd>
              </div>
            ))}
          </dl>
          <div className="tabela-rolavel" role="region" aria-labelledby="legenda-empresas-lote" tabIndex={0}>
            <table>
              <caption id="legenda-empresas-lote">Empresas do lote</caption>
              <thead>
                <tr>
                  <th scope="col">Empresa</th>
                  <th scope="col">Site</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Score</th>
                  <th scope="col">Atenção</th>
                </tr>
              </thead>
              <tbody>
                {lote.empresas.map((e) => (
                  <tr key={e.id}>
                    <th scope="row">
                      <a href={`/empresas/${e.id}`}>{e.nome}</a>
                    </th>
                    <td>{e.dominio ?? "a identificar"}</td>
                    <td>{ROTULO_ESTADO[e.estado] ?? e.estado}</td>
                    <td>{e.score ?? "—"}</td>
                    <td>{e.problema ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {lote.status === "cancelado" && <p>Este lote foi cancelado; nenhuma empresa foi cadastrada.</p>}

      {lote.linhas_ignoradas.length > 0 && (
        <details style={{ marginTop: "1.5rem" }}>
          <summary>Linhas que não viraram empresas novas ({lote.linhas_ignoradas.length})</summary>
          <ul>
            {lote.linhas_ignoradas.map((l) => (
              <li key={l.linha}>
                Linha {l.linha}: {l.motivo ?? "não cadastrada"}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
