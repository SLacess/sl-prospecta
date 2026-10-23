# Agentes
Um módulo por agente (CONSTITUICAO §6): hunter, researcher, auditor, qualifier, decision_mapper,
strategist, copywriter, reviewer, messenger, reply_reader, scheduler, proposer, analyst, guardian.
Cada agente = esquema de entrada + esquema de saída + prompt em `packages/prompts` + eval + teto de custo.
Agentes nunca escrevem no banco; devolvem o resultado ao orquestrador.
