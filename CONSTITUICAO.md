# SL Prospecta — Constituição do Departamento de SDR Autônomo da Sinal Link

> **Documento-mãe do projeto.** Este arquivo define missão, princípios, arquitetura, agentes, regras de autonomia, modelo de dados, interface e roteiro de construção da plataforma. Ele deve ficar na raiz do repositório (`/CONSTITUICAO.md`) e ser lido por qualquer pessoa ou agente de código (Claude Code, Cursor etc.) antes de escrever uma linha. Quando houver conflito entre este documento e qualquer outra instrução de implementação, **este documento prevalece** até ser formalmente emendado (ver §20).

**Versão:** 1.0 · **Data:** 23/10/2026 · **Dono:** Marcos Alencar — Diretor-Geral, Sinal Link Acessibilidade (Sorocaba/SP)
**Produto vendido pela plataforma:** plugin de acessibilidade digital (tecnologia assistiva) + consultoria Sinal Link

---

## Sumário

1. Missão e visão
2. Princípios inegociáveis
3. O que a plataforma faz (escopo funcional)
4. Perfil de Cliente Ideal (ICP) e sinais de compra
5. Arquitetura geral
6. A equipe de agentes (o "departamento")
7. Pipeline ponta a ponta — da URL ao contrato
8. Motor de auditoria de acessibilidade real
9. Motor de abordagem — mensagens assertivas, humanas e amigáveis
10. Microsite personalizado por prospect (o diferencial disruptivo)
11. Geração automática de proposta comercial
12. CRM visual e painel de controle
13. Níveis de autonomia e governança humana
14. Aprendizado contínuo (a plataforma que melhora sozinha)
15. Conformidade: LGPD, entregabilidade e ética
16. Stack técnica e infraestrutura (GitHub + VPS Hostinger)
17. Modelo de dados
18. Estrutura do repositório e convenções
19. Roteiro de construção (fases)
20. Métricas de sucesso, custos e emendas
21. Anexos: prompts-base, variáveis de ambiente, critérios de aceite

---

## 1. Missão e visão

**Missão:** encontrar, entender e conquistar organizações que precisam tornar seus ambientes digitais acessíveis — e fazer isso com a qualidade de um consultor sênior e a escala de uma máquina.

**Visão:** ser o primeiro departamento comercial do Brasil em que **cada prospect recebe um diagnóstico real e personalizado do próprio site antes do primeiro contato**, transformando a prospecção de "pedido de atenção" em "entrega de valor".

**Tese central:** SDRs humanos falham porque abordam sem contexto. A SL Prospecta só aborda depois de **auditar, pesquisar e entender** — o e-mail frio deixa de ser frio porque já carrega evidência concreta e útil para quem recebe.

---

## 2. Princípios inegociáveis

Estes princípios orientam toda decisão técnica e todo texto gerado pela IA.

1. **Evidência antes de argumento.** Nenhuma abordagem é enviada sem um achado verificável (problema real encontrado no site do prospect, com print ou trecho de código).
2. **Honestidade técnica.** A plataforma nunca afirma que o plugin torna um site "100% acessível" ou "em conformidade total com a lei". Testes automatizados detectam apenas parte das barreiras (estimativa de mercado: 30–40% dos critérios WCAG); o restante exige avaliação humana. O plugin é apresentado como **camada de tecnologia assistiva + início de uma jornada**, complementado pela consultoria Sinal Link.
3. **Sem medo como tática principal.** Risco jurídico (LBI, TAC, Ministério Público) pode ser mencionado como contexto, nunca como ameaça. O tom é consultivo e colaborativo.
4. **Humanização real.** As mensagens soam como escritas por uma pessoa atenciosa, não por um robô de vendas. Proibido: elogios genéricos, falsa intimidade, urgência artificial, "espero que este e-mail o encontre bem".
5. **Autonomia com freios.** A IA executa tudo que é reversível; o que é irreversível ou de alto risco (envio em massa, proposta com preço fora da tabela, resposta a reclamação) passa por regras de governança (§13).
6. **Respeito à pessoa.** Opt-out em um clique, honrado imediatamente e para sempre. Nada de raspar redes sociais em violação de termos de uso.
7. **Tudo é rastreável.** Cada decisão de agente gera registro (o quê, por quê, com quais dados, qual modelo, quanto custou).
8. **Acessibilidade em casa.** A própria plataforma, o microsite do prospect e as propostas seguem WCAG 2.2 AA. Vender acessibilidade com material inacessível é inaceitável.

---

## 3. O que a plataforma faz (escopo funcional)

| # | Função de um SDR humano | Como a SL Prospecta executa |
|---|---|---|
| 1 | Encontrar empresas | Entrada manual (nome ou URL), upload de planilha (lote), ou **Caçador autônomo** que busca empresas por sinais de compra |
| 2 | Pesquisar a empresa | Raspagem do site, enriquecimento via Apollo.io, notícias, vagas abertas, setor, porte, tecnologia usada |
| 3 | Qualificar pelo ICP | Pontuação multifatorial (fit + intenção + urgência regulatória + gravidade das barreiras) |
| 4 | Encontrar o decisor | Apollo (TI, RH, D&I, Marketing, ESG, Jurídico/Compliance), validação de e-mail |
| 5 | Preparar argumento | Mini-relatório de acessibilidade real + leitura do contexto regulatório do setor |
| 6 | Abordar | Sequência multicanal personalizada (e-mail como canal principal; LinkedIn e WhatsApp como tarefas assistidas) |
| 7 | Conversar | Classificação de respostas e resposta autônoma para objeções conhecidas |
| 8 | Agendar | Proposta de horários pelo Google Calendar e criação do convite |
| 9 | Propor | Geração de proposta visual em padrão de consultoria de tecnologia (PDF + página web) |
| 10 | Registrar | CRM visual com linha do tempo completa de cada interação |
| 11 | Aprender | Análise semanal do que funcionou e ajuste automático de mensagens, horários e segmentos |

**Fora do escopo da v1:** ligações telefônicas por voz sintética, envio automático em LinkedIn (violaria termos de uso), assinatura de contrato e faturamento.

---

## 4. Perfil de Cliente Ideal (ICP) e sinais de compra

### 4.1 ICP base (configurável no painel)

