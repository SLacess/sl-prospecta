import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import Papel, Usuario
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["autenticação"])


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioOut(BaseModel):
    id: uuid.UUID
    nome: str
    email: EmailStr
    papel: Papel


class UsuarioIn(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    papel: Papel = Papel.vendedor


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(Usuario).where(Usuario.email == form.username.lower()))
    if user is None or not user.ativo or not verify_password(form.password, user.senha_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="E-mail ou senha incorretos.")
    return TokenOut(access_token=create_access_token(str(user.id), user.papel.value))


@router.get("/me", response_model=UsuarioOut)
def me(user: Usuario = Depends(get_current_user)) -> Usuario:
    return user


@router.post("/usuarios", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(
    dados: UsuarioIn,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role(Papel.admin)),
) -> Usuario:
    if len(dados.senha) < 10:
        raise HTTPException(status_code=422, detail="A senha deve ter pelo menos 10 caracteres.")
    email = dados.email.lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail.")
    user = Usuario(nome=dados.nome, email=email, senha_hash=hash_password(dados.senha), papel=dados.papel)
    db.add(user)
    db.commit()
    return user
