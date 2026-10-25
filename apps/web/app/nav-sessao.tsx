"use client";

import { useEffect, useState } from "react";

import { lerToken, sair } from "@/lib/api";

/** "Entrar" ou "Sair", conforme haja sessão. Renderiza "Entrar" até o navegador confirmar o token. */
export function NavSessao() {
  const [logado, setLogado] = useState(false);

  useEffect(() => setLogado(Boolean(lerToken())), []);

  if (!logado) return <a href="/login">Entrar</a>;
  return (
    <button type="button" className="link" onClick={sair}>
      Sair
    </button>
  );
}
