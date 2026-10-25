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
  dominio: "hospitalexemplo.com.br",
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
    ocorrido_em: `2026-10-24T13:00:0${n}Z`,
  };
}

export const EVENTOS_INICIAIS = [
  evento(1, "entrada_recebida", "Empresa cadastrada a partir do site hospitalexemplo.com.br."),
  evento(2, "enfileirado", "Empresa na fila de processamento."),
];
export const EVENTOS_FINAIS = [
  ...EVENTOS_INICIAIS,
  evento(3, "processamento_iniciado", "Processamento iniciado."),
  evento(
    4,
    "aguardando_pesquisador",
    "Pronta para a pesquisa. A pesquisa automática ainda não está ativa nesta versão.",
  ),
];

interface Opcoes {
  disjuntorAtingido?: boolean;
  respostaPost?: { status: number; corpo: unknown };
  /** Linhas do tempo devolvidas a cada consulta, em ordem (a última se repete). */
  linhasDoTempo?: unknown[][];
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
  const linhas = opcoes.linhasDoTempo ?? [EVENTOS_INICIAIS, EVENTOS_FINAIS];
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
    if (url.pathname === `/empresas/${EMPRESA.id}`) {
      const eventos = linhas[Math.min(consulta, linhas.length - 1)];
      consulta += 1;
      return json(route, 200, { ...EMPRESA, eventos });
    }
    return json(route, 404, { detail: "não simulado" });
  });

  return { posts };
}
