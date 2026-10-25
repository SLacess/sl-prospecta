# ADR 0005 — Auditor com IA: nota, achados para leigos e plugin × código (Fase 1, Tarefa 4)

**Data:** 25/10/2026 · **Status:** aceita

## Contexto
O §8.2 define a saída do Auditor: nota 0–100, os 3 achados explicados para leigos, a separação obrigatória
entre o que o plugin resolve parcialmente e o que exige ajuste no código, e uma observação de honestidade.
O ADR 0004 deixou para esta tarefa as camadas com IA do §8.1 (visual e semântica). Tudo o que for dito ao
prospect precisa ser verdadeiro (§2.1, §2.2, §15.3).

## Decisões
1. **Divisão de trabalho:** a IA escolhe e explica os achados; regras fixas cuidam do que precisa ser
   reproduzível ou honesto.
   - Os problemas vêm agrupados por tipo: regra do axe ou verificação própria (`teclado:`, `responsivo:`,
     `semantica:`). Uma regra que aparece em várias páginas conta uma vez.
   - **Nota por fórmula** (`slp_workers/audit/regras.py`, versão 1.0):
     - parte de 100 e desconta por problema: crítico −12, grave −6, moderado −3, leve −1;
     - soma −1 por página adicional em que o mesmo problema aparece;
     - fica entre 0 e 100;
     - cada desconto é gravado em `descontos_nota`, então a nota é explicável;
     - os pesos podem ser recalibrados depois (§14.6), com nova versão.
   - Gravidade das verificações próprias:
     - armadilha de foco: crítico;
     - foco sem indicador visível: grave;
     - falta do link "pular conteúdo": moderado;
     - rolagem lateral em 320 px: grave;
     - links genéricos: moderado;
     - salto de título: leve.
2. **Plugin × código por tabela revisada por humanos:** a classificação vem de
   `packages/knowledge/plugin-sinal-link.json`, versionado e alterado só por PR. Problema fora da tabela vai
   para "exige ajuste no código": nunca prometemos o que o plugin não faz. A tabela inicial é conservadora e
   **precisa ser conferida pela equipe da Sinal Link**.
3. **Achados para leigos com Claude Sonnet 5.5** (`MODEL_ANALYSIS`, esforço médio, saída estruturada):
   - **Entrada:** a lista de problemas (com critérios WCAG e até 2 exemplos de HTML) e até 3 prints desktop,
     lidos do MinIO pelo worker principal.
   - **Conferência pelo orquestrador**, como no Pesquisador:
     - achado com problema ou página que não existem no resultado bruto é descartado;
     - trecho de HTML que não é um exemplo real do axe é apagado;
     - no máximo 3 achados, sem repetição.
   - **Honestidade (§2.2):** todo texto gerado passa por um filtro de frases proibidas ("100% acessível",
     "totalmente acessível", "garante conformidade", "resolve todas as barreiras"…). Uma violação gera uma
     nova tentativa com aviso; a segunda vira falha registrada (`analise_falhou`), com o gasto em
     `acoes_agentes`.
4. **Camada visual:** o mesmo modelo, com os prints, aponta indícios que o axe não pega (texto em imagem,
   informação só por cor, CAPTCHA visual, vídeo sem legenda aparente). São **indícios a confirmar**: aparecem
   assim no painel e **não entram na nota**.
5. **Camada semântica sem IA:** o Auditor técnico passa a coletar links genéricos ("clique aqui", "saiba
   mais"…) e saltos na hierarquia de títulos. Vale para as auditorias novas; as anteriores são analisadas com
   o que já têm.
6. **Fluxo e estados:**
   - O `worker-audit` termina a auditoria técnica e devolve a empresa à fila principal (`processar_empresa`).
   - O orquestrador vê AUDITANDO com auditoria sem nota, roda o Auditor com IA, grava o JSON do §8.2 em
     `auditorias.achados_json` e a nota em `auditorias.nota`, e passa a empresa para **QUALIFICANDO**, onde
     ela espera o Qualificador da Fase 2.
   - A retomada (`retomar` e reenvio pelo painel) passa a olhar só o estado: NOVO, PESQUISANDO e AUDITANDO
     ainda têm etapa pendente.
7. **Esquema publicado** em `packages/schemas/auditoria.schema.json`, gerado do modelo Pydantic e conferido
   por teste.
8. **Os prints continuam privados:** a API devolve a análise sem os endereços `s3://`; prints e PDF entram
   na Tarefa 5.

## Consequências
- Custo de cerca de R$ 0,30 a R$ 0,50 por análise. Somado à pesquisa, fica perto de R$ 1,20 por empresa,
  abaixo da meta de R$ 2,50 do §20.2.
- A nota é comparável entre empresas e ao longo do tempo enquanto a fórmula não mudar. Quando mudar, a
  `versao_nota` gravada diz qual fórmula foi usada.
- O critério da Fase 1 (20 auditorias revisadas, ≥ 90% de achados corretos) passa a medir os achados desta
  tarefa.
