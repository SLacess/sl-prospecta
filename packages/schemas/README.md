# Esquemas

Esquemas JSON de entrada e saída de cada agente. Gerados a partir dos modelos Pydantic e validados pelo
orquestrador antes de persistir. Toda saída inclui `raciocinio_resumido` (CONSTITUICAO §6).

Primeiro esquema a criar (Fase 1): `auditoria.schema.json`, seguindo o exemplo da CONSTITUICAO §8.2 —
incluindo os campos obrigatórios `plugin_resolve_parcialmente` e `exige_ajuste_no_codigo`.
