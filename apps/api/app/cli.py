"""Comandos administrativos.

Uso:
    python -m app.cli create-admin --email voce@exemplo.com --name "Seu Nome"
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Papel, Usuario
from app.security import hash_password


def create_admin(email: str, name: str) -> int:
    senha = getpass.getpass("Senha (mín. 10 caracteres): ")
    if len(senha) < 10:
        print("Senha muito curta.", file=sys.stderr)
        return 1
    if senha != getpass.getpass("Confirme a senha: "):
        print("As senhas não conferem.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        if db.scalar(select(Usuario).where(Usuario.email == email.lower())):
            print("Já existe um usuário com este e-mail.", file=sys.stderr)
            return 1
        db.add(Usuario(nome=name, email=email.lower(), senha_hash=hash_password(senha), papel=Papel.admin))
        db.commit()
    print(f"Administrador {email} criado.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-admin", help="Cria um usuário administrador")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    args = parser.parse_args()

    if args.cmd == "create-admin":
        return create_admin(args.email, args.name)
    return 1


if __name__ == "__main__":
    sys.exit(main())