- **Setores prioritários:** saúde (hospitais, operadoras, redes de clínicas), educação (IES privadas e grupos educacionais), utilities e concessões públicas, e-commerce e varejo, bancos e fintechs.
- **Porte:** a partir de 100–300 colaboradores (parametrizável por campanha).
- **Geografia:** Brasil (campanhas regionais, ex.: Sorocaba e região); preparação para LATAM hispânica em fase posterior (§19).
- **Decisores-alvo:** gestor/diretor de TI, RH, D&I, Marketing/Digital, ESG, Compliance/Jurídico.

### 4.2 Sinais de compra (o "radar")

O agente Caçador monitora e pontua sinais como:

| Sinal | Peso sugerido | Fonte |
|---|---|---|
| Notícia de TAC, ação civil ou recomendação do MP sobre acessibilidade no setor/empresa | Alto | Busca de notícias |
| Avaliação ou recredenciamento MEC próximo (IES) | Alto | Portais públicos / notícias |
| Vaga aberta para PcD, D&I, acessibilidade ou UX | Médio | Apollo (job postings) |
| Relatório ESG/sustentabilidade publicado mencionando inclusão | Médio | Site da empresa |
| Redesign recente do site (mudança de tecnologia detectada) | Médio | Comparação de snapshots |
| Lançamento de app, portal do cliente ou e-commerce | Médio | Notícias / site |
| Concorrente direto já com recurso de acessibilidade | Médio | Varredura do setor |
| Visita ao site da Sinal Link (rastreamento de visitantes) | Alto | Apollo website visitors |

---

## 5. Arquitetura geral

```
┌──────────────────────────────────────────────────────────────────────┐
│                     PAINEL WEB (Next.js) — acessível                 │
│  Prospecção · Lote · CRM Kanban · Linha do tempo · Caixa de aprovação│
│  Dashboard · Configurações (ICP, tom, limites, preços)               │
└───────────────┬──────────────────────────────────────────────────────┘
                │ REST + WebSocket (eventos em tempo real)
┌───────────────▼──────────────────────────────────────────────────────┐
│                     API (FastAPI / Python)                           │
│  Autenticação · Regras de governança · Webhooks · Rastreamento       │
└───────┬───────────────────────┬──────────────────────────┬───────────┘
        │                       │                          │
┌───────▼────────┐   ┌──────────▼───────────┐   ┌──────────▼──────────┐
│ ORQUESTRADOR   │   │ FILA (Redis +        │   │ POSTGRES + pgvector │
│ de agentes     │◄─►│ workers Python)      │◄─►│ dados, memória,     │
│ (máquina de    │   │ raspagem, auditoria, │   │ embeddings, logs    │
│  estados)      │   │ e-mail, PDF          │   └─────────────────────┘
└───────┬────────┘   └──────────┬───────────┘
        │                       │
┌───────▼───────────────────────▼──────────────────────────────────────┐
│ SERVIÇOS EXTERNOS                                                    │
│ Claude API · Apollo.io · Playwright+axe-core · Lighthouse ·          │
│ Provedor de e-mail transacional · Gmail/Google Calendar · Busca web  │
└──────────────────────────────────────────────────────────────────────┘
```

**Decisões arquiteturais:**

- **Orquestração por máquina de estados, não por agente livre.** Cada prospect percorre estados bem definidos (§7). Dentro de cada estado, agentes de IA têm liberdade; a transição entre estados obedece regras. Isso dá autonomia sem caos.
- **Monorepo** com `apps/web` (painel), `apps/api` (backend), `workers/` (tarefas pesadas) e `packages/` (prompts, esquemas compartilhados).
- **Tudo em contêineres Docker** orquestrados por Docker Compose na VPS Hostinger, com deploy automático via GitHub Actions.
- **n8n opcional** como camada de integrações rápidas (ex.: enviar resumo diário no WhatsApp), mas o núcleo da lógica fica em código versionado.

---

## 6. A equipe de agentes (o "departamento")

Cada agente tem uma função, um modelo de IA padrão, ferramentas permitidas e uma "definição de pronto". Modelos indicados são o padrão inicial e podem ser trocados por configuração.

| Agente | Papel no departamento | Modelo padrão | Ferramentas |
|---|---|---|---|
| **Caçador** (Hunter) | Encontra empresas novas por sinais de compra | `claude-haiku-5-5` (triagem) | Busca web, Apollo search, notícias |
| **Pesquisador** (Researcher) | Monta o dossiê da empresa | `claude-sonnet-5-5` | Raspagem, Apollo enrich, busca web |
| **Auditor** | Executa e interpreta a auditoria de acessibilidade | `claude-sonnet-5-5` (+ visão) | Playwright, axe-core, Lighthouse, screenshots |
| **Qualificador** | Calcula score e decide se vale abordar | `claude-haiku-5-5` + regras | Banco de dados |
| **Mapeador de Decisores** | Encontra e valida as pessoas certas | `claude-haiku-5-5` | Apollo people search, validação de e-mail |
| **Estrategista** | Escolhe ângulo, persona e canal | `claude-opus-5-5` | Dossiê, memória de campanhas vencedoras |
| **Redator** (Copywriter) | Escreve as mensagens da sequência | `claude-opus-5-5` | Dossiê, relatório, guia de voz |
| **Crítico** (Reviewer) | Revisa cada mensagem antes do envio | `claude-sonnet-5-5` | Checklist de qualidade (§9.4) |
| **Mensageiro** | Agenda e envia, respeitando limites | regras (sem IA) | Provedor de e-mail, Gmail |
| **Leitor de Respostas** | Classifica respostas e propõe/envia réplica | `claude-sonnet-5-5` | Caixa de entrada, CRM |
| **Agendador** | Converte interesse em reunião | `claude-haiku-5-5` | Google Calendar |
| **Propositor** | Gera a proposta comercial | `claude-opus-5-5` | Tabela de preços, modelos visuais, gerador de PDF |
| **Analista** (Coach) | Estuda resultados e sugere/aplica melhorias | `claude-opus-5-5` | Métricas, histórico de mensagens |
| **Guardião** (Compliance) | Verifica LGPD, opt-out, limites e tom | regras + `claude-haiku-5-5` | Lista de supressão, logs |

