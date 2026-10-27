# ADR 0010 — Upload de planilha para prospecção em lote (Fase 2, Tarefa 3)

**Data:** 27/10/2026 · **Status:** aceita

## Contexto
O §7.2 (entrada 2) pede upload de `.xlsx` ou `.csv`, com a IA identificando sozinha as colunas (empresa, site,
CNPJ, cidade, contato), prévia para confirmação e deduplicação por domínio e CNPJ. O §12.1 pede a área de
arrastar e soltar no Painel de Prospecção, e o critério da Fase 2 é um lote de 100 empresas processado sem erro,
com progresso visível.

## Decisões
1. **Fluxo em duas etapas:** envio → prévia → confirmação humana. Nada é cadastrado nem processado antes da
   confirmação; cancelar descarta tudo.
2. **Leitura na API** (`apps/api/app/planilha.py`): `.csv` (UTF-8 com ou sem BOM, Windows-1252 ou Latin-1;
   `,`, `;` ou tabulação) e `.xlsx` (só a 1ª aba, valores, não fórmulas, via `openpyxl`). Limites de 5 MB,
   1.000 linhas e 50 colunas; `.xlsx` com macro ou acima de 50 MB descompactados é recusado. Linhas em branco
   no meio contam para a numeração, para a prévia citar a linha que o vendedor vê no Excel.
3. **Mapeamento de colunas:** primeiro por regras sobre o nome do cabeçalho (e pelo conteúdo, para achar a
   coluna de sites). Se faltar a coluna da empresa ou a do site, o worker chama o Haiku (`mapear_colunas_lote`)
   só com os cabeçalhos e até 3 exemplos por coluna, com e-mails mascarados. As regras prevalecem; a IA só
   completa. Sem fila, sem orçamento ou com falha da IA, a prévia segue com as regras e um aviso; o vendedor
   sempre pode ajustar cada campo.
4. **Classificação de cada linha:** nova, já cadastrada (domínio ou CNPJ já no banco), repetida na planilha ou
   inválida (sem nome e sem site legível). CNPJ com dígito errado, UF desconhecida e e-mail malformado viram
   **avisos**: o dado é ignorado e a empresa entra, para um erro de digitação não descartar uma empresa válida.
5. **Linhas guardadas só até a decisão:** as linhas da planilha ficam em `lotes.linhas_json` e são apagadas na
   confirmação ou no cancelamento; fica só o resumo (contagens e linhas ignoradas com o motivo). O arquivo em
   si não é guardado (nem no MinIO). Coleta mínima, §15.1.
6. **Na confirmação:** as empresas novas entram com `fonte = "lote"` e `lote_id`, ganham o evento
   `entrada_recebida` com o número da linha e vão para a fila. A empresa já cadastrada recebe o evento
   `entrada_duplicada` e não é duplicada. Contato da planilha vira `contatos` com `fonte = "planilha"` e
   e-mail **não verificado** (webmail descartado); o Mapeador segue normalmente.
7. **Progresso:** calculado na hora a partir do estado das empresas do lote (na fila, pesquisando, auditando,
   qualificadas, com decisores) e do último evento de cada uma (problemas como site ilegível ou falha). O lote
   aparece como concluído quando nenhuma empresa está mais em pesquisa ou auditoria.
8. **Estimativa na prévia:** R$ 1,00 de IA e até 4 créditos do Apollo por empresa nova, e quantos dias o lote
   leva com os tetos diários atuais. A fila respeita os disjuntores sozinha.
9. **Permissões:** admin e vendedor enviam, ajustam, confirmam e cancelam; leitura só vê.

## Consequências
- O critério da Fase 2 (100 empresas) leva alguns dias com os tetos padrão; aumentar `DAILY_AI_BUDGET_BRL` e
  `APOLLO_DAILY_CREDIT_CAP` na VPS acelera sem mudar código.
- A Batch API (§16.1), que barateia lotes não urgentes, fica como otimização futura.
