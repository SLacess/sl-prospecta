"""Caixa de Aprovação (CONSTITUICAO §12.1, item 4; ADR 0014): decisão humana sobre o toque de dia 0.

Aqui ficam só as regras puras — sem banco, sem FastAPI — no mesmo espírito de `app/crm.py`. O router
(`app/routers/caixa_aprovacao.py`) cuida de banco e HTTP.
"""

from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher


def calcular_percentual_editado(
    assunto_original: str, corpo_original: str, assunto_final: str, corpo_final: str
) -> Decimal:
    """Quanto do texto da IA mudou até a aprovação humana — é o que a Fase 3 mede (50 aprovados com
    < 20% de edição). 0 quando o vendedor aprovou sem tocar em nada; 100 quando o texto é outro."""
    original = f"{assunto_original}\n\n{corpo_original}"
    final = f"{assunto_final}\n\n{corpo_final}"
    se_igual = SequenceMatcher(None, original, final).ratio()
    percentual = (Decimal(1) - Decimal(str(se_igual))) * Decimal(100)
    return percentual.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
