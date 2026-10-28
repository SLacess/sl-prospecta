# ADR 0013 — Busca web do Mapeador com o Haiku

**Data:** 28/10/2026 · **Status:** aceita

## Contexto
A busca web do Mapeador (`mapeador-web` e `mapeador-nomes`) era o item mais caro por empresa no mapeamento.
Em produção, 30 chamadas no Sonnet custaram em média **R$ 0,63** cada, com **~37 mil tokens de entrada**: quase
tudo é o conteúdo dos resultados de busca que o modelo lê. A taxa da busca (US$ 0,01 por busca) pesa pouco. No
teste de 5 universidades pelo caminho do Apify (ADR 0012), a busca web foi ~R$ 1,04 por empresa de R$ 1,05.

## Decisões
1. **Modelo próprio para a busca web do Mapeador:** `MODEL_WEB_SEARCH`, padrão `claude-haiku-5-5` (1/20 do preço
   de entrada do Sonnet na tabela do projeto). Vale para os dois caminhos (Apollo e alternativo). Configurável no
   `.env`; voltar ao Sonnet não exige mudar código (CLAUDE.md: modelos nunca fixos no código de negócio).
2. **As travas não mudam:** a fonte precisa estar entre as URLs da busca, LinkedIn não vale como fonte, e o nome
   completo precisa bater com a abreviação do Apollo. Elas independem do modelo e barram nome inventado.
3. **Pesquisador fica no Sonnet** por ora: mexer nele afeta a qualidade do dossiê e é decisão separada.
4. **Estimativa:** o `decisores --listar` mostra também o custo do caminho alternativo (~R$ 0,40 por empresa).

## Validação
Teste comparativo local, antes de adotar, nas mesmas empresas que já tinham resultado com o Sonnet:
ver a seção "Resultado do teste" abaixo.

## Resultado do teste (28/10/2026, ambiente local, Apollo sem créditos)
| Universidade | Sonnet (produção) | Haiku (local) |
|---|---|---|
| Univali | 1 contato válido (Gerente de TI) | **2 válidos** (o mesmo + Diretor Executivo de Pessoas, Processos e Tecnologia) |
| Unicamp | Diretor de TI, e-mail catch-all | o mesmo nome, e-mail catch-all |
| UFSC | ninguém | **Secretário de TI achado** (site da SETIC), mas nenhum e-mail entregável |
| UnB | ninguém | ninguém |
| Feevale | ninguém | ninguém |
| **Custo total** | **R$ 5,21** | **R$ 0,57** |

Nenhum nome inventado: todos com fonte pública na busca e conferidos pelas travas. O Haiku achou tudo o que o
Sonnet achou e mais. Ponto de atenção: em algumas chamadas do Haiku o uso devolvido pela API não trouxe buscas
contadas (custo ~R$ 0,02 com ~28 mil tokens). Se a cobrança real incluir essas buscas, o teste custaria até
~R$ 2,10, ainda ~60% abaixo do Sonnet. Conferir no console da Anthropic após o primeiro lote.

## Consequências
- Custo esperado da busca web: ~R$ 0,19 por chamada (antes R$ 0,63), ~70% a menos.
- Se a qualidade cair em produção, basta `MODEL_WEB_SEARCH=claude-sonnet-5-5` no `.env` e reiniciar o worker.
