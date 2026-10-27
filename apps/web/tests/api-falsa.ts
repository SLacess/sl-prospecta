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
  evento(7, "dossie_pronto", "Dossiê pronto."),
  evento(8, "auditoria_enfileirada", "Na fila da auditoria técnica de acessibilidade."),
  evento(9, "auditoria_iniciada", "Auditoria técnica de hospitalexemplo.com.br iniciada."),
  evento(10, "auditando_pagina", "Auditando hospitalexemplo.com.br — página 1 de 3: /"),
  evento(
    11,
    "auditoria_pronta",
    "Auditoria técnica pronta: 2 página(s) testada(s); problemas automáticos: 2 crítico(s), 1 grave(s), " +
      "0 moderado(s), 0 leve(s). Plugin de acessibilidade detectado: UserWay. " +
      "Em seguida vem a análise com a nota e os achados explicados.",
  ),
  evento(12, "analisando_auditoria", "Analisando a auditoria para explicar os achados."),
  evento(13, "analise_pronta", "Análise pronta: nota 58 de 100, com 2 achado(s) explicado(s) para leigos."),
  evento(14, "relatorio_pronto", "Mini-relatório em PDF pronto para baixar na ficha da empresa."),
];

export const ANALISE = {
  top3_para_leigos: [
    {
      titulo: "Formulário de contato não diz para quem usa leitor de tela o que cada campo pede",
      impacto_humano: "Uma pessoa cega não consegue saber onde digitar nome, e-mail ou mensagem.",
      quem_e_afetado: ["pessoas cegas", "pessoas com baixa visão"],
      criterio_wcag: "1.3.1 / 4.1.2",
      pagina: "/contato",
      trecho_html: '<input type="text" id="nome">',
    },
    {
      titulo: "Imagens da página inicial não têm descrição",
      impacto_humano: "Quem usa leitor de tela não sabe o que as imagens mostram.",
      quem_e_afetado: ["pessoas cegas"],
      criterio_wcag: "1.1.1",
      pagina: "/",
      trecho_html: null,
    },
  ],
  plugin_resolve_parcialmente: ["contraste de cores"],
  exige_ajuste_no_codigo: ["campos de formulário sem rótulo", "imagens sem texto alternativo"],
  indicios_visuais: [
    { tipo: "texto_em_imagem", descricao: "Banner com o horário de atendimento escrito na imagem.", pagina: "https://hospitalexemplo.com.br/" },
  ],
  observacao_honestidade:
    "Teste automatizado com apoio de IA em até 5 páginas públicas. Ferramentas automáticas encontram só parte " +
    "das barreiras de acessibilidade; o restante exige avaliação humana.",
};

export const AUDITORIA = {
  id: "22222222-2222-4222-8222-222222222222",
  criado_em: "2026-10-24T13:03:00Z",
  nota: 58 as number | null,
  analise: ANALISE as typeof ANALISE | null,
  totais: { critico: 2, grave: 1, moderado: 0, leve: 0, paginas_auditadas: 2 },
  plugins: ["UserWay"],
  paginas: [
    {
      url: "https://hospitalexemplo.com.br/",
      status: "ok",
      erro: null,
      problemas: 2,
      armadilha_de_foco: false,
      link_pular_conteudo: false,
      sem_indicador_de_foco: 3,
      rolagem_horizontal_320: true,
    },
    {
      url: "https://hospitalexemplo.com.br/contato",
      status: "ok",
      erro: null,
      problemas: 1,
      armadilha_de_foco: true,
      link_pular_conteudo: true,
      sem_indicador_de_foco: 0,
      rolagem_horizontal_320: false,
    },
    {
      url: "https://hospitalexemplo.com.br/trabalhe-conosco",
      status: "bloqueada",
      erro: "o robots.txt do site não permite a leitura automática desta página",
      problemas: 0,
      armadilha_de_foco: false,
      link_pular_conteudo: null,
      sem_indicador_de_foco: 0,
      rolagem_horizontal_320: null,
    },
  ],
};

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
  auditoria?: unknown;
  confirmacao_dominio?: unknown;
}

