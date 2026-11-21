"""Relatório público do diagnóstico (CONSTITUICAO §9.1, §17, §21.1) — o link que o Redator inclui no
e-mail. Deliberadamente **sem** `Depends(get_current_user)`: diferente de `ficha.py`, o acesso aqui vem
só do `slug` aleatório, não de login — é assim que a CONSTITUICAO §17 pensa o microsite (um link pessoal,
não uma área autenticada).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artefatos import Armazenamento, chave_relatorio, get_armazenamento
from app.db import get_db
from app.models import Microsite

router = APIRouter(tags=["diagnóstico"])


@router.get("/diagnostico/{slug}")
def diagnostico(
    slug: str, db: Session = Depends(get_db), armazenamento: Armazenamento = Depends(get_armazenamento)
) -> Response:
    microsite = db.scalar(
        select(Microsite).where(Microsite.slug == slug, Microsite.expira_em >= datetime.now(UTC))
    )
    if microsite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link não encontrado ou expirado.")
    dados = armazenamento.ler(chave_relatorio(microsite.empresa_id, microsite.auditoria_id, "html"))
    if dados is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado.")
    return Response(dados, media_type="text/html; charset=utf-8")
