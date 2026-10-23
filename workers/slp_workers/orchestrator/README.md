# Orquestrador
Máquina de estados do prospect (CONSTITUICAO §7.1). Recebe as saídas JSON dos agentes,
valida pelos esquemas de `packages/schemas`, persiste, registra em `acoes_agentes`
e decide a próxima transição conforme os níveis de autonomia (§13). Fase 1.
