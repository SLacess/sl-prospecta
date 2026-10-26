# ADR 0007 — Ferramenta de revisão para o critério da Fase 1

**Data:** 25/10/2026 · **Status:** aceita

## Contexto
O §19 só libera a Fase 2 depois que "20 auditorias [forem] revisadas por Marcos com ≥ 90% de achados
corretos". O Guia acrescenta: setores diferentes, conferência manual de cada achado (ex.: extensão WAVE) e
nenhum texto prometendo conformidade total. A medição precisa ser registrada, não feita de cabeça.

## Decisões
1. **Tabela `revisoes_achados`** (migração 0003, só aditiva).
   - Cada linha guarda auditoria, empresa, tipo (`achado_leigo`, `problema_tecnico` ou `honestidade`),
     chave do problema, veredito (`correto`, `parcial` ou `incorreto`), motivo, revisor e datas.
   - Há uma linha por item, e salvar de novo atualiza a mesma linha.
   - Os motivos ficam guardados para o Analista (§14.3).
2. **O que entra nos 90%:**
   - os **3 achados para leigos**, obrigatórios, porque é o que vai para o cliente;
   - os **problemas técnicos que o admin revisar**, opcionais;
   - "parcial" conta meio acerto.
   - Motivo é obrigatório em tudo que não estiver correto.
3. **Critério atingido** quando, ao mesmo tempo:
   - há **20 auditorias com revisão completa** (os 3 achados e a checagem de honestidade);
   - elas vêm de **pelo menos 4 setores**;
   - os acertos estão em **≥ 90%**;
   - **nenhuma** auditoria foi marcada com promessa de conformidade total ou "100% acessível".

   O mínimo de 4 setores é uma interpretação de "setores diferentes" do Guia e pode ser ajustado.
4. **Só o perfil admin revisa** ("revisadas por Marcos"). Vendedor e leitura veem o placar.
5. **Telas:**
   - a seção "Revisão da auditoria" na Ficha do Prospect, só para admin, com um grupo de opções por item
     e o campo de motivo;
   - a tela "Revisão da Fase 1", com o placar em texto, as pendências e a lista de auditorias com link
     para cada ficha.
6. **A entrada em lote continua na Fase 2.** Os 20 sites são prospectados pelo painel ou enfileirados com
   aprovação, sem antecipar a planilha.

## Consequências
- O fim da Fase 1 passa a ser verificável no próprio painel. Quando o placar marcar "Critério atingido", a
  linha "Fase atual" do CLAUDE.md muda para a Fase 2.
- Achados marcados como incorretos ou parciais, com o motivo, são a base para recalibrar a fórmula da nota e
  as regras do Auditor.

## Resultado (26/10/2026)
Critério atingido: 20 auditorias revisadas por Marcos, de 4 setores, com **92,2%** de acertos e nenhuma promessa
de conformidade total.

| Item | Correto | Parcial | Incorreto |
|---|---|---|---|
| Achados para leigos | 48 | 6 | 6 |
| Problemas técnicos | 61 | 1 | 0 |
| Checagem de honestidade | 20 | 0 | 0 |

Os achados para leigos, que vão para o cliente, ficaram em **85%** (parcial vale meio). Os erros se concentram em:
- **Teste de teclado** (5 de 12): modal ou banner de cookies que prende o foco de propósito e devolve com
  "Fechar" foi lido como armadilha; "sem indicador de foco" generalizou poucos elementos para o site inteiro.
- **Local do problema** (2): o problema existe, mas numa página ou subdomínio diferente do que o texto diz.
- **Falso positivo do axe ou conteúdo que mudou** (5): nome de botão ou link, contraste e estrutura de lista que
  não se confirmaram na conferência manual.

Recalibrar essas regras do Auditor fica registrado como pendência antes de a abordagem usar os achados (Fase 3).