**Regra de ouro dos agentes:** todo agente devolve uma saída estruturada (JSON validado por esquema) + um campo `raciocinio_resumido` legível pelo vendedor. Nenhum agente escreve diretamente no banco: ele devolve o resultado ao Orquestrador, que valida e persiste.

---

## 7. Pipeline ponta a ponta — da URL ao contrato

### 7.1 Estados do prospect

```
NOVO → PESQUISANDO → AUDITANDO → QUALIFICANDO ──(descartado)──► ARQUIVADO
                                     │
                                     ▼
                           MAPEANDO_DECISORES → PREPARANDO_ABORDAGEM
                                     │
                         (caixa de aprovação, se exigido pelo nível §13)
                                     ▼
                              EM_SEQUENCIA ──► RESPONDEU ──► REUNIAO_AGENDADA
                                     │              │               │
                                     ▼              ▼               ▼
                               SEM_RESPOSTA    NAO_INTERESSADO  PROPOSTA_ENVIADA
                              (nutrição 90d)   (supressão/nutr.)    │
                                                              NEGOCIACAO
                                                                    │
                                                         GANHO ◄────┴────► PERDIDO
```

### 7.2 Entradas aceitas

1. **Campo único "Nome da empresa ou site"** — se for nome, o Pesquisador resolve o domínio oficial (busca + Apollo) e pede confirmação apenas se houver ambiguidade (ex.: dois domínios plausíveis).
2. **Upload de planilha** (`.xlsx` ou `.csv`) — mapeamento inteligente de colunas: a IA identifica sozinha quais colunas são empresa, site, CNPJ, cidade, contato, e mostra uma prévia para confirmação. Deduplicação automática por domínio e CNPJ.
3. **Caçador autônomo** — campanhas configuradas ("IES privadas em SP com mais de 300 colaboradores") geram prospects continuamente, dentro de uma cota diária.
4. **Visitantes do site Sinal Link** — empresas que visitaram o site entram com prioridade alta.

### 7.3 Etapas detalhadas

**Etapa 1 — Pesquisa (dossiê).** O Pesquisador coleta:
- Dados cadastrais (setor, porte, localização, faturamento estimado) via Apollo.
- Missão, produtos, públicos atendidos, menções a inclusão/ESG/PcD no próprio site.
- Notícias dos últimos 12 meses; vagas abertas; tecnologias do site.
- Contexto regulatório aplicável ao setor (ver base de conhecimento §8.5).
Saída: `dossie.json` + resumo de 5 linhas em linguagem natural.

**Etapa 2 — Auditoria.** Ver §8. Saída: `auditoria.json`, prints anotados e nota de 0 a 100.

**Etapa 3 — Qualificação.** Score composto:

```
SCORE = 0,30·Fit_ICP + 0,25·Intencao(sinais) + 0,20·Gravidade_barreiras
      + 0,15·Pressao_regulatoria + 0,10·Acessibilidade_do_decisor(contato válido)
```
- ≥ 70: **Quente** → abordagem prioritária.
- 45–69: **Morno** → abordagem padrão.
- < 45: **Frio** → nutrição de longo prazo ou arquivamento.
Pesos ajustáveis no painel e recalibrados pelo Analista (§14).

**Etapa 4 — Decisores.** Até 3 contatos por empresa (ex.: TI + RH + Marketing), com função, e-mail validado, LinkedIn (apenas link, sem raspagem). Regra de multithreading: nunca enviar a mesma mensagem para duas pessoas da mesma empresa; cada uma recebe o ângulo da sua área.

**Etapa 5 — Estratégia.** O Estrategista escolhe, por decisor:
- **Ângulo:** experiência do cliente, inclusão de colaboradores PcD, ESG/reputação, conformidade (LBI/NBR 17225/eMAG), conversão e alcance de mercado.
- **Gancho de evidência:** o achado mais impactante e mais fácil de entender por um leigo.
- **Canal e cadência.**

**Etapa 6 — Redação e revisão.** Redator escreve; Crítico avalia com nota de 0–10 em cada critério do checklist (§9.4). Abaixo de 8 em qualquer critério → reescrita (máx. 3 ciclos) → se persistir, vai para a caixa de aprovação humana.

**Etapa 7 — Envio e conversa.** Mensageiro envia em janelas de horário inteligentes (padrão: terça a quinta, 8h–10h30 e 14h–16h, horário do destinatário), respeitando limites diários por caixa. Leitor de Respostas classifica toda resposta (§9.5).

**Etapa 8 — Reunião e proposta.** Interesse → Agendador oferece horários → reunião criada no Google Calendar com o vendedor → após a reunião, vendedor dita/cola anotações → Propositor gera a proposta (§11).

---

## 8. Motor de auditoria de acessibilidade real

### 8.1 O que é testado (por página)

Páginas auditadas por padrão: **home + até 4 páginas-chave** detectadas automaticamente (contato, produto/curso, login/portal, carrinho/checkout ou "trabalhe conosco").

| Camada | Ferramenta | Exemplos de verificação |
|---|---|---|
| Automática de regras | **axe-core** via Playwright | contraste, `alt` ausente, rótulos de formulário, hierarquia de títulos, ARIA inválido, idioma da página |
| Desempenho/boas práticas | **Lighthouse** (categoria accessibility) | nota geral e diagnósticos complementares |
| Teclado | Script Playwright | navegar com Tab: foco visível? armadilhas de foco? menu operável sem mouse? link "pular para o conteúdo"? |
| Zoom/responsividade | Playwright em 320px e zoom 200% | conteúdo cortado, rolagem horizontal (WCAG 1.4.10) |
| Visual com IA | Modelo com visão sobre screenshots | texto em imagem, informação transmitida só por cor, CAPTCHAs visuais, vídeos sem legenda aparente |
| Semântica com IA | Árvore de acessibilidade + IA | links genéricos ("clique aqui"), botões sem nome, estrutura de leitura confusa |
| Recurso assistivo existente | Detecção de scripts | já usa algum plugin/overlay de acessibilidade? Qual? |

### 8.2 Saída do Auditor

