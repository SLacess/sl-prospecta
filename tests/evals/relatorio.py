"""Checks determinísticos e o relatório humano de uma rodada de evals (Fase 3, Tarefa 1).

A nota do Crítico abaixo de 8 não entra nestes checks: é esperada em alguns casos-armadilha e aparece
só no relatório para leitura humana, nunca falha o teste sozinha.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROIBICOES = [
    "revolucionário",
    "solução completa",
    "100% acessível",
    "100% acessíveis",
    "garantimos conformidade",
    "garantia legal",
]

PASTA_RELATORIOS = Path(__file__).resolve().parent / "relatorios"


def contar_palavras(texto: str) -> int:
    return len(texto.split())


def checar_assunto(assunto: str) -> bool:
    return assunto == assunto.lower() and 0 < contar_palavras(assunto) <= 6


def checar_corpo(corpo: str) -> bool:
    return contar_palavras(corpo) <= 120


def checar_proibicoes(texto: str, extras: list[str] | None = None) -> list[str]:
    baixo = texto.lower()
    termos = PROIBICOES + [t.lower() for t in (extras or [])]
    encontradas = [t for t in termos if t in baixo]
    encontradas += re.findall(
        r"[^\s]+!{2,}", texto
    )  # pontuação de exclamação em excesso
    return encontradas


def checar_fundamentacao(
    corpo: str, fatos_usados: list[str], caso: dict[str, Any]
) -> bool:
    """Confere, sem outra chamada de IA, se o achado escolhido pelo Estrategista aparece de fato na
    mensagem — pega o caso grosseiro de "inventou achado". A veracidade fina é tarefa do Crítico."""
    fato_chave = caso.get("esperado", {}).get("fato_chave")
    if not fato_chave:
        return True
    alvo = fato_chave.replace("-", " ").lower()
    termos = {p for p in alvo.split() if len(p) > 3}
    if not termos:
        return True
    texto = (corpo + " " + " ".join(fatos_usados)).lower()
    return any(termo in texto for termo in termos)


def avaliar_caso(
    caso: dict[str, Any], estrategia: Any, redacao: Any, critica: Any
) -> dict[str, Any]:
    proibicoes_redacao = checar_proibicoes(
        f"{redacao.assunto} {redacao.corpo}",
        caso.get("esperado", {}).get("nunca_deve_conter"),
    )
    return {
        "id": caso["id"],
        "persona_coerente": estrategia.persona == caso.get("persona_esperada"),
        "angulo_aceitavel": estrategia.angulo
        in caso.get("esperado", {}).get("angulos_aceitaveis", []),
        "assunto_ok": checar_assunto(redacao.assunto),
        "corpo_palavras_ok": checar_corpo(redacao.corpo),
        "proibicoes_encontradas": proibicoes_redacao,
        "fundamentacao_ok": checar_fundamentacao(
            redacao.corpo, redacao.fatos_usados, caso
        ),
        "critica_nota": critica.nota,
        "critica_aprovado": critica.aprovado,
        "critica_motivo": critica.motivo,
        "estrategia": estrategia.model_dump(),
        "redacao": redacao.model_dump(),
        "critica": critica.model_dump(),
    }


def falhou_determinismo(resultado: dict[str, Any]) -> list[str]:
    """Checks que fazem o teste falhar de verdade — a nota do Crítico nunca entra aqui."""
    problemas = []
    if not resultado["assunto_ok"]:
        problemas.append("assunto fora do limite (até 6 palavras, minúsculas)")
    if not resultado["corpo_palavras_ok"]:
        problemas.append("corpo acima de 120 palavras")
    if resultado["proibicoes_encontradas"]:
        problemas.append(
            f"proibições encontradas: {resultado['proibicoes_encontradas']}"
        )
    if not resultado["fundamentacao_ok"]:
        problemas.append("achado escolhido não aparece no corpo nem em fatos_usados")
    return problemas


def imprimir_relatorio(resultados: list[dict[str, Any]]) -> None:
    aprovados = sum(1 for r in resultados if r["critica_aprovado"])
    notas = [r["critica_nota"] for r in resultados]
    media = sum(notas) / len(notas) if notas else 0
    print(
        f"\n{len(resultados)} caso(s) rodado(s); {aprovados} aprovado(s) pelo Crítico; nota média {media:.1f}"
    )
    for r in resultados:
        marca = "OK" if r["critica_aprovado"] else "REPROVADO"
        print(
            f"  [{marca}] {r['id']} — nota {r['critica_nota']} — {r['critica_motivo']}"
        )
        for problema in falhou_determinismo(r):
            print(f"      ! {problema}")


def salvar_relatorio(resultados: list[dict[str, Any]]) -> Path:
    PASTA_RELATORIOS.mkdir(exist_ok=True)
    caminho = PASTA_RELATORIOS / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    caminho.write_text(
        json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return caminho
