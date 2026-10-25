"""Baixa o axe-core na versão fixada e confere a integridade antes de salvar.

Mesma versão usada nos testes de acessibilidade do painel (apps/web/package-lock.json), para que
o Auditor e o CI do painel apliquem as mesmas regras.

Uso: python scripts/baixar_axe.py <destino/axe.min.js>
"""

import base64
import hashlib
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

VERSAO = "4.14.0"
URL = f"https://registry.npmjs.org/axe-core/-/axe-core-{VERSAO}.tgz"
# "integrity" do package-lock.json do painel
SHA512 = "9WTZxEjsZ7b13TH8JPmbV2z8CHbl80/2hm3XPEG4JgNdQLK81IBRXmSxHfMAOkSqQeRxT/0dwNDz2GOm3zzpcQ=="


def main(destino: str) -> None:
    alvo = Path(destino)
    if alvo.exists():
        print(f"axe-core já está em {alvo}")
        return
    with urllib.request.urlopen(URL, timeout=60) as resposta:
        pacote = resposta.read()
    calculado = base64.b64encode(hashlib.sha512(pacote).digest()).decode()
    if calculado != SHA512:
        sys.exit(f"integridade do axe-core {VERSAO} não confere")
    with tarfile.open(fileobj=io.BytesIO(pacote), mode="r:gz") as tar:
        arquivo = tar.extractfile("package/axe.min.js")
        if arquivo is None:
            sys.exit("axe.min.js não encontrado no pacote")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(arquivo.read())
    print(f"axe-core {VERSAO} salvo em {alvo}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "vendor/axe.min.js")