```json
{
  "nota_geral": 54,
  "paginas_auditadas": 5,
  "totais": {"critico": 7, "grave": 15, "moderado": 22, "leve": 9},
  "top3_para_leigos": [
    {
      "titulo": "Formulário de contato não informa o que cada campo pede para quem usa leitor de tela",
      "impacto_humano": "Uma pessoa cega não consegue saber onde digitar nome, e-mail ou mensagem.",
      "criterio_wcag": "1.3.1 / 4.1.2",
      "evidencia": {"print": "s3://.../contato_anotado.png", "trecho_html": "<input type='text' placeholder='...'>"},
      "pagina": "/contato"
    }
  ],
  "plugin_resolve_parcialmente": ["contraste", "tamanho de fonte", "espaçamento"],
  "exige_ajuste_no_codigo": ["rótulos de formulário", "ordem de foco"],
  "observacao_honestidade": "Teste automatizado + IA. Não substitui avaliação manual completa."
}
```

O campo `plugin_resolve_parcialmente` vs. `exige_ajuste_no_codigo` é obrigatório: ele permite à proposta vender **plugin + consultoria** de forma honesta e com maior valor.

### 8.3 Mini-relatório (o "presente" para o prospect)

Uma página A4 (PDF) e uma versão web, com:
1. Nota geral e comparação com a média do setor (benchmark interno acumulado pela plataforma).
2. Os 3 achados mais relevantes, com print anotado e explicação em linguagem simples.
3. "Quem é afetado": pessoas cegas, com baixa visão, daltônicas, com deficiência motora, idosos, neurodivergentes.
4. Três ações recomendadas (sendo pelo menos uma gratuita e possível de fazer sem a Sinal Link — gera confiança).
5. Nota metodológica honesta.

### 8.4 Execução segura da raspagem

- Respeitar `robots.txt` e limitar a 1 requisição por segundo por domínio.
- User-agent identificado (`SinalLinkA11yAudit/1.0 (+https://sinallink.com.br/auditoria)`).
- Somente páginas públicas; nunca contornar login, CAPTCHA ou paywall.
- Navegador headless isolado em contêiner, com tempo limite por página (45s).

### 8.5 Base de conhecimento regulatória (RAG)

Coleção vetorial no pgvector, mantida pelo time e atualizada periodicamente, contendo resumos próprios (não cópias integrais) de: Lei Brasileira de Inclusão (Lei 13.146/2015, incluindo art. 63 sobre sítios eletrônicos), ABNT NBR 17225 (acessibilidade web), eMAG (setor público), WCAG 2.2, Decreto 5.296/2004, exigências do instrumento de avaliação do MEC para IES, normas setoriais de saúde e de serviços financeiros, e casos públicos de TACs. Cada afirmação regulatória em mensagens ou propostas deve citar uma fonte desta base. **A plataforma não emite parecer jurídico.**

---

## 9. Motor de abordagem — mensagens assertivas, humanas e amigáveis

### 9.1 Guia de voz Sinal Link (injetado em todos os prompts de redação)

- **Tom:** consultivo, setorial, generoso com conhecimento. Fala como alguém que entende o negócio do prospect.
- **Estrutura do primeiro e-mail (máx. 120 palavras):**
  1. Observação específica sobre a empresa (não elogio vazio).
  2. Um achado real, explicado pelo impacto humano.
  3. Ponte para o interesse do decisor (cliente, colaborador, marca, conformidade).
  4. Oferta de valor sem compromisso (o relatório completo / microsite).
  5. Pergunta leve como CTA ("faz sentido eu te mostrar em 15 minutos?").
- **Assunto:** curto, minúsculo, específico (ex.: "formulário de contato da [empresa]").
- **Proibições:** "revolucionário", "solução completa", "100% acessível", "garantimos conformidade", múltiplos links, anexos no 1º contato, ponto de exclamação em excesso, emojis.

### 9.2 Personalização por persona

| Decisor | Ângulo principal | Linguagem |
|---|---|---|
| TI | Esforço de correção, padrões técnicos (WCAG/NBR 17225), integração simples do plugin | técnica, objetiva |
| RH / D&I | Inclusão de colaboradores PcD, Lei de Cotas, marca empregadora | humana, propósito + métrica |
| Marketing / Digital | Alcance (cerca de 18,6 milhões de pessoas com deficiência no Brasil, segundo o IBGE/PNAD 2022), conversão, reputação | resultado, experiência |
| ESG | Indicadores sociais, relatórios, critérios de investidores | estratégica |
| Jurídico / Compliance | LBI, exposição a TAC, trilha de evidências | sóbria, factual |

### 9.3 Sequência padrão (ajustável e otimizada pelo Analista)

| Dia | Canal | Conteúdo |
|---|---|---|
| 0 | E-mail | Achado principal + convite para ver o relatório |
| 3 | E-mail (mesma thread) | Segundo achado, outro tipo de usuário afetado |
| 5 | LinkedIn (tarefa para o vendedor) | Pedido de conexão com nota curta gerada pela IA |
| 8 | E-mail | Caso/insight do setor ("como IES estão se preparando para...") |
| 14 | E-mail | Benchmark: "vocês estão na posição X entre N sites do setor que analisamos" |
| 21 | E-mail de encerramento | Despedida educada, deixando o relatório disponível |

WhatsApp: apenas se o contato tiver interagido antes ou fornecido o número, como tarefa assistida ou via API oficial do WhatsApp Business com modelo aprovado.

### 9.4 Checklist do Crítico (nota 0–10 cada)

1. **Especificidade:** só poderia ter sido escrito para esta empresa?
2. **Veracidade:** todo fato confere com dossiê/auditoria?
3. **Humanidade:** soa como pessoa real e respeitosa?
4. **Clareza:** um leigo entende o achado em 5 segundos?
5. **Valor:** o destinatário ganha algo mesmo sem responder?
6. **Honestidade:** nenhuma promessa exagerada sobre o plugin ou a lei?
7. **Brevidade:** dentro do limite de palavras?
8. **Acessibilidade do próprio e-mail:** texto simples, links descritivos, sem informação só em imagem?

### 9.5 Leitor de Respostas — classes e ações

