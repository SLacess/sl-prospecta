# ADR 0004 — Auditor técnico (Fase 1, Tarefa 3)

**Data:** 25/10/2026 · **Status:** aceita

## Contexto
A Etapa 2 do pipeline (§7.3) audita a acessibilidade real do site com Playwright e axe-core (§8.1),
seguindo as regras de raspagem do §8.4. O Chromium consome memória (§16.2), e o resultado precisa ser
honesto sobre o alcance dos testes automáticos (§2.2).

## Decisões
1. **Serviço separado `worker-audit`:**
   - Imagem `mcr.microsoft.com/playwright/python:v1.64.1-noble`, a mesma versão do Playwright do painel.
   - Fila própria (`arq:queue:auditoria`), no máximo 2 auditorias ao mesmo tempo, `shm_size` de 1 GB e
     limite de 3 GB de memória em produção.
   - O worker principal só enfileira; ele nem instala o navegador.
2. **Estados:** o orquestrador leva a empresa de PESQUISANDO para AUDITANDO quando o dossiê fica pronto
   e enfileira a auditoria. A empresa **fica em AUDITANDO** com o resultado bruto. A nota 0–100, os
   achados para leigos (§8.2) e a passagem para QUALIFICANDO entram com o Auditor com IA (Tarefa 4).
   O Guia sugeria QUALIFICANDO já aqui, mas a auditoria só está completa com a Tarefa 4.
3. **O que é testado em cada página** (home + até 4 páginas-chave: contato, produto/curso, login/portal,
   carrinho/checkout, trabalhe conosco):
   - axe-core 4.14.0 com as tags WCAG 2.0/2.1/2.2 A e AA. É a mesma versão dos testes do painel; ela é
     baixada no build e conferida pelo hash SHA-512.
   - Teclado, com até 40 Tabs:
     - link "pular para o conteúdo" como primeiro foco;
     - indicador de foco aparente (contorno ou sombra no estilo calculado);
     - armadilha de foco: 12 paradas seguidas presas em até 3 elementos, havendo outros focáveis.
   - Tela de 320 px (WCAG 1.4.10): rolagem horizontal e quais elementos estouram.
   - Prints desktop e de 320 px no MinIO, em `artefatos/auditorias/<empresa>/<auditoria>/`. O bucket é
     privado; os prints só aparecem na ficha e no relatório (Tarefa 5).
   - Plugin de acessibilidade já instalado, pela assinatura de scripts e variáveis globais: UserWay,
     accessiBe, EqualWeb, Hand Talk, VLibras, AudioEye, Recite Me, Equally AI, Rybená e Sinal Link.
4. **Regras de raspagem (§8.4):**
   - `robots.txt` é conferido antes de cada página, com o mesmo leitor do Pesquisador.
   - **1 abertura de página por segundo por domínio**, com a mesma trava no Redis. Os recursos que a
     página carrega (CSS, imagens, scripts) vêm normalmente; sem eles o site não renderiza e o teste não
     vale. Essa é a interpretação do "1 req/s" para um navegador.
   - Nada é clicado, preenchido ou enviado: as páginas de login e de checkout são só abertas.
   - 45 s por página e 6 min por auditoria.
5. **Proteção contra SSRF no navegador:** todas as requisições de todas as páginas passam por um filtro
   (`context.route`). Só saem `http(s)` para hosts com IP público; `data:` e `blob:` são liberados. Assim,
   uma página não consegue fazer o navegador acessar Postgres, Redis, MinIO ou o endereço de metadados da
   nuvem. Um teste confirma que o servidor "interno" do site de exemplo não recebe nenhuma requisição.
6. **Resultado:**
   - Cada página traz as violações do axe (regra, gravidade com os nomes do §8.2, critérios WCAG,
     ocorrências e até 3 exemplos de HTML), o teclado, o resultado em 320 px e os prints.
   - `totais_json` conta 1 problema por regra violada em cada página, separado por gravidade.
   - `nota` e `achados_json` ficam vazios até a Tarefa 4.
7. **Retomada:** quem ficou parado no meio do pipeline numa mudança de versão volta à fila com
   `python -m slp_workers.cli retomar` (no contêiner do worker) ou ao ser reenviado pelo painel. Isso
   inclui as empresas com dossiê de antes desta tarefa.
8. **Fora desta tarefa** (o Guia não pede): Lighthouse, zoom de 200% e as camadas com IA do §8.1 (visual
   e semântica). As camadas com IA entram na Tarefa 4.

## Consequências
- A auditoria não usa IA, então não tem custo de API. O custo é de CPU e memória na VPS.
- O indicador de foco é aferido pelo estilo calculado; um foco indicado só por mudança de cor de fundo
  aparece como "não aparente". A Tarefa 4 e a revisão humana das 20 auditorias da Fase 1 calibram esse
  ponto.
- Sites que bloqueiam robôs ou só funcionam com login não são auditados; a linha do tempo explica o motivo.
