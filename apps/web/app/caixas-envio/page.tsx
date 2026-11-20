"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, type CaixaEnvio, ErroApi, lerToken, type UsuarioAtual } from "@/lib/api";

import { RemoverCaixa } from "./remover-caixa";

/**
 * Caixas de envio conectadas (CONSTITUICAO §9, §15.2; ADR 0016 — retomada da Fase 3, Tarefa 4): conectar
 * uma caixa pelo Google (OAuth), ver status, ativar/desativar/remover. O Mensageiro usa as caixas ativas
 * em rodízio quando alguém roda `python -m slp_workers.cli enviar` no worker (Tarefa 3).
 */
export default function CaixasEnvio() {
  const [usuario, setUsuario] = useState<UsuarioAtual | null>(null);
  const [caixas, setCaixas] = useState<CaixaEnvio[] | null>(null);
  const [erro, setErro] = useState("");
  const [anuncio, setAnuncio] = useState("");
  const [conectando, setConectando] = useState(false);
  const [paraRemover, setParaRemover] = useState<CaixaEnvio | null>(null);

  const carregar = useCallback(async () => {
    try {
      setCaixas(await apiFetch<CaixaEnvio[]>("/caixas-envio"));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar as caixas de envio.");
    }
  }, []);

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    apiFetch<UsuarioAtual>("/auth/me")
      .then(setUsuario)
      .catch(() => {});
    void carregar();

    const params = new URLSearchParams(window.location.search);
    if (params.get("conectado")) setAnuncio("Caixa conectada.");
    if (params.get("erro")) setErro(params.get("erro")!);
    if (params.has("conectado") || params.has("erro")) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [carregar]);

  const admin = usuario?.papel === "admin";

  async function conectar() {
    if (conectando) return;
    setConectando(true);
    setErro("");
    try {
      const { url_autorizacao } = await apiFetch<{ url_autorizacao: string }>("/caixas-envio/conectar");
      window.location.href = url_autorizacao;
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível iniciar a conexão com o Google.");
      setConectando(false);
    }
  }

  async function alternarAtiva(caixa: CaixaEnvio) {
    try {
      const atualizada = await apiFetch<CaixaEnvio>(
        `/caixas-envio/${caixa.id}/${caixa.ativa ? "desativar" : "ativar"}`,
        { method: "POST" },
      );
      setAnuncio(`${atualizada.email} ${atualizada.ativa ? "ativada" : "desativada"}.`);
      setCaixas((atual) => atual?.map((c) => (c.id === atualizada.id ? atualizada : c)) ?? atual);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível atualizar a caixa.");
    }
  }

  function aoRemover(id: string) {
    setAnuncio("Caixa removida.");
    setParaRemover(null);
    setCaixas((atual) => atual?.filter((c) => c.id !== id) ?? atual);
  }

  return (
    <>
      <h1>Caixas de envio</h1>
      <p className="lead">
        Conecte uma caixa do Gmail para o Mensageiro usar no rodízio de envio (ADR 0016). Conectar aqui
        ainda não envia nada por si só: o Mensageiro só tenta enviar quando alguém roda o comando no
        worker, pelas caixas ativas listadas abaixo, respeitando o limite diário de cada uma.
      </p>

      <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>
        {anuncio}
      </div>
      <div role="alert" className={erro ? "status error" : undefined}>
        {erro}
      </div>

      {!admin && usuario && (
        <p className="hint">Só administradores podem conectar, ativar, desativar ou remover caixas.</p>
      )}

      {admin && (
        <div className="row" style={{ margin: "1rem 0" }}>
          <button type="button" aria-disabled={conectando} onClick={conectar}>
            {conectando ? "Abrindo o Google…" : "Conectar nova caixa"}
          </button>
        </div>
      )}

      {caixas && caixas.length === 0 && <p className="hint">Nenhuma caixa conectada ainda.</p>}

      {caixas?.map((caixa) => (
        <section key={caixa.id} className="card" aria-labelledby={`titulo-caixa-${caixa.id}`}>
          <h2 id={`titulo-caixa-${caixa.id}`} style={{ marginTop: 0 }}>
            {caixa.email}
          </h2>
          <dl className="totais-auditoria">
            <div>
              <dt>Remetente</dt>
              <dd>{caixa.nome_remetente}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{caixa.ativa ? "Ativa" : "Desativada"}</dd>
            </div>
            <div>
              <dt>Limite diário</dt>
              <dd>{caixa.limite_diario} e-mails</dd>
            </div>
          </dl>
          {caixa.erro_verificacao && (
            <p role="alert" className="status error">
              {caixa.erro_verificacao}
            </p>
          )}
          {admin && (
            <div className="row">
              <button type="button" className="secundario" onClick={() => alternarAtiva(caixa)}>
                {caixa.ativa ? "Desativar" : "Ativar"}
              </button>
              <button type="button" className="secundario" onClick={() => setParaRemover(caixa)}>
                Remover
              </button>
            </div>
          )}
        </section>
      ))}

      {paraRemover && (
        <RemoverCaixa caixa={paraRemover} aoRemover={aoRemover} aoFechar={() => setParaRemover(null)} />
      )}
    </>
  );
}
