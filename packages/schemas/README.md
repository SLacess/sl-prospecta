# Esquemas

Esquemas JSON de entrada e saída de cada agente. Gerados a partir dos modelos Pydantic e validados pelo
orquestrador antes de persistir. Toda saída inclui `raciocinio_resumido` (CONSTITUICAO §6).

Esquemas publicados (gerados dos modelos Pydantic; os testes do worker falham se ficarem desatualizados):
- `dossie.schema.json` — saída do Pesquisador (§7.3, Etapa 1).
- `auditoria.schema.json` — JSON do §8.2 gravado em `auditorias.achados_json`, com os campos obrigatórios
  `plugin_resolve_parcialmente` e `exige_ajuste_no_codigo`.
- `qualificacao.schema.json` — saída do Qualificador (§7.3, Etapa 3), gravada em `qualificacoes`.
- `mapeador.schema.json` — escolha do Mapeador de decisores (§7.3, Etapa 4): até 3 pessoas, uma por área.
- `mapeador-web.schema.json` — pessoas encontradas em fontes públicas pela busca web (nunca o LinkedIn).
- `mapeador-colunas.schema.json` — colunas de uma planilha de lote identificadas pela IA (§7.2, entrada 2).
