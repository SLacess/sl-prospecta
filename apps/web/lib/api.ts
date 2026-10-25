/**
 * Cliente da API do painel. O token fica em sessionStorage (ADR 0002); 401 leva de volta ao login.
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const CHAVE_TOKEN = "slp_token";

export function lerToken(): string | null {
  try {
    return sessionStorage.getItem(CHAVE_TOKEN);
  } catch {
    return null;
  }
}

export function guardarToken(token: string): void {
  try {
    sessionStorage.setItem(CHAVE_TOKEN, token);
  } catch {
    /* armazenamento indisponível */
  }
}

export function sair(): void {
  try {
    sessionStorage.removeItem(CHAVE_TOKEN);
  } catch {
    /* armazenamento indisponível */
  }
  window.location.href = "/login";
}

export class ErroApi extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(caminho: string, init: RequestInit = {}): Promise<T> {
  const token = lerToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let r: Response;
  try {
    r = await fetch(`${API_URL}${caminho}`, { ...init, headers });
  } catch {
    throw new ErroApi(0, "Não foi possível conectar à API. Verifique a conexão e tente novamente.");
  }

  if (r.status === 401) {
    sair();
    throw new ErroApi(401, "Sua sessão expirou. Entre novamente.");
  }
  if (!r.ok) {
    let detalhe: string | undefined;
    try {
      const corpo = await r.json();
      if (typeof corpo?.detail === "string") detalhe = corpo.detail;
    } catch {
      /* resposta sem JSON */
    }
    throw new ErroApi(r.status, detalhe ?? "Não foi possível concluir a ação. Tente novamente.");
  }
  return (await r.json()) as T;
}

// --- Tipos das respostas (espelham apps/api/app/routers) ---

export type EstadoProspect =
  | "NOVO" | "PESQUISANDO" | "AUDITANDO" | "QUALIFICANDO" | "ARQUIVADO" | "MAPEANDO_DECISORES"
  | "PREPARANDO_ABORDAGEM" | "EM_SEQUENCIA" | "SEM_RESPOSTA" | "RESPONDEU" | "NAO_INTERESSADO"
  | "REUNIAO_AGENDADA" | "PROPOSTA_ENVIADA" | "NEGOCIACAO" | "GANHO" | "PERDIDO";

export const ROTULO_ESTADO: Record<EstadoProspect, string> = {
  NOVO: "Novo",
  PESQUISANDO: "Pesquisando",
  AUDITANDO: "Auditando",
  QUALIFICANDO: "Qualificando",
  ARQUIVADO: "Arquivado",
  MAPEANDO_DECISORES: "Mapeando decisores",
  PREPARANDO_ABORDAGEM: "Preparando abordagem",
  EM_SEQUENCIA: "Em sequência",
  SEM_RESPOSTA: "Sem resposta",
  RESPONDEU: "Respondeu",
  NAO_INTERESSADO: "Não interessado",
  REUNIAO_AGENDADA: "Reunião agendada",
  PROPOSTA_ENVIADA: "Proposta enviada",
  NEGOCIACAO: "Negociação",
  GANHO: "Ganho",
  PERDIDO: "Perdido",
};

export interface Empresa {
  id: string;
  nome: string;
  dominio: string | null;
  estado: EstadoProspect;
  fonte: string;
  criado_em: string;
}

export interface Evento {
  id: string;
  tipo: string;
  origem: string;
  mensagem: string;
  ocorrido_em: string;
}

export const ROTULO_SETOR: Record<string, string> = {
  saude: "Saúde",
  educacao: "Educação",
  utilities: "Utilities e concessões",
  ecommerce: "E-commerce e varejo",
  financeiro: "Financeiro",
  outro: "Outro",
};

export interface DossieResumo {
  versao: number;
  setor: string | null;
  resumo: string[];
  criado_em: string;
}

export interface CandidatoDominio {
  dominio: string;
  nome_oficial: string;
  evidencia_url: string;
}

export interface PaginaAuditada {
  url: string;
  status: "ok" | "bloqueada" | "tempo_esgotado" | string;
  erro: string | null;
  problemas: number;
  armadilha_de_foco: boolean;
  link_pular_conteudo: boolean | null;
  sem_indicador_de_foco: number;
  rolagem_horizontal_320: boolean | null;
}

export interface AchadoParaLeigos {
  titulo: string;
  impacto_humano: string;
  quem_e_afetado: string[];
  criterio_wcag: string;
  pagina: string;
  trecho_html: string | null;
}

export interface AnaliseAuditoria {
  top3_para_leigos: AchadoParaLeigos[];
  plugin_resolve_parcialmente: string[];
  exige_ajuste_no_codigo: string[];
  indicios_visuais: { tipo: string; descricao: string; pagina: string }[];
  observacao_honestidade: string;
}

export interface AuditoriaResumo {
  criado_em: string;
  nota: number | null;
  totais: Record<string, number>;
  plugins: string[];
  paginas: PaginaAuditada[];
  analise: AnaliseAuditoria | null;
}

export interface EmpresaDetalhe extends Empresa {
  eventos: Evento[];
  dossie: DossieResumo | null;
  auditoria: AuditoriaResumo | null;
  confirmacao_dominio: { mensagem: string; candidatos: CandidatoDominio[] } | null;
}

export interface ProspeccaoResposta {
  empresa: Empresa;
  duplicada: boolean;
  na_fila: boolean;
  fila_pausada: boolean;
  mensagem: string;
}

export interface Disjuntores {
  custo: { custo_hoje_brl: string; teto_brl: string; atingido: boolean; mensagem: string };
}
