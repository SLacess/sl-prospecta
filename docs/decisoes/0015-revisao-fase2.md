# ADR 0015 — Critério da Fase 2 atingido

**Data:** 18/11/2026 · **Status:** aceita

## Contexto
O critério de saída da Fase 2 (CLAUDE.md, Guia §19): "uma planilha de 100 empresas processada sem erro,
com score e decisores coerentes na avaliação de Marcos." A revisão qualitativa foi feita na própria planilha
`revisao-fase2-lote-100.xlsx` (colunas "Score coerente?"/"Decisores coerentes?"), fora do painel — a Fase 2
não teve uma tela de revisão dedicada como a `revisoes_achados` da Fase 1 (ADR 0007).

## Resultado (18/11/2026)
- **Processamento técnico:** das 100 empresas do lote, 99 chegaram a um estado final sem erro de sistema.
  A única exceção é a BTG Pactual, bloqueada pelo `robots.txt` do próprio site — comportamento correto do
  Auditor (CLAUDE.md regra 7), não um erro, aceito como estado final (ver histórico da investigação do lote).
  Dois bugs reais no Auditor (links `<a>` dentro de SVG virando dict; navegação no meio do teste de teclado)
  foram corrigidos e confirmados num reenvio real antes deste resultado.
- **Distribuição final do lote:** 29 em `PREPARANDO_ABORDAGEM` (decisor válido encontrado), 70 em
  `MAPEANDO_DECISORES` (busca completa, sem e-mail válido — resultado de negócio legítimo, não erro técnico,
  fica para o vendedor decidir manualmente) e 1 em `AUDITANDO` (BTG Pactual, exceção documentada acima).
- **Score e decisores coerentes:** confirmado por Marcos Alencar em conversa, com base na própria planilha
  de revisão. Nenhuma inconsistência entre a planilha e o banco de produção foi encontrada na checagem cruzada
  (score, faixa e decisores de cada linha batem com os dados reais).

**Critério atingido.** A linha "Fase atual" do CLAUDE.md passa para a Fase 3.

## Consequências
- A recalibração dos 70 casos sem decisor válido (se vale tentar de novo com mais créditos, ou se é um
  resultado aceitável do ICP) fica como pendência de produto, não bloqueia a Fase 3.
- A Fase 3 começa sem o Mensageiro automático (ADR 0014): a trilha comercial de e-mail/aquecimento não é
  mais pré-requisito bloqueante.
