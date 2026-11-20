"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, type EstadoOperacao, ErroApi, lerToken, type UsuarioAtual } from "@/lib/api";

/**
 * Botão vermelho "Pausar tudo" sempre visível no painel (CONSTITUICAO §13; ADR 0016, Tarefa 4). Pausar
 * bloqueia só o Mensageiro — a Caixa de Aprovação continua funcionando normalmente. Qualquer pessoa
 * logada pode pausar ou reportar spam (freio de emergência); só um admin retoma.
 */
export function BarraOperacao() {
  const [estado, setEstado] = useState<EstadoOperacao | null>(null);
  const [papel, setPapel] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [pausando, setPausando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    try {
      setEstado(await apiFetch<EstadoOperacao>("/operacao"));
    } catch {
      // painel sem sessão válida ainda — a própria página trata o redirect para /login
    }
  }, []);

  useEffect(() => {
    if (!lerToken()) return;
    void carregar();
    apiFetch<UsuarioAtual>("/auth/me")
      .then((u) => setPapel(u.papel))
      .catch(() => {});
  }, [carregar]);

  async function pausar() {
    const texto = motivo.trim();
    if (!texto) return;
    setErro("");
    try {
      setEstado(await apiFetch<EstadoOperacao>("/operacao/pausar", {
        method: "POST",
        body: JSON.stringify({ motivo: texto }),
      }));
      setPausando(false);
      setMotivo("");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível pausar.");
    }
  }

  async function reportarSpam() {
    setErro("");
    try {
      setEstado(await apiFetch<EstadoOperacao>("/operacao/reportar-spam", { method: "POST" }));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível reportar.");
    }
  }

  async function retomar() {
    setErro("");
    setEnviando(true);
    try {
      setEstado(await apiFetch<EstadoOperacao>("/operacao/retomar", { method: "POST" }));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível retomar.");
    } finally {
      setEnviando(false);
    }
  }

  if (!lerToken() || estado === null) return null;

  return (
    <div className={`barra-operacao ${estado.pausado ? "pausada" : ""}`}>
      {erro && (
        <p role="alert" className="status error" style={{ margin: 0 }}>
          {erro}
        </p>
      )}
      {estado.pausado ? (
        <p role="alert" style={{ margin: 0 }}>
          <strong>Operação pausada</strong> — {estado.motivo}
          {estado.pausado_por_nome && ` (por ${estado.pausado_por_nome})`}. O Mensageiro não envia nada
          enquanto durar.{" "}
          {papel === "admin" && (
            <button type="button" aria-disabled={enviando} onClick={retomar}>
              Retomar envio
            </button>
          )}
        </p>
      ) : pausando ? (
        <div className="row" style={{ alignItems: "center" }}>
          <label htmlFor="motivo-pausa" className="hint" style={{ margin: 0 }}>
            Motivo
          </label>
          <input
            id="motivo-pausa"
            type="text"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            style={{ flex: 1 }}
          />
          <button type="button" aria-disabled={!motivo.trim()} onClick={pausar}>
            Confirmar pausa
          </button>
          <button type="button" className="secundario" onClick={() => setPausando(false)}>
            Cancelar
          </button>
        </div>
      ) : (
        <div className="row" style={{ alignItems: "center" }}>
          <button type="button" className="secundario" onClick={() => setPausando(true)}>
            Pausar tudo
          </button>
          <button type="button" className="secundario" onClick={reportarSpam}>
            Reportar reclamação de spam
          </button>
        </div>
      )}
    </div>
  );
}
