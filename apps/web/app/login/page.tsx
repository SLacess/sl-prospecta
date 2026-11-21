"use client";

import { useState } from "react";

import { API_URL, guardarToken } from "@/lib/api";

export default function Login() {
  const [erro, setErro] = useState("");
  const [status, setStatus] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function aoEntrar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErro("");
    setStatus("");
    const dados = new FormData(e.currentTarget);
    const body = new URLSearchParams({
      username: String(dados.get("email") ?? ""),
      password: String(dados.get("senha") ?? ""),
    });

    setEnviando(true);
    try {
      const r = await fetch(`${API_URL}/auth/login`, { method: "POST", body });
      if (!r.ok) {
        setErro("E-mail ou senha incorretos.");
        return;
      }
      const { access_token } = await r.json();
      // Token em sessionStorage; a migração para cookie httpOnly é tarefa própria (ADR 0002)
      guardarToken(access_token);
      setStatus("Login realizado. Redirecionando…");
      window.location.href = "/";
    } catch {
      setErro("Não foi possível conectar à API. Tente novamente.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="tela-login">
      <div className="login-painel">
        <p className="login-painel-titulo">Plataforma de Prospecção de Acessibilidade Digital</p>
        <p className="login-painel-texto">
          Pesquisa, auditoria real e abordagem com evidência — do primeiro contato até a proposta, num só
          lugar.
        </p>
        <div className="login-painel-ilustracao" aria-hidden="true">
          <svg viewBox="0 0 220 160" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="18" y="20" width="120" height="100" rx="12" fill="var(--surface)" />
            <rect x="34" y="40" width="88" height="10" rx="5" fill="var(--frio-bg)" />
            <rect x="34" y="60" width="64" height="10" rx="5" fill="var(--surface-2)" />
            <rect x="34" y="80" width="72" height="10" rx="5" fill="var(--surface-2)" />
            <path
              d="M34 100h36"
              stroke="var(--verde-fg)"
              strokeWidth="10"
              strokeLinecap="round"
            />
            <circle cx="150" cy="54" r="34" fill="var(--surface)" />
            <path
              d="M150 36v22l16 10"
              stroke="var(--primary)"
              strokeWidth="7"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
            <circle cx="150" cy="54" r="5" fill="var(--primary)" />
          </svg>
        </div>
      </div>

      <div className="login-form-col">
        <h1>Entrar</h1>
        <p className="lead">Acesso restrito à equipe Sinal Link.</p>
        <form className="card" onSubmit={aoEntrar} style={{ maxWidth: 440 }}>
          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="email">E-mail</label>
            <input id="email" name="email" type="email" autoComplete="username" required />
          </div>
          <div style={{ marginBottom: "1.25rem" }}>
            <label htmlFor="senha">Senha</label>
            <input id="senha" name="senha" type="password" autoComplete="current-password" required />
          </div>
          <button type="submit" aria-disabled={enviando}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>
          <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>
          <div role="status" aria-live="polite">{status}</div>
        </form>
      </div>
    </div>
  );
}