| Classe | Ação autônoma (nível ≥ L3) |
|---|---|
| Interessado | Responde com proposta de horários; move para RESPONDEU |
| Pede mais informação | Responde com material relevante e relatório completo |
| Objeção conhecida (preço, "já temos plugin", "não é prioridade agora") | Responde com contra-argumento da biblioteca de objeções |
| Encaminhou para outra pessoa | Agradece, cria novo contato, inicia abordagem referenciada |
| Fora do escritório | Pausa e reagenda após a data de retorno |
| Não interessado | Agradece, encerra, nutrição em 6 meses (se permitido) |
| Pedido de descadastro / irritação | Supressão imediata e permanente; alerta ao vendedor |
| Ambíguo ou sensível | **Sempre** vai para aprovação humana |

---

## 10. Microsite personalizado por prospect (o diferencial disruptivo)

Cada prospect qualificado ganha uma página exclusiva e privada (`https://diagnostico.sinallink.com.br/{slug-unico}`), que é o coração da conversão.

**Conteúdo do microsite:**

1. **Saudação personalizada** com o nome da empresa e do decisor.
2. **"Seu site pelos olhos de quem tem deficiência"** — os recursos mais disruptivos da plataforma:
   - **Simulador de leitor de tela:** um áudio gerado por síntese de voz reproduzindo como um leitor de tela anuncia o topo da página do prospect (baseado na árvore de acessibilidade real), por exemplo: "botão, botão, link, imagem, imagem sem descrição...". A pessoa ouve a barreira, em vez de ler sobre ela.
   - **Simulador visual:** prints da home com filtros de daltonismo, baixa visão e zoom de 200%.
   - **Vídeo de navegação por teclado:** gravação automática do Playwright tentando navegar só com Tab, mostrando onde o foco se perde.
3. **Antes e depois:** o mesmo trecho do site com o plugin ativado (prévia injetada em ambiente de demonstração, sem alterar o site real).
4. **Relatório interativo** com os achados e a nota comparada ao setor.
5. **Calculadora de alcance:** quantas pessoas do público do prospect podem estar enfrentando barreiras (usando dados públicos do IBGE, com fonte citada).
6. **Agendamento integrado** (link para horários do vendedor) e botão "falar com um especialista".

**Rastreamento de engajamento (com transparência):** abertura do microsite, tempo em cada seção, reprodução do áudio/vídeo, cliques em agendar, download do PDF. Cada evento alimenta a linha do tempo do CRM e o **Score de Intenção em tempo real**: se o decisor ouve o simulador de leitor de tela duas vezes e volta ao microsite no dia seguinte, o vendedor recebe alerta "momento quente" para contato humano imediato.

> Observação técnica: a taxa de abertura de e-mail via pixel é imprecisa (proteções de privacidade de clientes como Apple Mail inflam aberturas). Por isso, **o sinal confiável de engajamento é o comportamento no microsite**, não a abertura do e-mail.

O microsite inclui aviso de privacidade e link de opt-out, e expira após 120 dias.

---

## 11. Geração automática de proposta comercial

### 11.1 Gatilho
Após reunião registrada (anotações do vendedor coladas, ditadas ou transcritas) ou por solicitação direta no CRM.

### 11.2 Estrutura (padrão de consultoria de tecnologia)

1. Capa com identidade visual Sinal Link e logotipo do cliente.
2. Resumo executivo (1 página): situação, oportunidade, recomendação.
3. Diagnóstico: dados da auditoria e do microsite, com visualizações.
4. Contexto setorial e regulatório (com fontes da base §8.5).
5. Solução proposta em camadas: **plugin de acessibilidade** (tecnologia assistiva imediata) + **consultoria Sinal Link** (correções no código, capacitação, auditoria manual) + **monitoramento contínuo**.
6. Roadmap de implantação (30/60/90 dias).
7. Investimento: planos a partir da **tabela de preços configurada** (a IA nunca inventa preço).
8. Por que a Sinal Link: experiência, cases, equipe.
9. Próximos passos e validade.

### 11.3 Formatos
- **PDF** gerado por HTML + WeasyPrint (PDF com tags e estrutura acessível).
- **Proposta web** com rastreamento (seções lidas, tempo, encaminhamentos).
- **Regra:** desconto acima do limite configurado ou escopo fora do catálogo exige aprovação do Marcos.

---

## 12. CRM visual e painel de controle

### 12.1 Telas

1. **Painel de Prospecção** (tela inicial)
   - Campo único: "Digite o nome da empresa ou o site" + botão **Prospectar**.
   - Área de arrastar e soltar planilha para lote, com prévia do mapeamento de colunas.
   - Feed ao vivo: "Auditando hospitalexemplo.com.br — página 3 de 5…".
2. **CRM Kanban** — colunas = estados do §7.1; cartões com nome, score (cor + número + texto, nunca só cor), nota de acessibilidade, próximo passo e responsável. Arrastar cartão = mudança manual de estado (registrada).
3. **Ficha do Prospect**
   - Dossiê, auditoria, decisores, mensagens enviadas/recebidas.
   - **Linha do tempo unificada**: cada e-mail, resposta, visita ao microsite, reprodução de áudio, abertura de proposta, ação de agente e intervenção humana.
   - Botões: "Assumir conversa" (pausa a IA), "Gerar proposta", "Reauditar", "Pausar", "Descartar".
   - **Copiloto da ficha:** chat em que o vendedor pergunta ("qual o melhor argumento para o diretor de TI dessa empresa?") e a IA responde com base em tudo que sabe do prospect.
4. **Caixa de Aprovação** — mensagens e ações aguardando revisão, com edição em linha e atalhos de teclado (aprovar, editar, rejeitar com motivo — o motivo treina o Analista).
5. **Dashboard**
   - Funil: prospects → qualificados → abordados → responderam → reuniões → propostas → ganhos.
   - Taxas por setor, persona, ângulo e versão de mensagem.
   - Valor de pipeline e previsão de receita.
   - Custo de IA e de dados por prospect e por reunião gerada.
   - **Briefing diário** gerado pela IA às 8h: "3 prospects estão quentes hoje, 2 propostas foram abertas ontem, a mensagem com ângulo ESG está superando as demais em IES".
6. **Configurações** — ICP, pesos do score, tabela de preços, limites de envio, horários, nível de autonomia por etapa, guia de voz, biblioteca de objeções, caixas de e-mail conectadas.

