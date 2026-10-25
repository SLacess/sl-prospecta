import type { Metadata } from "next";
import "./globals.css";

import { NavSessao } from "./nav-sessao";

export const metadata: Metadata = {
  title: "SL Prospecta — Sinal Link",
  description: "Departamento de SDR autônomo da Sinal Link Acessibilidade",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <a className="skip-link" href="#conteudo">
          Pular para o conteúdo
        </a>
        <header className="topbar">
          <div className="brand">
            SL Prospecta <span>· Sinal Link</span>
          </div>
          <nav aria-label="Navegação principal">
            <ul>
              <li><a href="/" aria-current="page">Prospecção</a></li>
              <li><NavSessao /></li>
            </ul>
          </nav>
        </header>
        <main id="conteudo" tabIndex={-1}>
          {children}
        </main>
        <footer className="hint" style={{ textAlign: "center", padding: "2rem 1rem" }}>
          SL Prospecta v0.2 · Fase 1 — Auditor + Pesquisador
        </footer>
      </body>
    </html>
  );
}
