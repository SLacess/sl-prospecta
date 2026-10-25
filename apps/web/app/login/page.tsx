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
    <>
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
    </>
  );
}
