"""Candidatos de e-mail corporativo a partir do nome e do domínio (ADR 0012, caminho alternativo do Mapeador).

Sem IA e sem custo: os padrões mais comuns nas empresas brasileiras. Nenhum candidato é usado sem a
verificação SMTP do Apify; e-mail inferido só vale para o domínio corporativo da empresa (§15.1, LIA).
"""

import re
import unicodedata

PARTICULAS = frozenset({"de", "da", "do", "das", "dos", "e", "di", "du", "del", "van", "von"})
MAX_CANDIDATOS = 5


def _limpo(parte: str) -> str:
    texto = unicodedata.normalize("NFKD", parte).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", texto)


def candidatos(nome: str, dominio: str, maximo: int = MAX_CANDIDATOS) -> list[str]:
    partes = [_limpo(p) for p in nome.replace("-", " ").split()]
    partes = [p for p in partes if p and p not in PARTICULAS]
    if len(partes) < 2 or not dominio:
        return []
    primeiro, ultimo = partes[0], partes[-1]
    locais = [
        f"{primeiro}.{ultimo}",
        f"{primeiro[0]}{ultimo}",
        f"{primeiro}",
        f"{primeiro}{ultimo}",
        f"{primeiro}_{ultimo}",
    ]
    if len(partes) > 2:
        # Muita gente usa o penúltimo sobrenome (ex.: Ana Paula Souza Lima → ana.souza)
        locais.insert(2, f"{primeiro}.{partes[-2]}")
    vistos: list[str] = []
    for local in locais:
        email = f"{local}@{dominio}"
        if email not in vistos:
            vistos.append(email)
    return vistos[:maximo]
