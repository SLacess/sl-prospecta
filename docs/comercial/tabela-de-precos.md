# Tabela de preços — estrutura proposta

> Proposta de estrutura, **sem valores**. A CONSTITUICAO (§2.2, §11.2) proíbe a IA de inventar preço:
> a plataforma só usa o que for cadastrado aqui. Preencha os valores e leve para a Fase 3 — o Propositor
> (§11.2) monta a proposta só com o que estiver nesta tabela.

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
| `tipo` | `plugin` \| `consultoria` \| `combo` \| `monitoramento` | — |
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

## Exemplo de preenchimento (estrutura, não use os valores)

```json
{
  "moeda": "BRL",
  "desconto_maximo_sem_aprovacao": 0,
  "validade_proposta_dias": 0,
  "atualizado_em": "AAAA-MM-DD",
  "planos": [
    {
      "id": "preencher",
      "nome": "preencher",
      "tipo": "plugin",
      "descricao": "preencher",
      "unidade": "preencher",
      "valor_setup": null,
      "valor_recorrente": null,
      "periodicidade": "preencher"
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
- [ ] Definir os planos reais (quantos, quais tipos, valores de setup/recorrência)
- [ ] Definir o teto de desconto que o Propositor pode aplicar sem te consultar
- [ ] Definir a validade padrão da proposta gerada
