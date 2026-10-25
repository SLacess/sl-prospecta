import type { Page, Route } from "@playwright/test";

/** Simula a API no navegador para os testes do painel não dependerem do backend. */

const API = "http://localhost:8000";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "Authorization, Content-Type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

export const EMPRESA = {
  id: "11111111-1111-4111-8111-111111111111",
  nome: "hospitalexemplo.com.br",
  dominio: "hospitalexemplo.com.br" as string | null,
  estado: "NOVO",
  fonte: "manual",
  criado_em: "2026-10-24T13:00:00Z",
};

function evento(n: number, tipo: string, mensagem: string) {
  return {
    id: `e${n}`,
    tipo,
    origem: n <= 1 ? "humano" : "sistema",
    mensagem,
    ocorrido_em: `2026-10-24T13:00:${String(n).padStart(2, "0")}Z`,
  };
}

export const EVENTOS_INICIAIS = [
  evento(1, "entrada_recebida", "Empresa cadastrada a partir do site hospitalexemplo.com.br."),
  evento(2, "enfileirado", "Empresa na fila de processamento."),
];
export const EVENTOS_FINAIS = [
  ...EVENTOS_INICIAIS,
  evento(3, "pesquisa_iniciada", "Pesquisa iniciada."),
  evento(4, "lendo_pagina", "Lendo a página inicial de hospitalexemplo.com.br."),
  evento(5, "lendo_pagina", "Lendo página 2 de 3: /quem-somos"),
  evento(6, "analisando", "Analisando 3 página(s) para montar o dossiê."),
  evento(7, "dossie_pronto", "Dossiê pronto. A auditoria de acessibilidade entra na próxima versão."),
];

export const DOSSIE = {
  versao: 1,
  setor: "saude",
  resumo: [
    "Hospital geral de alta complexidade.",
    "Atende pacientes particulares e de convênios.",
    "Sede em Sorocaba (SP).",
    "Mantém programa de inclusão de pessoas com deficiência.",
    "O programa de inclusão é um bom ponto de partida para falar de acessibilidade digital.",
  ],
  criado_em: "2026-10-24T13:01:00Z",
};

/** Estado da empresa a cada consulta ao andamento. */
export interface Detalhe {
  eventos: unknown[];
  estado?: string;
  dominio?: string | null;
  nome?: string;
  dossie?: unknown;
  confirmacao_dominio?: unknown;
}

export const ANDAMENTO_PADRAO: Detalhe[] = [
  { eventos: EVENTOS_INICIAIS },
  { eventos: EVENTOS_FINAIS, estado: "PESQUISANDO", dossie: DOSSIE },
];

export const CANDIDATOS = [
  { dominio: "unimed-a.com.br", nome_oficial: "Unimed A", evidencia_url: "https://unimed-a.com.br/" },
  { dominio: "unimed-b.com.br", nome_oficial: "Unimed B", evidencia_url: "https://unimed-b.com.br/" },
];

export const ANDAMENTO_CONFIRMACAO: Detalhe[] = [
  {
    nome: "Unimed",
    dominio: null,
    estado: "PESQUISANDO",
    eventos: [
      evento(1, "entrada_recebida", "Empresa cadastrada pelo nome. O site oficial será identificado na pesquisa."),
      evento(2, "buscando_site", "Procurando o site oficial de Unimed."),
      evento(3, "confirmacao_dominio", "Encontrei 2 site(s) possível(is). Confirme qual é o oficial para continuar."),
    ],
    confirmacao_dominio: {
      mensagem: "Encontrei 2 site(s) possível(is). Confirme qual é o oficial para continuar.",
      candidatos: CANDIDATOS,
    },
  },
];

interface Opcoes {
  disjuntorAtingido?: boolean;
  respostaPost?: { status: number; corpo: unknown };
  /** Respostas do andamento, em ordem (a última se repete). */
  andamento?: Detalhe[];
  /** Andamento depois que o vendedor confirma o site. */
  andamentoDepoisDaConfirmacao?: Detalhe[];
  respostaConfirmacao?: { status: number; corpo: unknown };
}

function json(route: Route, status: number, corpo: unknown) {
  return route.fulfill({
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}

export async function prepararPainel(page: Page, opcoes: Opcoes = {}) {
  const posts: unknown[] = [];
  const confirmacoes: unknown[] = [];
  let andamento = opcoes.andamento ?? ANDAMENTO_PADRAO;
  let consulta = 0;

  await page.addInitScript(() => sessionStorage.setItem("slp_token", "token-de-teste"));

  await page.route(`${API}/**`, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });

    if (url.pathname === "/governanca/disjuntores") {
      const atingido = Boolean(opcoes.disjuntorAtingido);
      return json(route, 200, {
        custo: {
          custo_hoje_brl: atingido ? "30.00" : "4.10",
          teto_brl: "30",
          atingido,
          mensagem: atingido
            ? "Teto diário de IA atingido (R$ 30,00 de R$ 30,00). " +
              "Novas empresas ficam na fila e o processamento recomeça amanhã."
            : "Custo de IA hoje: R$ 4,10 de R$ 30,00.",
        },
      });
    }
    if (url.pathname === "/prospeccao" && req.method() === "POST") {
      posts.push(req.postDataJSON());
      const r = opcoes.respostaPost ?? {
        status: 201,
        corpo: {
          empresa: EMPRESA,
          duplicada: false,
          na_fila: true,
          fila_pausada: false,
          mensagem: "Empresa cadastrada. Processamento na fila.",
        },
      };
      return json(route, r.status, r.corpo);
    }
    if (url.pathname === `/empresas/${EMPRESA.id}/dominio` && req.method() === "POST") {
      confirmacoes.push(req.postDataJSON());
      const r = opcoes.respostaConfirmacao ?? {
        status: 200,
        corpo: { ...EMPRESA, nome: "Unimed", dominio: "unimed-b.com.br", estado: "PESQUISANDO" },
      };
      if (r.status === 200 && opcoes.andamentoDepoisDaConfirmacao) {
        andamento = opcoes.andamentoDepoisDaConfirmacao;
        consulta = 0;
      }
      return json(route, r.status, r.corpo);
    }
    if (url.pathname === `/empresas/${EMPRESA.id}`) {
      const atual = andamento[Math.min(consulta, andamento.length - 1)];
      consulta += 1;
      return json(route, 200, { ...EMPRESA, dossie: null, confirmacao_dominio: null, ...atual });
    }
    return json(route, 404, { detail: "não simulado" });
  });

  return { posts, confirmacoes };
}