### 12.2 Requisitos de interface
- WCAG 2.2 AA: navegação completa por teclado, foco visível, contraste, rótulos, compatível com leitores de tela.
- Responsiva (uso no celular para aprovar mensagens e ver alertas).
- Notificações: no painel, por e-mail e, opcionalmente, WhatsApp (via n8n) para "momentos quentes".
- Perfis de acesso: **Admin** (Marcos), **Vendedor** (ex.: José Elias), **Leitura**.

---

## 13. Níveis de autonomia e governança humana

A autonomia é concedida **por etapa** e evolui por mérito medido, como um SDR júnior que ganha confiança.

| Nível | Nome | Comportamento |
|---|---|---|
| L0 | Manual | IA só sugere; humano faz tudo |
| L1 | Assistido | IA prepara tudo; humano aprova cada ação |
| L2 | Supervisionado | IA executa; humano aprova primeiro contato e respostas a objeções |
| L3 | Autônomo com amostragem | IA executa tudo; 10% das ações vão para revisão aleatória; exceções sempre revisadas |
| L4 | Autônomo pleno | IA executa; humano vê relatórios e alertas |

**Configuração inicial recomendada:** pesquisa, auditoria, qualificação e decisores em L4; primeiro e-mail em L2 nas primeiras 4 semanas; respostas em L2; propostas em L1.

**Promoção automática sugerida:** após 50 ações consecutivas aprovadas sem edição significativa (< 10% do texto alterado), a plataforma **sugere** subir um nível; quem decide é o Admin.

**Disjuntores automáticos (kill switches)** — pausam toda a operação de envio e alertam o Admin:
- Taxa de rejeição (bounce) > 3% em 24h.
- Reclamações de spam > 0,1%.
- Taxa de respostas negativas/irritadas > 5% em uma campanha.
- Custo diário de IA/dados acima do teto configurado.
- Erro de veracidade detectado pelo Crítico em mensagem já enviada.

**Botão vermelho:** "Pausar tudo" sempre visível no painel.

---

## 14. Aprendizado contínuo (a plataforma que melhora sozinha)

1. **Experimentos automáticos:** cada campanha testa variações (assunto, ângulo, tamanho, CTA, horário). O Analista usa alocação adaptativa (estilo multi-armed bandit): variações vencedoras recebem mais tráfego automaticamente.
2. **Memória de campanhas vencedoras:** mensagens que geraram reunião são armazenadas com embeddings e servem de exemplos para o Redator em prospects semelhantes (mesmo setor e persona).
3. **Aprendizado com o humano:** toda edição na Caixa de Aprovação gera um "diff de estilo" que o Analista resume semanalmente em novas regras para o guia de voz (aplicadas após aprovação do Admin).
4. **Retrospectiva semanal:** relatório automático — o que funcionou, o que não funcionou, hipóteses para a semana seguinte, ajustes já aplicados e ajustes que aguardam aprovação.
5. **Benchmark setorial vivo:** cada auditoria alimenta a base anônima de notas por setor, o que torna os comparativos dos microsites cada vez mais ricos — e gera, como subproduto, conteúdo para relatórios públicos de mercado ("Índice Sinal Link de Acessibilidade Digital"), ótimo para marketing e PR.
6. **Recalibração do score:** mensalmente, o Analista compara scores com resultados reais (ganhou/perdeu) e propõe novos pesos.

---

## 15. Conformidade: LGPD, entregabilidade e ética

### 15.1 LGPD
- **Base legal:** legítimo interesse para contato B2B com profissionais em seu papel corporativo, documentado em um Relatório de Legítimo Interesse (LIA) mantido no repositório (`/docs/compliance/LIA.md`). Recomenda-se validação com advogado.
- Coletar apenas dados profissionais necessários (nome, cargo, e-mail corporativo, empresa).
- Todo e-mail informa quem é o remetente, por que a pessoa está recebendo e como sair.
- **Lista de supressão global** (por e-mail e por domínio), verificada antes de qualquer envio.
- Atendimento a pedidos de titular (acesso, correção, exclusão) pelo painel, com exclusão em até 15 dias.
- Retenção: prospects sem interação são anonimizados após 18 meses.
- Dados em servidor sob controle da Sinal Link (VPS), criptografia em repouso para campos sensíveis e backups criptografados.

### 15.2 Entregabilidade de e-mail
- **Domínio(s) secundário(s) exclusivos para prospecção** (ex.: `sinallink-acessibilidade.com.br`), nunca o domínio principal.
- SPF, DKIM e DMARC configurados; aquecimento (warm-up) gradual de 2–4 semanas.
- Limite inicial de 30–50 e-mails por caixa por dia; múltiplas caixas com rodízio.
- Validação de e-mail antes do envio; nenhum envio para endereços "catch-all" sem verificação.
- Texto simples, sem anexos e no máximo 1 link no primeiro contato.

### 15.3 Ética da IA
- Se perguntada diretamente ("é um robô?"), a plataforma responde com honestidade que a pesquisa e o rascunho foram feitos com apoio de IA e que há uma pessoa da Sinal Link acompanhando. Assinaturas usam pessoas reais da equipe que de fato acompanham as contas.
- Nada de fabricar depoimentos, cases ou números. Todo dado citado tem fonte rastreável.

---

## 16. Stack técnica e infraestrutura (GitHub + VPS Hostinger)

### 16.1 Stack

| Camada | Tecnologia | Motivo |
|---|---|---|
| Frontend | Next.js + TypeScript + Tailwind + componentes acessíveis (Radix UI / shadcn) | produtividade, acessibilidade nativa dos componentes |
| Backend/API | FastAPI (Python 3.12) + Pydantic | ecossistema de IA e automação em Python |
| Workers | Python + fila Redis (RQ/Arq ou Celery) | raspagem, auditoria e e-mails em segundo plano |
| Navegador | Playwright (Chromium) + axe-core + Lighthouse CLI | auditoria real |
| IA | Claude API (Opus, Sonnet, Haiku) com saídas estruturadas, prompt caching e Batch API para lotes | qualidade e custo |
| Banco | PostgreSQL 16 + pgvector | dados relacionais + memória vetorial |
| Arquivos | Armazenamento local na VPS com MinIO (compatível S3) | prints, PDFs, áudios |
| E-mail | Gmail/Google Workspace (caixas de prospecção) ou provedor dedicado de cold e-mail; webhook de respostas | entrega e leitura |
| Agenda | Google Calendar API | reuniões |
| Dados B2B | Apollo.io API | empresas, pessoas, vagas, visitantes |
| PDF | HTML + WeasyPrint | propostas e relatórios com qualidade gráfica |
| Voz (simulador) | TTS de mercado (via API) | simulador de leitor de tela no microsite |
| Proxy reverso | Caddy (HTTPS automático) ou Traefik | simplicidade |
| Observabilidade | Logs estruturados + Grafana/Prometheus (ou Uptime Kuma + Sentry) | saúde e custos |
| CI/CD | GitHub Actions → build de imagens → deploy por SSH na VPS | automação de deploy |

