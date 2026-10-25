# ADR 0003 — Pesquisador: domínio, leitura do site e custo de IA (Fase 1, Tarefa 2)

**Data:** 25/10/2026 · **Status:** aceita

## Contexto
O Pesquisador (§6, §7.3 Etapa 1) monta o dossiê de cada empresa. A entrada pode ser só o nome (§7.2), e a
leitura do site precisa seguir o §8.4: `robots.txt`, 1 requisição por segundo, user-agent identificado,
somente páginas públicas. Toda ação de IA vai para `acoes_agentes` com o custo (§2.7). Pelo §15.3, todo dado
citado precisa ter fonte rastreável.

## Decisões
1. **Domínio a partir do nome pela busca na web da própria Claude API** (`web_search_20260209`):
   - Não exige fornecedor nem chave nova.
   - O orquestrador só aceita domínios que apareceram nos resultados da busca, nunca um domínio "lembrado"
     pelo modelo.
   - Um único candidato com confiança alta é gravado direto. Nos outros casos a pesquisa para no evento
     `confirmacao_dominio` e o vendedor escolhe no painel (`POST /empresas/{id}/dominio`).
   - Se o domínio já pertence a outra empresa, nada é duplicado: a linha do tempo avisa.
2. **Leitura do site com httpx, sem navegador** (o navegador real é do Auditor, Tarefa 3):
   - Lê a home e até 5 páginas institucionais escolhidas por palavras-chave: sobre, ESG/inclusão, carreiras,
     produtos/serviços e contato.
   - Limites por página: 15 s e 2 MB, com o texto cortado em 12 mil caracteres.
   - Não segue redirecionamento para outro domínio.
   - Se o `robots.txt` responder com erro 5xx ou falhar na rede, o site não é lido (mesma postura dos
     buscadores). Se responder 404, o site está liberado.
   - O ritmo de 1 req/s por domínio usa uma trava no Redis com expiração de 1 s, que vale entre workers.
3. **Proteção contra SSRF:** antes de cada requisição, inclusive nos redirecionamentos, o host é resolvido e
   precisa ter só IPs públicos. Um domínio digitado que aponte para a rede interna da VPS é recusado.
   `WEB_ALLOW_PRIVATE_HOSTS` existe só para testes locais. Limitação conhecida: entre a checagem e a conexão
   o DNS pode mudar (*DNS rebinding*). O risco é aceito nesta fase; fixar a conexão no IP verificado fica
   como melhoria para o Auditor, que lê muito mais páginas.
4. **Dossiê com saída estruturada e fontes conferidas:**
   - Claude Sonnet 5.5 (`MODEL_ANALYSIS`), esforço médio, com saída estruturada pelo modelo Pydantic `Dossie`.
     O esquema é publicado em `packages/schemas/dossie.schema.json`, e um teste falha se ele divergir.
   - O orquestrador descarta menções, sinais e localização que citem uma página não lida e registra o
     descarte em `lacunas`.
   - O texto das páginas vai ao modelo marcado como dado de terceiros, e o prompt manda ignorar instruções
     contidas nele.
   - Os prompts ficam versionados em `packages/prompts/researcher*.md`.
5. **Recusa do modelo:** as chamadas usam `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`).
   Se o classificador de segurança recusar, a própria API refaz no modelo indicado, e o custo é calculado
   pelo modelo que respondeu. Desligável com `AI_REFUSAL_FALLBACK=false`.
6. **Custo em reais:**
   - Tokens × tabela de preços por modelo (`AI_PRICES_USD_PER_MTOK`), mais US$ 0,01 por busca na web,
     convertidos por `USD_BRL_RATE` (padrão 5,50).
   - Cache conta 10% na leitura e 125% na escrita.
   - Modelo fora da tabela é cobrado pelo preço mais alto, para nunca subestimar o disjuntor.
   - Ações que falham depois de gastar também são registradas.
   - Teto por empresa: `RESEARCH_COST_CAP_BRL` (R$ 2,00).
7. **Estados:**
   - O job leva a empresa de NOVO para PESQUISANDO e ela fica em PESQUISANDO com o dossiê pronto. A passagem
     para AUDITANDO entra com o Auditor (Tarefa 3).
   - O job roda com `keep_result=0`: o `job_id` fixo evita duplicata enquanto o job existe, e uma empresa em
     pesquisa sem dossiê (ex.: falhou) pode voltar à fila ao ser reenviada pelo painel.
8. **Fora desta tarefa:** Apollo (sem chave; entra na Fase 2), notícias e vagas externas, e a base
   regulatória (§8.5). O dossiê registra o que faltou em `lacunas`, sem estimar porte ou faturamento.

## Consequências
- Uma empresa custa cerca de R$ 0,40 (dossiê) mais R$ 0,50 (busca de domínio, só quando a entrada é o nome).
  O valor real fica em `acoes_agentes` e no aviso de custo do painel.
- Sites que bloqueiam robôs no `robots.txt` não geram dossiê; a linha do tempo explica o motivo.
- Os evals do Pesquisador (§18) entram com os 30 prospects de referência (Fase 3). Até lá, a revisão
  humana das 20 auditorias da Fase 1 cobre também os dossiês.
