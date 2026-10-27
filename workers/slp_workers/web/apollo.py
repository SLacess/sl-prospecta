"""Cliente do Apollo.io (CONSTITUICAO §16.1, dados B2B). Usado só pelo Mapeador de decisores.

Três chamadas (docs.apollo.io, conferidas em 26/10/2026):
- `GET  /organizations/enrich?domain=` — 1 crédito; porte, UF e cidade da empresa.
- `POST /mixed_people/api_search` — sem crédito; pessoas pelo domínio e cargos, sem e-mail nem sobrenome.
- `POST /people/match` — 1 crédito quando encontra dados; e-mail profissional e `email_status`.
  Nunca pedimos e-mail pessoal nem telefone (coleta mínima, §15.1).

Os parâmetros vão na query string mesmo no POST, como a API documenta. A chave vai no cabeçalho `x-api-key`.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

MAX_TENTATIVAS_429 = 3


class ErroApollo(Exception):
    def __init__(self, mensagem: str, transitorio: bool = False) -> None:
        super().__init__(mensagem)
        self.transitorio = transitorio


class ApolloNaoConfigurado(ErroApollo):
    pass


@dataclass
class OrganizacaoApollo:
    colaboradores: int | None
    cidade: str | None
    estado: str | None
    pais: str | None
    creditos: int = 1


@dataclass
class PessoaBusca:
    """Pessoa da busca (sem crédito): só primeiro nome, sobrenome ofuscado e cargo."""

    id: str
    primeiro_nome: str
    sobrenome_ofuscado: str | None
    cargo: str | None
    tem_email: bool


@dataclass
class PessoaEnriquecida:
    id: str | None
    nome: str | None
    cargo: str | None
    email: str | None
    email_status: str | None
    linkedin_url: str | None
    confianca: str | None
    creditos: int
    org_dominio: str | None = None  # organization.primary_domain da pessoa
    org_site: str | None = None  # organization.website_url da pessoa
    bruto: dict[str, Any] = field(default_factory=dict, repr=False)


class ClienteApollo:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.apollo.io/api/v1",
        timeout_s: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
        espera_429_s: float = 5.0,
    ) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._transport = transport
        self._espera_429_s = espera_429_s

    @property
    def configurado(self) -> bool:
        return bool(self._api_key)

    async def _chamar(self, metodo: str, caminho: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.configurado:
            raise ApolloNaoConfigurado("APOLLO_API_KEY não configurada no worker")
        cabecalhos = {"x-api-key": self._api_key, "Cache-Control": "no-cache", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as cliente:
            for tentativa in range(MAX_TENTATIVAS_429):
                try:
                    r = await cliente.request(
                        metodo, f"{self._base_url}{caminho}", params=params, headers=cabecalhos
                    )
                except httpx.HTTPError as exc:
                    raise ErroApollo(f"Apollo indisponível ({type(exc).__name__})", transitorio=True) from exc
                if r.status_code == 429 and tentativa < MAX_TENTATIVAS_429 - 1:
                    await asyncio.sleep(self._espera_429_s * (tentativa + 1))
                    continue
                break
        if r.status_code == 429 or r.status_code >= 500:
            raise ErroApollo(f"Apollo indisponível ({r.status_code})", transitorio=True)
        if r.status_code in (401, 403):
            raise ErroApollo(f"Apollo recusou a chave ({r.status_code}); confira a APOLLO_API_KEY e o plano")
        if r.status_code >= 400:
            raise ErroApollo(f"Apollo recusou a chamada ({r.status_code})")
        try:
            return r.json()
        except ValueError as exc:
            raise ErroApollo("Apollo devolveu uma resposta que não é JSON", transitorio=True) from exc

    async def organizacao(self, dominio: str) -> OrganizacaoApollo | None:
        dados = await self._chamar("GET", "/organizations/enrich", {"domain": dominio})
        org = dados.get("organization")
        if not isinstance(org, dict):
            return None
        colaboradores = org.get("estimated_num_employees")
        return OrganizacaoApollo(
            colaboradores=int(colaboradores) if isinstance(colaboradores, int | float) else None,
            cidade=org.get("city"),
            estado=org.get("state"),
            pais=org.get("country"),
        )

    async def buscar_pessoas(
        self, dominio: str, cargos: list[str], senioridades: list[str], limite: int
    ) -> list[PessoaBusca]:
        params: dict[str, Any] = {
            "q_organization_domains_list[]": [dominio],
            "person_titles[]": cargos,
            "include_similar_titles": "true",
            "person_seniorities[]": senioridades,
            "page": 1,
            "per_page": min(max(limite, 1), 100),
        }
        dados = await self._chamar("POST", "/mixed_people/api_search", params)
        pessoas = []
        for p in dados.get("people") or []:
            if not isinstance(p, dict) or not p.get("id") or not p.get("first_name"):
                continue
            pessoas.append(
                PessoaBusca(
                    id=str(p["id"]),
                    primeiro_nome=str(p["first_name"]),
                    sobrenome_ofuscado=p.get("last_name_obfuscated"),
                    cargo=p.get("title"),
                    tem_email=bool(p.get("has_email")),
                )
            )
        return pessoas[:limite]

    async def enriquecer_pessoa(
        self, *, apollo_id: str | None = None, nome: str | None = None, dominio: str | None = None
    ) -> PessoaEnriquecida | None:
        params: dict[str, Any] = {"reveal_personal_emails": "false", "reveal_phone_number": "false"}
        if apollo_id:
            params["id"] = apollo_id
        else:
            params.update({"name": nome, "domain": dominio})
        dados = await self._chamar("POST", "/people/match", params)
        p = dados.get("person")
        if not isinstance(p, dict):
            return None
        confianca = p.get("match_confidence")
        org = p.get("organization") if isinstance(p.get("organization"), dict) else {}
        # Conta por cima (1 crédito sempre que volta alguém), para o disjuntor nunca subestimar
        return PessoaEnriquecida(
            id=p.get("id"),
            nome=p.get("name") or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x) or None,
            cargo=p.get("title"),
            email=p.get("email"),
            email_status=p.get("email_status"),
            linkedin_url=p.get("linkedin_url"),
            confianca=confianca,
            creditos=0 if confianca == "none" else 1,
            org_dominio=org.get("primary_domain"),
            org_site=org.get("website_url"),
            bruto={
                **{k: p.get(k) for k in ("id", "title", "email_status", "match_confidence")},
                "email_dominio": (p.get("email") or "").rpartition("@")[2] or None,
                "org_dominio": org.get("primary_domain"),
            },
        )