### 16.2 Infraestrutura na Hostinger
- **VPS recomendada:** mínimo KVM 4 (4 vCPU, 16 GB RAM); Playwright e Lighthouse consomem memória. Escalar para KVM 8 com volumes acima de ~500 auditorias/dia.
- **Serviços Docker Compose:** `web`, `api`, `worker-audit` (com limite de concorrência), `worker-general`, `scheduler`, `postgres`, `redis`, `minio`, `caddy`, `n8n` (opcional), `monitoring`.
- **Subdomínios:** `app.` (painel, com login), `diagnostico.` (microsites públicos), `proposta.` (propostas web), `api.`.
- **Segurança:** firewall liberando apenas 80/443/SSH (SSH por chave, porta alterada, fail2ban), segredos em `.env` fora do repositório (GitHub Secrets no CI), atualizações automáticas de segurança.
- **Backups:** dump diário do Postgres + MinIO para armazenamento externo, com retenção de 30 dias e teste de restauração mensal.

### 16.3 Fluxo de deploy
```
push na branch main → GitHub Actions: lint + testes + testes de acessibilidade do painel (axe)
  → build das imagens → publicação no GitHub Container Registry
  → SSH na VPS → docker compose pull && docker compose up -d → migrações → health check
  → rollback automático se o health check falhar
```

---

## 17. Modelo de dados (entidades principais)

```
empresas        (id, nome, dominio, cnpj, setor, porte, cidade, uf, fonte, score, estado, criado_em)
dossies         (id, empresa_id, dados_json, resumo, sinais_json, versao, criado_em)
auditorias      (id, empresa_id, nota, totais_json, achados_json, paginas_json, artefatos_urls, criado_em)
contatos        (id, empresa_id, nome, cargo, area, email, email_status, linkedin_url, telefone, opt_out)
campanhas       (id, nome, icp_json, sequencia_json, nivel_autonomia_json, ativa)
mensagens       (id, contato_id, campanha_id, canal, direcao, assunto, corpo, variante, status,
                 nota_critico_json, aprovado_por, enviado_em)
eventos         (id, empresa_id, contato_id, tipo, origem, dados_json, ocorrido_em)   ← linha do tempo
microsites      (id, empresa_id, slug, expira_em, metricas_json)
propostas       (id, empresa_id, versao, escopo_json, valor, status, pdf_url, web_url, criado_em)
acoes_agentes   (id, agente, empresa_id, entrada_hash, saida_json, raciocinio, modelo,
                 tokens_in, tokens_out, custo, duracao_ms, criado_em)                ← auditoria de IA
supressao       (id, email, dominio, motivo, criado_em)
memoria_vetorial(id, tipo, conteudo, embedding, metadados_json)  ← mensagens vencedoras, base regulatória
usuarios        (id, nome, email, papel)
config          (chave, valor_json)   ← ICP, pesos, preços, limites, guia de voz
```

---

## 18. Estrutura do repositório e convenções

```
sl-prospecta/
├── CONSTITUICAO.md            ← este documento
├── CLAUDE.md                  ← instruções curtas para agentes de código (resumo deste doc)
├── README.md
├── docker-compose.yml
├── .github/workflows/         ← ci.yml, deploy.yml
├── apps/
│   ├── web/                   ← Next.js (painel, microsite, proposta web)
│   └── api/                   ← FastAPI (rotas, governança, webhooks)
├── workers/
│   ├── orchestrator/          ← máquina de estados
│   ├── agents/                ← um módulo por agente (§6)
│   ├── audit/                 ← Playwright, axe, Lighthouse, teclado, simuladores
│   ├── outreach/              ← envio, leitura de respostas, agendamento
│   └── documents/             ← relatórios e propostas (HTML → PDF)
├── packages/
│   ├── prompts/               ← prompts versionados (.md) por agente
│   ├── schemas/               ← esquemas JSON compartilhados
│   └── knowledge/             ← base regulatória e biblioteca de objeções
├── templates/                 ← modelos visuais de relatório, microsite e proposta
├── infra/                     ← Caddyfile, scripts de backup, configuração da VPS
├── docs/
│   ├── compliance/            ← LIA, política de privacidade, retenção
│   └── decisoes/              ← ADRs (registros de decisão arquitetural)
└── tests/                     ← unitários, integração, avaliações de IA (evals)
```

**Convenções:**
- Código e nomes técnicos em inglês; textos de interface, prompts de cliente e documentação em português.
- **Prompts são código:** versionados em `packages/prompts`, com testes de avaliação (evals) — um conjunto de 30 prospects de referência com saídas esperadas. Nenhuma alteração de prompt vai para produção sem rodar os evals.
- Todo agente tem: esquema de entrada, esquema de saída, prompt, eval e limite de custo por execução.
- Commits no padrão Conventional Commits; PRs pequenos; branch `main` protegida.

---

## 19. Roteiro de construção (fases)

