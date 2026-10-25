"use client";

import { useEffect, useState } from "react";

import { apiFetch, ErroApi, type ItemRevisao, type Revisao, type Veredito } from "@/lib/api";

const OPCOES: [Veredito, string][] = [
  ["correto", "Correto"],
  ["parcial", "Parcialmente"],
  ["incorreto", "Incorreto"],
];

type Estado = Record<string, { veredito: Veredito | null; motivo: string }>;

function estadoInicial(itens: ItemRevisao[]): Estado {
  return Object.fromEntries(itens.map((i) => [i.chave, { veredito: i.veredito, motivo: i.motivo ?? "" }]));
}

function GrupoItem({
  prefixo,
  item,
  valor,
  aoMudar,
  obrigatorio,
}: {
  prefixo: string;
  item: ItemRevisao;
  valor: { veredito: Veredito | null; motivo: string };
  aoMudar: (v: { veredito: Veredito | null; motivo: string }) => void;
  obrigatorio: boolean;
}) {
  const id = `${prefixo}-${item.chave.replace(/[^a-z0-9]/gi, "-")}`;
  const pedeMotivo = valor.veredito !== null && valor.veredito !== "correto";
  return (
    <fieldset className="item-revisao">
      <legend>
        {item.rotulo}
        {item.pagina ? <span className="hint"> (página {item.pagina})</span> : null}
        {obrigatorio ? <span className="visually-hidden"> (obrigatório)</span> : null}
      </legend>
      <div className="opcoes-revisao">
        {OPCOES.map(([v, rotulo]) => (
          <span className="opcao" key={v}>
            <input
              type="radio"
              id={`${id}-${v}`}
              name={id}
              value={v}
              checked={valor.veredito === v}
              onChange={() => aoMudar({ ...valor, veredito: v })}
            />
            <label htmlFor={`${id}-${v}`}>{rotulo}</label>
          </span>
        ))}
      </div>
      {pedeMotivo && (
        <div className="motivo-revisao">
          <label htmlFor={`${id}-motivo`}>O que está errado ou incompleto?</label>
          <textarea
            id={`${id}-motivo`}
            rows={2}
            value={valor.motivo}
            onChange={(e) => aoMudar({ ...valor, motivo: e.target.value })}
          />
        </div>
      )}
    </fieldset>
  );
}

/**
 * Revisão humana da auditoria (critério da Fase 1, CONSTITUICAO §19). Só aparece para o perfil admin.
 * Os 3 achados para leigos são obrigatórios; os problemas técnicos, opcionais.
 */
export function RevisaoAuditoria({ auditoriaId }: { auditoriaId: string }) {
  const [revisao, setRevisao] = useState<Revisao | null>(null);
  const [achados, setAchados] = useState<Estado>({});
  const [tecnicos, setTecnicos] = useState<Estado>({});
  const [honestos, setHonestos] = useState(true);
  const [anuncio, setAnuncio] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    apiFetch<Revisao>(`/auditorias/${auditoriaId}/revisao`)
      .then((r) => {
        setRevisao(r);
        setAchados(estadoInicial(r.achados));
        setTecnicos(estadoInicial(r.tecnicos));
        setHonestos(r.textos_honestos ?? true);
      })
      .catch((e) => setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar a revisão."));
  }, [auditoriaId]);

  async function salvar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (salvando || !revisao) return;
    setErro("");
    const faltando = revisao.achados.filter((a) => !achados[a.chave]?.veredito);
    if (faltando.length) {
      setErro(`Marque os 3 achados para leigos (falta: ${faltando.map((a) => a.rotulo).join("; ")}).`);
      return;
    }
    const semMotivo = [...Object.values(achados), ...Object.values(tecnicos)].some(
      (v) => v.veredito && v.veredito !== "correto" && !v.motivo.trim(),
    );
    if (semMotivo) {
      setErro("Explique o motivo de cada item que não está correto.");
      return;
    }
    setSalvando(true);
    setAnuncio("Salvando a revisão…");
    try {
      const corpo = {
        achados: revisao.achados.map((a) => ({
          chave: a.chave,
          veredito: achados[a.chave].veredito,
          motivo: achados[a.chave].motivo || null,
        })),
        tecnicos: revisao.tecnicos
          .filter((t) => tecnicos[t.chave]?.veredito)
          .map((t) => ({ chave: t.chave, veredito: tecnicos[t.chave].veredito, motivo: tecnicos[t.chave].motivo || null })),
        textos_honestos: honestos,
      };
      const r = await apiFetch<Revisao>(`/auditorias/${auditoriaId}/revisao`, {
        method: "PUT",
        body: JSON.stringify(corpo),
      });
      setRevisao(r);
      setAnuncio("Revisão salva. O placar da Fase 1 foi atualizado.");
    } catch (e) {
      setAnuncio("");
      setErro(e instanceof ErroApi ? e.message : "Não foi possível salvar a revisão.");
    } finally {
      setSalvando(false);
    }
  }

  if (!revisao) {
    return <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>;
  }

  return (
    <section className="card" aria-labelledby="titulo-revisao" style={{ marginTop: "1.5rem" }}>
      <h2 id="titulo-revisao" style={{ marginTop: 0 }}>Revisão da auditoria</h2>
      <p className="hint">
        Confira cada achado no site (por exemplo, com a extensão WAVE ou navegando com teclado e leitor de tela).
        {revisao.completa ? " Esta auditoria já foi revisada; salvar de novo atualiza a revisão." : ""}
      </p>
      <form onSubmit={salvar} noValidate aria-busy={salvando}>
        <h3>Achados para leigos (obrigatório)</h3>
        {revisao.achados.map((item) => (
          <GrupoItem
            key={item.chave}
            prefixo="achado"
            item={item}
            obrigatorio
            valor={achados[item.chave] ?? { veredito: null, motivo: "" }}
            aoMudar={(v) => setAchados({ ...achados, [item.chave]: v })}
          />
        ))}

        <details>
          <summary>Problemas técnicos (opcional, {revisao.tecnicos.length})</summary>
          {revisao.tecnicos.map((item) => (
            <GrupoItem
              key={item.chave}
              prefixo="tecnico"
              item={item}
              obrigatorio={false}
              valor={tecnicos[item.chave] ?? { veredito: null, motivo: "" }}
              aoMudar={(v) => setTecnicos({ ...tecnicos, [item.chave]: v })}
            />
          ))}
        </details>

        <div className="checagem-honestidade">
          <input
            type="checkbox"
            id="textos-honestos"
            checked={honestos}
            onChange={(e) => setHonestos(e.target.checked)}
          />
          <label htmlFor="textos-honestos">
            Os textos não prometem conformidade total nem site “100% acessível”
          </label>
        </div>

        <button type="submit" aria-disabled={salvando}>
          Salvar revisão
        </button>
      </form>
      <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>{anuncio}</div>
      <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>
    </section>
  );
}
