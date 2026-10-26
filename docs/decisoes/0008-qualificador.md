# ADR 0008 — Qualificador por regra fixa (Fase 2, Tarefa 1)

**Data:** 26/10/2026 · **Status:** aceita

## Contexto
O §7.3 (Etapa 3) define o score composto
`0,30·Fit_ICP + 0,25·Intenção + 0,20·Gravidade + 0,15·Pressão regulatória + 0,10·Acesso ao decisor`,
com faixas Quente (≥ 70), Morno (45–69) e Frio (< 45), pesos ajustáveis no painel e recalibrados pelo Analista.
Os pesos e as faixas já estavam na `config` desde a migração 0001. Faltava dizer como cada componente vira um
número de 0 a 100 com os dados que existem hoje (dossiê e auditoria; o Apollo só chega na Tarefa 2).

## Decisões
1. **Regra fixa, sem IA.** O score sai de uma função determinística (`workers/slp_workers/agents/qualificador.py`,
   versão `regra-v1`). Custo zero, resultado reproduzível e fácil de recalibrar. A ação fica em `acoes_agentes`
   (agente `qualificador`, modelo `regra-v1`, custo 0), com saída Pydantic e `raciocinio_resumido` (§6).
2. **Componentes (0–100), com justificativa em texto:**
   - **Fit_ICP:** setor na lista do ICP = 60; atua no Brasil (UF ou domínio `.br`) = 20; porte ≥ `porte_minimo`
     = 20, desconhecido = 10 (neutro), menor = 0. O porte vem de `empresas.porte` (Apollo, Tarefa 2); o texto
     de `porte_indicios` do dossiê só aparece na justificativa, porque não diz o número de colaboradores.
   - **Intenção:** soma dos sinais do dossiê com teto de 100, pela tabela `config.sinais_pesos` (vaga PcD,
     relatório ESG, página de acessibilidade e app/portal valem 20; "outro" 10; menções a inclusão 10 cada, até 20).
     Os sinais de peso alto do §4.2 (TAC/MP, MEC, visitas ao site) ainda não são coletados e a justificativa diz isso.
   - **Gravidade das barreiras:** 100 − nota da auditoria.
   - **Pressão regulatória:** tabela por setor em `config.pressao_setor` (educação 90, utilities 80, saúde 75,
     financeiro 75, e-commerce 60, outros 40). Os valores são uma proposta inicial para Marcos conferir.
   - **Acesso ao decisor:** 0 até existir a tabela `contatos`; 100 com ao menos um contato de e-mail válido.
     Até lá, o score máximo possível é 90.
3. **Arredondamento meio para cima** (60,5 → 61), não o arredondamento para o par do Python.
4. **Estados (§7.1):** Quente e Morno passam de QUALIFICANDO para MAPEANDO_DECISORES, onde esperam o Mapeador.
   Frio fica em QUALIFICANDO; nada é arquivado automaticamente: o vendedor decide no Kanban (Tarefa 4).
   Recalcular nunca faz a empresa voltar de estado.
5. **Histórico:** tabela `qualificacoes` (migração 0004, só aditiva), uma linha por cálculo, com componentes,
   pesos usados e versão da regra; a mais recente vale e `empresas.score` guarda o número atual.
6. **Ordem no pipeline:** análise da auditoria → qualificação → mini-relatório. Uma configuração inválida gera o
   evento `qualificacao_falhou` e não impede o relatório. Empresas analisadas antes desta versão são pontuadas
   com `python -m slp_workers.cli qualificar --faltantes` (sem IA).
7. **Painel:** seção "Qualificação" na Ficha (score em número, faixa em texto, tabela dos 5 componentes) e a tela
   Configurações → Score, onde só o admin altera pesos (em %, somando 100) e faixas. Cada alteração vira o
   evento `config_score_alterada` com os valores de antes e depois. Pesos novos valem para as próximas
   qualificações; `qualificar --todas` recalcula as atuais.

## Consequências
- Todo score é explicável linha a linha, o que ajuda o vendedor a confiar no número e o Analista a recalibrar.
- Com o Acesso ao decisor em 0, poucas empresas chegam a Quente até a Tarefa 2; quando os contatos chegarem,
  o Mapeador deve chamar a requalificação.
- As tabelas `sinais_pesos` e `pressao_setor` são editáveis direto na `config`; a tela de Configurações cobre
  por enquanto só pesos e faixas.