| Fase | Duração estimada | Entregas | Critério para avançar |
|---|---|---|---|
| **0 — Fundação** | 1 semana | Repositório, Docker Compose, CI/CD, VPS configurada, autenticação, banco | Deploy automático funcionando |
| **1 — Auditor + Pesquisador** | 2 semanas | Entrada por nome/URL, dossiê, auditoria completa, mini-relatório PDF | 20 auditorias revisadas por Marcos com ≥ 90% de achados corretos |
| **2 — Qualificação + Decisores + Lote** | 1–2 semanas | Score, Apollo, upload de planilha, CRM Kanban básico | Lote de 100 empresas processado sem erro |
| **3 — Abordagem (L1/L2)** | 2 semanas | Estrategista, Redator, Crítico, Caixa de Aprovação, envio com limites, supressão, domínio aquecido | 50 e-mails aprovados com < 20% de edição |
| **4 — Conversa + Agenda + Linha do tempo** | 2 semanas | Leitor de Respostas, Agendador, eventos unificados, dashboard | Primeiras reuniões agendadas pela plataforma |
| **5 — Microsite disruptivo** | 2 semanas | Microsite com simulador de leitor de tela, simuladores visuais, vídeo de teclado, antes/depois, score de intenção em tempo real | Taxa de visita ao microsite ≥ 25% dos abordados |
| **6 — Proposta automática** | 1–2 semanas | Propositor, modelos visuais, proposta web rastreada | Proposta gerada em < 5 min, aprovada com ajustes mínimos |
| **7 — Autonomia e aprendizado** | contínuo | Caçador autônomo, experimentos, Analista, briefing diário, promoção de níveis | Operação em L3 na maioria das etapas |
| **8 — Expansão** | futuro | Multi-idioma (espanhol) para Accessibility Total (LATAM), multiempresa (white-label para parceiros) | Decisão estratégica |

> Sugestão de ordem: comece pelas Fases 1 e 5 em versão simples — o **relatório real + microsite** é o que diferencia a Sinal Link no mercado e pode até ser usado manualmente pelo vendedor antes de toda a automação ficar pronta.

---

## 20. Métricas de sucesso, custos e emendas

### 20.1 Metas iniciais (revisar após 60 dias)
- Tempo da entrada (URL) até mensagem pronta: **< 10 minutos**.
- Precisão de achados da auditoria (validação humana amostral): **≥ 90%**.
- Taxa de resposta positiva no primeiro contato: **≥ 5%** (referência de mercado para cold e-mail costuma ficar abaixo disso).
- Visitas ao microsite: **≥ 25%** dos abordados.
- Reuniões por 100 prospects qualificados: **≥ 3**.
- Bounce < 2%; reclamações de spam < 0,1%.

### 20.2 Controle de custos
- Teto de custo por prospect configurável (meta inicial: até R$ 2,50 em IA + dados por prospect totalmente processado; ajustar com dados reais).
- Haiku para triagem, Sonnet para análise, Opus apenas para estratégia, redação e proposta.
- Prompt caching do guia de voz e da base regulatória; Batch API para lotes não urgentes.
- Auditoria completa só para prospects que passam por uma pré-triagem barata (fit básico de ICP).
- Painel de custos por agente, por campanha e por reunião gerada.

### 20.3 Emendas a esta Constituição
- Alterações nos **Princípios (§2)** e **Conformidade (§15)** exigem aprovação explícita do Diretor-Geral e registro em `docs/decisoes/`.
- Demais seções podem ser atualizadas via Pull Request revisado, com changelog no fim deste documento.
- O Analista pode **propor** emendas (ex.: novos pesos de score), nunca aplicá-las sozinho nesta Constituição.

---

## 21. Anexos

### 21.1 Prompt-base do Redator (resumo)

```
Você é redator(a) sênior da Sinal Link Acessibilidade, consultoria brasileira de
tecnologia assistiva e acessibilidade digital. Escreva o primeiro e-mail para
{nome}, {cargo} na {empresa} ({setor}).

DADOS VERIFICADOS (use apenas estes fatos):
- Dossiê: {resumo_dossie}
- Achado principal: {achado.titulo} — impacto: {achado.impacto_humano} — página: {achado.pagina}
- Ângulo escolhido pelo Estrategista: {angulo}
- Link do diagnóstico: {url_microsite}

REGRAS:
- Máx. 120 palavras; assunto em minúsculas, até 6 palavras, específico.
- Estrutura: observação específica → achado com impacto humano → ponte com a área
  do decisor → oferta do diagnóstico gratuito → pergunta leve.
- Tom consultivo, gentil, direto. Português do Brasil.
- Proibido: prometer conformidade total, "100% acessível", urgência artificial,
  elogios genéricos, emojis, mais de um link.
- Termine com assinatura de {remetente} e linha de descadastro.

SAÍDA (JSON): {"assunto": "...", "corpo": "...", "fatos_usados": [...], "angulo": "..."}
```

### 21.2 Variáveis de ambiente (`.env.example`)

```
ANTHROPIC_API_KEY=
APOLLO_API_KEY=
DATABASE_URL=postgresql://...
REDIS_URL=redis://redis:6379
MINIO_ENDPOINT= / MINIO_ACCESS_KEY= / MINIO_SECRET_KEY=
GOOGLE_OAUTH_CLIENT_ID= / GOOGLE_OAUTH_CLIENT_SECRET=
OUTREACH_MAILBOXES=           # lista de caixas de prospecção
TTS_API_KEY=
APP_BASE_URL=https://app.sinallink.com.br
MICROSITE_BASE_URL=https://diagnostico.sinallink.com.br
DAILY_AI_BUDGET_BRL=
DAILY_SEND_LIMIT_PER_MAILBOX=40
```

### 21.3 Critérios de aceite da v1 (MVP)

- [ ] Digitar "Hospital Exemplo" ou `hospitalexemplo.com.br` gera, sem outra intervenção, dossiê + auditoria + score + decisores + rascunho de e-mail + microsite.
- [ ] Upload de planilha com 100 linhas é mapeado, deduplicado e processado em lote, com progresso visível.
- [ ] Mini-relatório PDF e microsite passam em verificação automática de acessibilidade (axe) sem erros críticos.
- [ ] Nenhum e-mail sai sem passar pelo Crítico e pela lista de supressão.
- [ ] Respostas recebidas aparecem classificadas na linha do tempo em até 5 minutos.
- [ ] Kanban permite mover cartões, assumir conversa e pausar a IA por prospect e globalmente.
- [ ] Dashboard mostra funil, custos e briefing diário.
- [ ] Proposta em PDF e web é gerada a partir das anotações da reunião usando apenas preços da tabela.
- [ ] Todas as ações de agentes ficam registradas com modelo, custo e raciocínio resumido.
- [ ] Disjuntores de bounce, spam e custo testados e funcionando.

---

### Changelog
- **1.0 (23/10/2026)** — Versão inicial da Constituição.
