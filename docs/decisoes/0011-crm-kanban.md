# ADR 0011 — CRM Kanban e mudança manual de estado (Fase 2, Tarefa 4)

**Data:** 27/10/2026 · **Status:** aceita

## Contexto
O §12.1 (item 2) pede um Kanban com colunas = estados do §7.1 e cartões com nome, score (cor + número + texto,
nunca só cor), nota de acessibilidade, próximo passo e responsável; arrastar o cartão é a mudança manual de estado,
registrada. O Guia pede também operar pelo teclado. O orquestrador já faz as transições automáticas e só muda uma
empresa se ela ainda estiver no estado esperado.

## Decisões
1. **Colunas:** os 16 estados do §7.1, na ordem do pipeline. As 4 colunas da Fase 3 (Em sequência, Sem resposta,
   Respondeu, Não interessado) aparecem recolhidas enquanto estão vazias. O quadro rola na horizontal e empilha as
   colunas em telas estreitas (§12.2). Até 200 cartões por coluna; os filtros (busca por nome ou site, setor,
   faixa, "só as minhas") reduzem o resto.
2. **Mudanças manuais permitidas** (`apps/api/app/crm.py`):

   | De | Para | Motivo |
   |---|---|---|
   | qualquer estado, menos Arquivado e Ganho | Arquivado | obrigatório |
   | Arquivado | Qualificando (reabrir) | opcional |
   | Qualificando | Mapeando decisores (seguir com uma empresa fria) | opcional |
   | Preparando abordagem e estados da Fase 3 | Reunião agendada | opcional |
   | Reunião agendada | Proposta enviada | opcional |
   | Proposta enviada | Negociação, Ganho ou Perdido | Perdido: obrigatório |
   | Negociação | Ganho ou Perdido | Perdido: obrigatório |

   Não são destino manual: Novo, Pesquisando e Auditando (passos do sistema), Preparando abordagem (exige contato
   verificado; quem leva é o Mapeador) e os estados da Fase 3 (dependem do envio de mensagens).
3. **Registro:** toda mudança manual vira o evento `estado_alterado_manual` (origem humano) com quem, de onde, para
   onde e o motivo. A API grava só se a empresa ainda estiver no estado de origem que o painel mostrou; senão
   responde 409 e o painel recarrega o quadro.
4. **Interação:** arrastar com o mouse (HTML5) e, como alternativa de teclado e de um clique só (WCAG 2.5.7), o
   botão "Mover…" em cada cartão, que abre um diálogo nativo (`<dialog>`) só com os destinos permitidos. Destino
   com motivo obrigatório abre o diálogo também ao soltar. Depois de mover, o painel anuncia a mudança e o foco
   volta ao botão do cartão, já na coluna nova.
5. **Cartão:** score como "74 · Quente" (a borda colorida só reforça), nota de acessibilidade, próximo passo em texto
   (calculado do estado, da faixa, dos contatos válidos e do último evento) e responsável. O alerta "precisa de
   atenção" usa a mesma regra da tela de lotes (módulo comum).
6. **Ficha:** botão "Mudar estado…" com o mesmo diálogo (cobre o "Descartar" do §12.1). **Funil** da tela inicial
   passa a mostrar números reais.
7. **Permissões:** admin e vendedor movem; leitura só vê.

## Consequências
- Sem migração e sem IA.
- "Assumir conversa" e "Pausar a IA" (checklist do §19) ficam para a Fase 3, junto das conversas.
