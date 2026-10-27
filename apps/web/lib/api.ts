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
  id: string;
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
  apollo?: { creditos_hoje: number; teto: number; atingido: boolean; mensagem: string };
}

// --- Ficha do Prospect (Tarefa 5) ---

export interface DossieCompleto {
  versao: number;
  criado_em: string;
  resumo: string[];
  descricao: string | null;
  missao: string | null;
  produtos_servicos: string[];
  publicos_atendidos: string[];
  cidade: string | null;
  uf: string | null;
  porte_indicios: string | null;
  mencoes_inclusao: { tema: string; trecho: string; url: string }[];
  sinais: { tipo: string; descricao: string; url: string }[];
  lacunas: string[];
  paginas_lidas: string[];
  tecnologias_site: string[];
  raciocinio_resumido: string | null;
}

export interface Evidencia {
  numero: number;
  titulo: string;
  pagina: string;
  print_indice: number | null;
  caixa: { left: number; top: number; width: number; height: number } | null;
  alt: string;
}

// --- Qualificação (Fase 2, §7.3 Etapa 3) ---

export type FaixaScore = "quente" | "morno" | "frio";

export interface ComponenteScore {
  chave: string;
  rotulo: string;
  valor: number;
  peso: number;
  contribuicao: number;
  justificativa: string;
}

export interface Qualificacao {
  score: number;
  faixa: FaixaScore;
  rotulo_faixa: string;
  proximo_passo: string;
  componentes: ComponenteScore[];
  regra_versao: string;
  criado_em: string;
}

export const COMPONENTES_SCORE = [
  "fit_icp",
  "intencao",
  "gravidade_barreiras",
  "pressao_regulatoria",
  "acessibilidade_decisor",
] as const;

export type ChaveComponente = (typeof COMPONENTES_SCORE)[number];

export const ROTULO_COMPONENTE: Record<ChaveComponente, string> = {
  fit_icp: "Aderência ao perfil de cliente (ICP)",
  intencao: "Sinais de interesse",
  gravidade_barreiras: "Gravidade das barreiras",
  pressao_regulatoria: "Pressão regulatória do setor",
  acessibilidade_decisor: "Acesso ao decisor",
};

export interface ConfigScore {
  pesos: Record<ChaveComponente, number>;
  faixas: { quente: number; morno: number };
}

// --- Decisores (Fase 2, §7.3 Etapa 4) ---

export interface Decisor {
  id: string;
  nome: string;
  cargo: string | null;
  area: string;
  email: string | null;
  email_status: "valido" | "nao_verificado" | "sem_email";
  rotulo_email: string;
  linkedin_url: string | null;
  fonte: string;
  fonte_url: string | null;
}

export interface Ficha {
  empresa: Empresa & { setor: string | null; cidade: string | null; uf: string | null };
  dossie: DossieCompleto | null;
  auditoria: AuditoriaResumo | null;
  evidencias: Evidencia[];
  qualificacao: Qualificacao | null;
  decisores: Decisor[];
  relatorio_disponivel: boolean;
  eventos: Evento[];
}

/** Baixa um arquivo protegido por login (o navegador não manda o token em links e imagens comuns). */
export async function baixarArquivo(caminho: string): Promise<Blob> {
  const token = lerToken();
  let r: Response;
  try {
    r = await fetch(`${API_URL}${caminho}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
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
    throw new ErroApi(r.status, detalhe ?? "Não foi possível baixar o arquivo.");
  }
  return r.blob();
}

// --- Revisão da Fase 1 (critério do §19) ---

export type Veredito = "correto" | "parcial" | "incorreto";

export interface ItemRevisao {
  chave: string;
  rotulo: string;
  pagina: string | null;
  veredito: Veredito | null;
  motivo: string | null;
}

export interface Revisao {
  auditoria_id: string;
  empresa_id: string;
  achados: ItemRevisao[];
  tecnicos: ItemRevisao[];
  textos_honestos: boolean | null;
  completa: boolean;
  atualizado_em: string | null;
}

export interface Placar {
  meta_auditorias: number;
  meta_setores: number;
  meta_percentual: number;
  auditorias_revisadas: number;
  setores: number;
  percentual_correto: number | null;
  promessas_encontradas: number;
  atingido: boolean;
  pendencias: string[];
  lista: {
    empresa_id: string;
    nome: string;
    setor: string | null;
    nota: number | null;
    revisada: boolean;
    percentual: number | null;
  }[];
}

export interface UsuarioAtual {
  id: string;
  nome: string;
  email: string;
  papel: "admin" | "vendedor" | "leitura";
}
