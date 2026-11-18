# Tabela de preços

> A CONSTITUICAO (§2.2, §11.2) proíbe a IA de inventar preço: a plataforma só usa o que estiver cadastrado
> aqui. Valores definidos por Marcos Alencar em 2026-11-18. Ainda faltam o teto de desconto sem aprovação
> e a validade padrão da proposta (seção "O que falta" abaixo) — até lá, o Propositor (Fase 6) não tem
> essas duas regras para aplicar sozinho.

## Planos definidos

| Plano | Tipo | Valor | Periodicidade |
|---|---|---|---|
| Plugin | `plugin` | R$ 930,00 | anual |
| Combo (plugin + consultoria) | `combo` | R$ 3.945,00 | _a confirmar: anual ou único?_ |
| Enterprise / escopo customizado | `custom` | Sob consulta | — |

_Confirmar com Marcos: a periodicidade do Combo (R$ 3.945,00) — segue anual como o Plugin, ou é um valor
único de projeto?_

## Por que esta estrutura

§11.2 define a proposta em camadas — **plugin de acessibilidade** (tecnologia assistiva imediata) +
**consultoria Sinal Link** (correção no código, capacitação, auditoria manual) + **monitoramento contínuo**
— e exige aprovação do Marcos para desconto acima do limite ou escopo fora do catálogo. A estrutura abaixo
só formaliza isso em campos; os nomes podem mudar, mas esses três tipos e o teto de desconto precisam existir
para o Propositor funcionar.

## Planos

| Campo | O que é | Preencher |
|---|---|---|
| `id` | Identificador curto (ex. `plugin-basico`) | — |
| `nome` | Nome comercial do plano | — |
| `tipo` | `plugin` \| `consultoria` \| `combo` \| `monitoramento` \| `custom` | — |
| `descricao` | Frase curta para a proposta | — |
| `unidade` | Como é cobrado: `por_site`, `por_hora`, `por_pagina`, `mensal`, `unico` | — |
| `valor_setup` | Cobrança única de implantação (se houver) | _preencher_ |
| `valor_recorrente` | Valor por ciclo (se for mensal/anual) | _preencher_ |
| `periodicidade` | `mensal`, `anual`, `nenhuma` | — |
| `porte_recomendado` | Faixas de porte/score da `config.icp` em que esse plano se encaixa (opcional) | — |

## Regras de negócio (vão junto na mesma chave de `config`)

| Campo | O que é | Preencher |
|---|---|---|
| `moeda` | Hoje só BRL | `BRL` |
| `desconto_maximo_sem_aprovacao` | Percentual que o Propositor pode aplicar sozinho; acima disso, para e pede sua aprovação (§11.2) | _preencher_ |
| `validade_proposta_dias` | Quantos dias a proposta gerada fica válida | _preencher_ |
| `atualizado_em` | Data da última revisão de preços | — |

## JSON com os valores definidos

Periodicidade do Combo marcada como `"a_confirmar"` até a resposta de Marcos; `desconto_maximo_sem_aprovacao`
e `validade_proposta_dias` seguem sem valor.

```json
{
  "moeda": "BRL",
  "desconto_maximo_sem_aprovacao": null,
  "validade_proposta_dias": null,
  "atualizado_em": "2026-11-18",
  "planos": [
    {
      "id": "plugin",
      "nome": "Plugin de acessibilidade",
      "tipo": "plugin",
      "descricao": "Tecnologia assistiva imediata no site.",
      "unidade": "por_site",
      "valor_setup": null,
      "valor_recorrente": 930.00,
      "periodicidade": "anual"
    },
    {
      "id": "combo",
      "nome": "Combo (plugin + consultoria)",
      "tipo": "combo",
      "descricao": "Plugin + correção no código, capacitação e auditoria manual.",
      "unidade": "por_site",
      "valor_setup": null,
      "valor_recorrente": 3945.00,
      "periodicidade": "a_confirmar"
    },
    {
      "id": "enterprise",
      "nome": "Enterprise / escopo customizado",
      "tipo": "custom",
      "descricao": "Para organizações grandes ou escopo fora do catálogo padrão.",
      "unidade": "sob_consulta",
      "valor_setup": null,
      "valor_recorrente": null,
      "periodicidade": "nenhuma"
    }
  ]
}
```

## Quando isso entra no código

Fica como proposta até a Fase 3: quando o Propositor (§11.2, Fase 6) for construído, este JSON — já com os
valores reais — se torna a chave `precos` na tabela `config` (mesmo padrão de `icp`, `score_pesos` etc.),
com uma migração Alembic simples. Não crie essa migração agora; a Fase 2 não antecipa código de fases
futuras sem pedido explícito.

## O que falta para fechar esta frente
- [x] Definir os planos reais e valores (Plugin R$ 930/ano, Combo R$ 3.945, Enterprise sob consulta)
- [ ] Confirmar a periodicidade do Combo (anual, como o Plugin, ou valor único de projeto?)
- [ ] Definir o teto de desconto que o Propositor pode aplicar sem te consultar
- [ ] Definir a validade padrão da proposta gerada