export const ANDAMENTO_PADRAO: Detalhe[] = [
  { eventos: EVENTOS_INICIAIS },
  { eventos: EVENTOS_FINAIS, estado: "QUALIFICANDO", dossie: DOSSIE, auditoria: AUDITORIA },
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

// PNG 1×1 transparente: basta para testar o print autenticado na ficha
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

export const FICHA = {
  empresa: {
    ...EMPRESA,
    nome: "Hospital Exemplo S.A.",
    estado: "QUALIFICANDO",
    setor: "saude",
    cidade: "Sorocaba",
    uf: "SP",
  },
  dossie: {
    ...DOSSIE,
    descricao: "Hospital geral de alta complexidade.",
    missao: null,
    produtos_servicos: ["internação", "pronto-socorro"],
    publicos_atendidos: ["pacientes particulares e de convênios"],
    cidade: "Sorocaba",
    uf: "SP",
    porte_indicios: null,
    mencoes_inclusao: [
      {
        tema: "pcd",
        trecho: "Programa de inclusão de pessoas com deficiência.",
        url: "https://hospitalexemplo.com.br/esg",
      },
    ],
    sinais: [{ tipo: "outro", descricao: "Programa de inclusão no RH", url: "https://hospitalexemplo.com.br/esg" }],
    lacunas: ["o site não informa número de leitos"],
    paginas_lidas: ["https://hospitalexemplo.com.br/", "https://hospitalexemplo.com.br/esg"],
    tecnologias_site: ["WordPress"],
    raciocinio_resumido: "Dados da home e da página de ESG.",
  },
  auditoria: AUDITORIA,
  evidencias: [
    {
      numero: 1,
      titulo: ANALISE.top3_para_leigos[0].titulo,
      pagina: "/contato",
      print_indice: 0 as number | null,
      caixa: { left: 20, top: 30, width: 25, height: 10 } as { left: number; top: number; width: number; height: number } | null,
      alt: "Print da página /contato de hospitalexemplo.com.br, com o problema 1 destacado por uma caixa numerada.",
    },
    {
      numero: 2,
      titulo: ANALISE.top3_para_leigos[1].titulo,
      pagina: "/",
      print_indice: null as number | null,
      caixa: null as { left: number; top: number; width: number; height: number } | null,
      alt: "Print da página /.",
    },
  ],
  qualificacao: {
    score: 61,
    faixa: "morno",
    rotulo_faixa: "Morno",
    proximo_passo: "abordagem padrão",
    componentes: [
      { chave: "fit_icp", rotulo: "Aderência ao perfil de cliente (ICP)", valor: 90, peso: 0.3, contribuicao: 27,
        justificativa: "Setor prioritário (saúde); atua no Brasil (SP); porte ainda não conhecido, contado como neutro." },
      { chave: "intencao", rotulo: "Sinais de interesse", valor: 20, peso: 0.25, contribuicao: 5,
        justificativa: "Encontrado: 1× outro sinal, 1 menção(ões) a inclusão no site." },
      { chave: "gravidade_barreiras", rotulo: "Gravidade das barreiras", valor: 42, peso: 0.2, contribuicao: 8.4,
        justificativa: "Nota de acessibilidade 58 de 100: quanto mais barreiras, maior a necessidade." },
      { chave: "pressao_regulatoria", rotulo: "Pressão regulatória do setor", valor: 75, peso: 0.15, contribuicao: 11.25,
        justificativa: "Setor de saúde: a LBI (art. 63) vale para todos os sites; o setor tem exigências próprias." },
      { chave: "acessibilidade_decisor", rotulo: "Acesso ao decisor", valor: 0, peso: 0.1, contribuicao: 0,
        justificativa: "Ainda sem contatos mapeados; o score é recalculado quando os decisores forem encontrados." },
    ],
    regra_versao: "regra-v1",
    criado_em: "2026-10-26T15:00:00Z",
  } as unknown,
  decisores: [
    { id: "c1", nome: "Ana Souza", cargo: "CTO", area: "TI", email: "ana@hospitalexemplo.com.br",
      email_status: "valido", rotulo_email: "e-mail verificado", linkedin_url: "http://www.linkedin.com/in/ana-souza",
      fonte: "apollo", fonte_url: null },
    { id: "c2", nome: "Carla Dias", cargo: "Diretora de Compliance", area: "Compliance", email: null,
      email_status: "sem_email", rotulo_email: "sem e-mail", linkedin_url: null,
      fonte: "web+apollo", fonte_url: "https://hospitalexemplo.com.br/diretoria" },
  ] as unknown[],
  relatorio_disponivel: true,
  eventos: EVENTOS_FINAIS,
};

export const CONFIG_SCORE = {
  pesos: { fit_icp: 0.3, intencao: 0.25, gravidade_barreiras: 0.2, pressao_regulatoria: 0.15, acessibilidade_decisor: 0.1 },
  faixas: { quente: 70, morno: 45 },
};

export const REVISAO = {
  auditoria_id: "22222222-2222-4222-8222-222222222222",
  empresa_id: EMPRESA.id,
  achados: [
    { chave: "label", rotulo: ANALISE.top3_para_leigos[0].titulo, pagina: "/contato", veredito: null, motivo: null },
    { chave: "image-alt", rotulo: ANALISE.top3_para_leigos[1].titulo, pagina: "/", veredito: null, motivo: null },
  ],
  tecnicos: [{ chave: "color-contrast", rotulo: "Contraste de cores", pagina: null, veredito: null, motivo: null }],
  textos_honestos: null,
  completa: false,
  atualizado_em: null,
};

export const PLACAR = {
  meta_auditorias: 20,
  meta_setores: 4,
  meta_percentual: 90,
  auditorias_revisadas: 1,
  setores: 1,
  percentual_correto: 83.3,
  promessas_encontradas: 0,
  atingido: false,
  pendencias: ["faltam 19 auditoria(s) revisada(s)", "faltam 3 setor(es) diferente(s)", "acertos em 83.3%, abaixo de 90%"],
  lista: [
    { empresa_id: EMPRESA.id, nome: "Hospital Exemplo S.A.", setor: "saude", nota: 58, revisada: true, percentual: 83.3 },
    { empresa_id: "33333333-3333-4333-8333-333333333333", nome: "Faculdade Y", setor: "educacao", nota: 71, revisada: false, percentual: null },
  ],
};

interface Opcoes {
  disjuntorAtingido?: boolean;
  respostaPost?: { status: number; corpo: unknown };
  /** Respostas do andamento, em ordem (a última se repete). */
  andamento?: Detalhe[];
  /** Andamento depois que o vendedor confirma o site. */
  andamentoDepoisDaConfirmacao?: Detalhe[];
  respostaConfirmacao?: { status: number; corpo: unknown };
  ficha?: typeof FICHA;
  papel?: "admin" | "vendedor" | "leitura";
  respostaRevisao?: { status: number; corpo: unknown };
  respostaConfigScore?: { status: number; corpo: unknown };
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
  const revisoes: unknown[] = [];
  const confirmacoes: unknown[] = [];
  const configs: unknown[] = [];
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
        apollo: { creditos_hoje: 8, teto: 60, atingido: false, mensagem: "Créditos do Apollo hoje: 8 de 60." },
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
    if (url.pathname === "/auth/me") {
      return json(route, 200, { id: "u1", nome: "Marcos", email: "m@x.com", papel: opcoes.papel ?? "vendedor" });
    }
    if (url.pathname === "/revisao/fase1") return json(route, 200, PLACAR);
    if (url.pathname === "/config/score") {
      if (req.method() === "PUT") {
        configs.push(req.postDataJSON());
        const r = opcoes.respostaConfigScore ?? { status: 200, corpo: req.postDataJSON() };
        return json(route, r.status, r.corpo);
      }
      return json(route, 200, CONFIG_SCORE);
    }
    if (url.pathname === `/auditorias/${AUDITORIA.id}/revisao`) {
      if (req.method() === "PUT") {
        revisoes.push(req.postDataJSON());
        const r = opcoes.respostaRevisao ?? { status: 200, corpo: { ...REVISAO, completa: true, textos_honestos: true } };
        return json(route, r.status, r.corpo);
      }
      return json(route, 200, REVISAO);
    }
    if (url.pathname === `/empresas/${EMPRESA.id}/ficha`) return json(route, 200, opcoes.ficha ?? FICHA);
    if (url.pathname === `/empresas/${EMPRESA.id}/relatorio.pdf`) {
      return route.fulfill({ status: 200, headers: { ...CORS, "Content-Type": "application/pdf" }, body: "%PDF-1.7" });
    }
    if (url.pathname === `/empresas/${EMPRESA.id}/relatorio`) {
      return route.fulfill({
        status: 200,
        headers: { ...CORS, "Content-Type": "text/html; charset=utf-8" },
        body: "<!doctype html><html lang='pt-BR'><title>Relatório</title><main><h1>Relatório</h1></main></html>",
      });
    }
    if (url.pathname === `/empresas/${EMPRESA.id}/prints/0`) {
      return route.fulfill({ status: 200, headers: { ...CORS, "Content-Type": "image/png" }, body: PNG });
    }
    if (url.pathname === `/empresas/${EMPRESA.id}`) {
      const atual = andamento[Math.min(consulta, andamento.length - 1)];
      consulta += 1;
      return json(route, 200, { ...EMPRESA, dossie: null, auditoria: null, confirmacao_dominio: null, ...atual });
    }
    return json(route, 404, { detail: "não simulado" });
  });

  return { posts, confirmacoes, revisoes, configs };
}
