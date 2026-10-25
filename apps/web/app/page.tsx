"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  apiFetch,
  type Disjuntores,
  type EmpresaDetalhe,
  ErroApi,
  lerToken,
  type ProspeccaoResposta,
  ROTULO_ESTADO,
  ROTULO_SETOR,
} from "@/lib/api";

import { AuditoriaTecnica } from "./auditoria-tecnica";
import { ConfirmarSite } from "./confirmar-site";

/** Intervalo da consulta ao andamento (ADR 0002: consulta periódica em vez de WebSocket na Fase 1). */
const INTERVALO_MS = 2000;
const LIMITE_CONSULTAS = 300; // ~10 minutos: pesquisa + auditoria técnica levam uns 2 a 3 min

/** Eventos depois dos quais não há mais novidade a esperar nesta versão do pipeline (Tarefa 4). */
const EVENTOS_DE_PARADA = new Set([
  "analise_pronta",
  "analise_falhou",
  "auditoria_bloqueada",
  "auditoria_falhou",
  "confirmacao_dominio",
  "dominio_ja_cadastrado",
  "site_indisponivel",
  "pesquisa_falhou",
  "teto_por_empresa",
  "fila_pausada_custo",
  "falha_enfileirar",
]);

function horario(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/**
 * Painel de Prospecção (CONSTITUICAO §12.1, tela 1).
 * Fase 1: a prospecção individual cadastra a empresa, o Pesquisador monta o dossiê e o painel mostra
 * o andamento ao vivo, o resumo e, quando preciso, pede a confirmação do site oficial.
 */
export default function PainelProspeccao() {
  const [anuncio, setAnuncio] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [empresaId, setEmpresaId] = useState<string | null>(null);
  // Cada rodada reinicia o acompanhamento, inclusive da mesma empresa
  const [rodada, setRodada] = useState(0);
  const [detalhe, setDetalhe] = useState<EmpresaDetalhe | null>(null);
  const [acompanhando, setAcompanhando] = useState(false);
  const [disjuntor, setDisjuntor] = useState<Disjuntores["custo"] | null>(null);

  const campoRef = useRef<HTMLInputElement>(null);
  const ultimoEventoAnunciado = useRef<string | null>(null);

  const atualizarDisjuntor = useCallback(async () => {
    try {
      const d = await apiFetch<Disjuntores>("/governanca/disjuntores");
      setDisjuntor(d.custo);
    } catch {
      /* o aviso é complementar; erros de rede aparecem no envio */
    }
  }, []);

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    void atualizarDisjuntor();
  }, [atualizarDisjuntor]);

  // Acompanhamento ao vivo da empresa enviada
  useEffect(() => {
    if (!empresaId) return;
    let ativo = true;
    let consultas = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function consultar() {
      consultas += 1;
      try {
        const d = await apiFetch<EmpresaDetalhe>(`/empresas/${empresaId}`);
        if (!ativo) return;
        setDetalhe(d);

        const ultimo = d.eventos.at(-1);
        if (ultimo && ultimo.id !== ultimoEventoAnunciado.current) {
          // Anuncia só a novidade mais recente, para o leitor de tela não repetir a lista inteira
          if (ultimoEventoAnunciado.current !== null) setAnuncio(ultimo.mensagem);
          ultimoEventoAnunciado.current = ultimo.id;
        }
        if ((ultimo && EVENTOS_DE_PARADA.has(ultimo.tipo)) || consultas >= LIMITE_CONSULTAS) {
          setAcompanhando(false);
          void atualizarDisjuntor(); // o custo do dia mudou
          return;
        }
      } catch (e) {
        if (!ativo) return;
        setErro(e instanceof ErroApi ? e.message : "Não foi possível atualizar o andamento.");
        setAcompanhando(false);
        return;
      }
      timer = setTimeout(consultar, INTERVALO_MS);
    }

    setAcompanhando(true);
    void consultar();
    return () => {
      ativo = false;
      if (timer) clearTimeout(timer);
    };
  }, [empresaId, rodada, atualizarDisjuntor]);

  /** Reinicia o acompanhamento, inclusive da mesma empresa (entrada duplicada ou site confirmado). */
  function acompanhar(id: string) {
    setEmpresaId(id);
    setRodada((r) => r + 1);
  }

  function aoConfirmarSite(dominio: string) {
    setAnuncio(`Site ${dominio} confirmado. A pesquisa continua.`);
    if (detalhe) acompanhar(detalhe.id);
  }

  async function aoProspectar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (enviando) return;
    setErro("");

    const alvo = campoRef.current?.value.trim() ?? "";
    if (!alvo) {
      setErro("Digite o nome da empresa ou o endereço do site.");
      campoRef.current?.focus();
      return;
    }

    setEnviando(true);
    setAnuncio("Enviando…");
    try {
      const r = await apiFetch<ProspeccaoResposta>("/prospeccao", {
        method: "POST",
        body: JSON.stringify({ alvo }),
      });
      setAnuncio(r.mensagem);
      if (campoRef.current) campoRef.current.value = "";
      ultimoEventoAnunciado.current = null;
      setDetalhe(null);
      acompanhar(r.empresa.id);
      if (r.fila_pausada) void atualizarDisjuntor();
    } catch (e) {
      setAnuncio("");
      setErro(e instanceof ErroApi ? e.message : "Não foi possível enviar. Tente novamente.");
    } finally {
      setEnviando(false);
      campoRef.current?.focus();
    }
  }

  return (
    <>
      <h1>Painel de Prospecção</h1>
      <p className="lead">
        Informe uma empresa e a SL Prospecta pesquisa, audita a acessibilidade do site, qualifica e prepara a
        abordagem.
      </p>

      {disjuntor?.atingido && (
        <section className="aviso" aria-labelledby="titulo-aviso-custo">
          <h2 id="titulo-aviso-custo">
            <span aria-hidden="true">⚠ </span>Fila de IA pausada
          </h2>
          <p>{disjuntor.mensagem}</p>
        </section>
      )}

      <section className="card" aria-labelledby="titulo-individual">
        <h2 id="titulo-individual" style={{ marginTop: 0 }}>Prospecção individual</h2>
        <form onSubmit={aoProspectar} noValidate aria-busy={enviando}>
          <div className="row">
            <div className="grow">
              <label htmlFor="alvo">Nome da empresa ou site</label>
              <input
                ref={campoRef}
                id="alvo"
                name="alvo"
                type="text"
                autoComplete="off"
                maxLength={500}
                placeholder="ex.: hospitalexemplo.com.br"
                aria-describedby={erro ? "alvo-dica alvo-erro" : "alvo-dica"}
                aria-invalid={erro ? true : undefined}
              />
              <p id="alvo-dica" className="hint">
                Pode ser o nome (ex.: Hospital Exemplo) ou o endereço do site.
              </p>
            </div>
            <button type="submit" aria-disabled={enviando}>
              Prospectar
            </button>
          </div>
        </form>
        <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>
          {anuncio}
        </div>
        <div id="alvo-erro" role="alert" className={erro ? "status error" : undefined}>
          {erro}
        </div>
        {disjuntor && !disjuntor.atingido && <p className="hint custo-dia">{disjuntor.mensagem}</p>}
      </section>

      {detalhe && (
        <section className="card" aria-labelledby="titulo-andamento" style={{ marginTop: "1.5rem" }}>
          <h2 id="titulo-andamento" style={{ marginTop: 0 }}>
            Andamento: {detalhe.nome}
          </h2>
          <dl className="resumo">
            <div>
              <dt>Estado</dt>
              <dd>{ROTULO_ESTADO[detalhe.estado] ?? detalhe.estado}</dd>
            </div>
            <div>
              <dt>Site</dt>
              <dd>{detalhe.dominio ?? "Ainda não identificado"}</dd>
            </div>
            {detalhe.dossie?.setor && (
              <div>
                <dt>Setor</dt>
                <dd>{ROTULO_SETOR[detalhe.dossie.setor] ?? detalhe.dossie.setor}</dd>
              </div>
            )}
          </dl>
          <p className="hint">{acompanhando ? "Atualizando automaticamente…" : "Sem novidades no momento."}</p>

          {detalhe.confirmacao_dominio && !acompanhando && (
            <ConfirmarSite
              key={detalhe.eventos.at(-1)?.id}
              empresaId={detalhe.id}
              nome={detalhe.nome}
              mensagem={detalhe.confirmacao_dominio.mensagem}
              candidatos={detalhe.confirmacao_dominio.candidatos}
              aoConfirmar={aoConfirmarSite}
            />
          )}

          {detalhe.dossie && (
            <>
              <h3>Resumo da pesquisa</h3>
              <ul className="resumo-dossie">
                {detalhe.dossie.resumo.map((linha, i) => (
                  <li key={i}>{linha}</li>
                ))}
              </ul>
              <p className="hint">
                Gerado com apoio de IA a partir das páginas públicas do site. Confira antes de usar com o cliente.
              </p>
            </>
          )}

          {detalhe.auditoria && <AuditoriaTecnica auditoria={detalhe.auditoria} />}
          <h3>Linha do tempo</h3>
          <ol className="linha-do-tempo">
            {detalhe.eventos.map((ev) => (
              <li key={ev.id}>
                <time dateTime={ev.ocorrido_em}>{horario(ev.ocorrido_em)}</time>
                <span>{ev.mensagem}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="card" aria-labelledby="titulo-lote" style={{ marginTop: "1.5rem" }}>
        <h2 id="titulo-lote" style={{ marginTop: 0 }}>Prospecção em lote</h2>
        <label htmlFor="planilha">Planilha de empresas (.xlsx ou .csv)</label>
        <input id="planilha" type="file" accept=".xlsx,.csv" aria-describedby="planilha-dica" disabled />
        <p id="planilha-dica" className="hint">
          Disponível na Fase 2. A IA vai identificar as colunas sozinha e mostrar uma prévia antes de processar.
        </p>
      </section>

      <h2>Funil</h2>
      <div className="grid" role="list" aria-label="Indicadores do funil">
        {["Prospects", "Qualificados", "Abordados", "Reuniões"].map((rotulo) => (
          <div key={rotulo} className="card" role="listitem">
            <div className="hint">{rotulo}</div>
            <div style={{ fontSize: "1.6rem", fontWeight: 700 }}>0</div>
          </div>
        ))}
      </div>
    </>
  );
}
