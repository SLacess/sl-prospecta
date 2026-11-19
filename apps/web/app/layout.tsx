import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

import { NavSessao } from "./nav-sessao";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "SL Prospecta — Sinal Link",
  description: "Departamento de SDR autônomo da Sinal Link Acessibilidade",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={inter.variable}>
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
              <li><a href="/">Prospecção</a></li>
              <li><a href="/crm">CRM</a></li>
              <li><a href="/caixa-aprovacao">Caixa de Aprovação</a></li>
              <li><a href="/caixas-envio">Caixas de envio</a></li>
              <li><a href="/lotes">Lotes</a></li>
              <li><a href="/revisao">Revisão da Fase 1</a></li>
              <li><a href="/configuracoes">Configurações</a></li>
              <li><NavSessao /></li>
            </ul>
          </nav>
        </header>
        <main id="conteudo" tabIndex={-1}>
          {children}
        </main>
        <footer className="hint" style={{ textAlign: "center", padding: "2rem 1rem" }}>
          SL Prospecta v0.3 · Fase 3 — Abordagem com aprovação humana
        </footer>
      </body>
    </html>
  );
}
