"use client";

import { type DragEvent, type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  apiFetch,
  type CartaoCRM,
  type ColunaCRM,
  ErroApi,
  type EstadoProspect,
  lerToken,
  type QuadroCRM,
  ROTULO_SETOR,
  type UsuarioAtual,
} from "@/lib/api";

import { MoverEstado } from "../mover-estado";

interface Filtros {
  busca: string;
  setor: string;
  faixa: string;
  minhas: boolean;
}

interface Movimento {
  cartao: CartaoCRM;
  destino: EstadoProspect | null;
}

function focarCartao(id: string) {
  // Depois de mover, o foco volta para o botão do cartão, já na coluna nova
  requestAnimationFrame(() => document.getElementById(`mover-${id}`)?.focus());
}

/**
 * CRM Kanban (CONSTITUICAO §12.1, item 2): colunas = estados do §7.1. Arrastar com o mouse ou usar
 * "Mover…" (teclado e um clique) faz a mudança manual de estado, registrada na linha do tempo (ADR 0011).
 */
export default function Crm() {
  const [quadro, setQuadro] = useState<QuadroCRM | null>(null);
  const [usuario, setUsuario] = useState<UsuarioAtual | null>(null);
  const [filtros, setFiltros] = useState<Filtros>({ busca: "", setor: "", faixa: "", minhas: false });
  const [aplicados, setAplicados] = useState<Filtros>(filtros);
  const [movimento, setMovimento] = useState<Movimento | null>(null);
  const [arrastando, setArrastando] = useState<CartaoCRM | null>(null);
  // O cartão arrastado também fica numa ref: os eventos de arrastar chegam antes de o React redesenhar
  const arrastado = useRef<CartaoCRM | null>(null);
  const [sobre, setSobre] = useState<EstadoProspect | null>(null);
  const [anuncio, setAnuncio] = useState("");
  const [erro, setErro] = useState("");

  const carregar = useCallback(async (f: Filtros) => {
    const params = new URLSearchParams();
    if (f.busca.trim()) params.set("busca", f.busca.trim());
    if (f.setor) params.set("setor", f.setor);
    if (f.faixa) params.set("faixa", f.faixa);
    if (f.minhas) params.set("minhas", "true");
    try {
      const q = await apiFetch<QuadroCRM>(`/crm/quadro${params.size ? `?${params}` : ""}`);
      setQuadro(q);
      return q;
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar o quadro.");
      return null;
    }
  }, []);

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    void carregar(aplicados);
    apiFetch<UsuarioAtual>("/auth/me")
      .then(setUsuario)
      .catch(() => setUsuario(null));
  }, [carregar, aplicados]);

  const podeMover = usuario?.papel === "admin" || usuario?.papel === "vendedor";

  function aoFiltrar(e: FormEvent) {
    e.preventDefault();
    setAplicados(filtros);
  }

  async function aoMover(cartao: CartaoCRM, nome: string, rotuloDestino: string) {
    setMovimento(null);
    setErro("");
    setAnuncio(`${nome} movido para ${rotuloDestino}.`);
    await carregar(aplicados);
    focarCartao(cartao.id);
  }

  async function moverDireto(cartao: CartaoCRM, destino: EstadoProspect) {
    const alvo = cartao.destinos.find((d) => d.estado === destino);
    if (!alvo) {
      setErro(`Não é possível mover ${cartao.nome} para essa coluna à mão.`);
      return;
    }
    if (alvo.motivo_obrigatorio) {
      setMovimento({ cartao, destino }); // pede o motivo no diálogo
      return;
    }
    try {
      const novo = await apiFetch<CartaoCRM>(`/empresas/${cartao.id}/estado`, {
        method: "POST",
        body: JSON.stringify({ origem: cartao.estado, destino, motivo: null }),
      });
      await aoMover(novo, cartao.nome, alvo.rotulo);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível mudar o estado.");
      void carregar(aplicados);
    }
  }

  function aoSoltar(e: DragEvent<HTMLElement>, coluna: ColunaCRM) {
    e.preventDefault();
    setSobre(null);
    const cartao = arrastado.current;
    arrastado.current = null;
    setArrastando(null);
    if (cartao && cartao.estado !== coluna.estado) void moverDireto(cartao, coluna.estado);
  }

  return (
    <>
      <h1>CRM</h1>
      <p className="lead">
        Cada coluna é uma etapa do funil. Arraste um cartão ou use “Mover…” para mudar a etapa à mão; a mudança
        fica registrada na linha do tempo da empresa.
      </p>

      <form className="card filtros-crm" onSubmit={aoFiltrar} aria-label="Filtros do quadro">
        <div>
          <label htmlFor="filtro-busca">Buscar</label>
          <input
            id="filtro-busca"
            type="text"
            placeholder="nome ou site"
            value={filtros.busca}
            onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })}
          />
        </div>
        <div>
          <label htmlFor="filtro-setor">Setor</label>
          <select
            id="filtro-setor"
            value={filtros.setor}
            onChange={(e) => setFiltros({ ...filtros, setor: e.target.value })}
          >
            <option value="">Todos</option>
            {Object.entries(ROTULO_SETOR).map(([valor, rotulo]) => (
              <option key={valor} value={valor}>
                {rotulo}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="filtro-faixa">Faixa do score</label>
          <select
            id="filtro-faixa"
            value={filtros.faixa}
            onChange={(e) => setFiltros({ ...filtros, faixa: e.target.value })}
          >
            <option value="">Todas</option>
            <option value="quente">Quente</option>
            <option value="morno">Morno</option>
            <option value="frio">Frio</option>
          </select>
        </div>
        <div className="checagem-honestidade">
          <input
            id="filtro-minhas"
            type="checkbox"
            checked={filtros.minhas}
            onChange={(e) => setFiltros({ ...filtros, minhas: e.target.checked })}
          />
          <label htmlFor="filtro-minhas">Só as minhas</label>
        </div>
        <button type="submit">Filtrar</button>
      </form>

      <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>{anuncio}</div>
      <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>

      {quadro && (
        <>
          <p className="hint">{quadro.total} empresa(s) no quadro.</p>
          <div className="quadro" role="region" aria-label="Quadro do funil" tabIndex={0}>
            {quadro.colunas.map((col) => {
              const recolhida = col.fase_3 && col.total === 0;
              const aceita = arrastando?.destinos.some((d) => d.estado === col.estado) ?? false;
              return (
                <section
                  key={col.estado}
                  className={[
                    "coluna-crm",
                    recolhida ? "recolhida" : "",
                    sobre === col.estado ? (aceita ? "alvo-ok" : "alvo-nao") : "",
                  ].join(" ")}
                  aria-labelledby={`coluna-${col.estado}`}
                  onDragOver={(e) => {
                    if (!arrastado.current) return;
                    e.preventDefault();
                    e.dataTransfer.dropEffect = "move";
                    if (sobre !== col.estado) setSobre(col.estado);
                  }}
                  onDragLeave={() => setSobre(null)}
                  onDrop={(e) => aoSoltar(e, col)}
                >
                  <h2 id={`coluna-${col.estado}`}>
                    {col.rotulo} <span className="contagem">({col.total})</span>
                  </h2>
                  {recolhida ? (
                    <p className="hint">Usada na Fase 3 (abordagem).</p>
                  ) : col.cartoes.length === 0 ? (
                    <p className="hint">Nenhuma empresa.</p>
                  ) : (
                    <ol className="cartoes">
                      {col.cartoes.map((c) => (
                        <li key={c.id}>
                          <article
                            className={`cartao-crm faixa-${c.faixa ?? "sem"}`}
                            aria-labelledby={`nome-${c.id}`}
                            draggable={podeMover && c.destinos.length > 0}
                            onDragStart={(e) => {
                              e.dataTransfer.setData("text/plain", c.id);
                              e.dataTransfer.effectAllowed = "move";
                              arrastado.current = c;
                              setArrastando(c);
                            }}
                            onDragEnd={() => {
                              arrastado.current = null;
                              setArrastando(null);
                              setSobre(null);
                            }}
                          >
                            <h3 id={`nome-${c.id}`}>
                              <a href={`/empresas/${c.id}`}>{c.nome}</a>
                            </h3>
                            {c.dominio && <p className="hint">{c.dominio}</p>}
                            <dl className="dados-cartao">
                              <div>
                                <dt>Score</dt>
                                <dd>{c.score !== null ? `${c.score} · ${c.rotulo_faixa ?? "sem faixa"}` : "—"}</dd>
                              </div>
                              <div>
                                <dt>Acessibilidade</dt>
                                <dd>{c.nota_acessibilidade !== null ? `${c.nota_acessibilidade}/100` : "—"}</dd>
                              </div>
                              <div>
                                <dt>Próximo passo</dt>
                                <dd>{c.proximo_passo}</dd>
                              </div>
                              <div>
                                <dt>Responsável</dt>
                                <dd>{c.responsavel ?? "—"}</dd>
                              </div>
                            </dl>
                            {c.problema && <p className="alerta-cartao">Precisa de atenção: {c.problema}</p>}
                            {podeMover && c.destinos.length > 0 && (
                              <button
                                type="button"
                                id={`mover-${c.id}`}
                                className="secundario"
                                onClick={() => setMovimento({ cartao: c, destino: null })}
                              >
                                Mover…<span className="visually-hidden"> {c.nome}</span>
                              </button>
                            )}
                          </article>
                        </li>
                      ))}
                    </ol>
                  )}
                  {col.total > col.cartoes.length && (
                    <p className="hint">Mostrando {col.cartoes.length} de {col.total}. Use os filtros.</p>
                  )}
                </section>
              );
            })}
          </div>
        </>
      )}

      {movimento && (
        <MoverEstado
          empresa={movimento.cartao}
          destinos={movimento.cartao.destinos}
          destinoInicial={movimento.destino}
          aoMover={(novo) => {
            const rotulo = movimento.cartao.destinos.find((d) => d.estado === novo.estado)?.rotulo ?? novo.estado;
            void aoMover(novo, movimento.cartao.nome, rotulo);
          }}
          aoConflito={(mensagem) => {
            const id = movimento.cartao.id;
            setMovimento(null);
            setErro(mensagem);
            void carregar(aplicados).then(() => focarCartao(id));
          }}
          aoFechar={() => {
            const id = movimento.cartao.id;
            setMovimento(null);
            focarCartao(id);
          }}
        />
      )}
    </>
  );
}
