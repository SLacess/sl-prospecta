"use client";

import { ClipboardCheck, Inbox, Layers, Send, Settings, Target, Users } from "lucide-react";
import { usePathname } from "next/navigation";

import { BarraOperacao } from "./barra-operacao";
import { NavSessao } from "./nav-sessao";

const ITENS_NAV = [
  { href: "/", rotulo: "Prospecção", Icone: Target },
  { href: "/crm", rotulo: "CRM", Icone: Users },
  { href: "/caixa-aprovacao", rotulo: "Caixa de Aprovação", Icone: Inbox },
  { href: "/caixas-envio", rotulo: "Caixas de envio", Icone: Send },
  { href: "/lotes", rotulo: "Lotes", Icone: Layers },
  { href: "/revisao", rotulo: "Revisão da Fase 1", Icone: ClipboardCheck },
  { href: "/configuracoes", rotulo: "Configurações", Icone: Settings },
];

/**
 * Barra lateral (substitui o antigo menu de topo em todas as telas) + `BarraOperacao`. A tela de
 * `/login` não tem sessão ainda, então não faz sentido mostrar a navegação nem o botão "Pausar tudo" —
 * ela só renderiza o próprio conteúdo.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login") {
    return (
      <main id="conteudo" tabIndex={-1}>
        {children}
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <p className="sidebar-marca">
          SL Prospecta
          <span>Sinal Link Acessibilidade</span>
        </p>
        <nav className="sidebar-nav" aria-label="Navegação principal">
          <ul>
            {ITENS_NAV.map(({ href, rotulo, Icone }) => {
              const ativo = href === "/" ? pathname === "/" : pathname?.startsWith(href);
              return (
                <li key={href}>
                  <a href={href} aria-current={ativo ? "page" : undefined}>
                    <Icone size={18} aria-hidden="true" />
                    {rotulo}
                  </a>
                </li>
              );
            })}
          </ul>
        </nav>
        <p className="sidebar-sessao">
          <NavSessao />
        </p>
        <p className="sidebar-rodape">SL Prospecta v0.3 · Fase 3 — Abordagem com aprovação humana</p>
      </aside>

      <div className="app-conteudo">
        <BarraOperacao />
        <main id="conteudo" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
