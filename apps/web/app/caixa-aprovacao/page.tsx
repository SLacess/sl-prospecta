"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, ErroApi, type FiltroCaixa, type ItemCaixaAprovacao, lerToken, type PlacarCaixa } from "@/lib/api";

import { ItemCaixa } from "./item";

const ABAS: { valor: FiltroCaixa; rotulo: string }[] = [
  { valor: "pendentes", rotulo: "Pendentes" },
  { valor: "aprovados", rotulo: "Aprovados" },
  { valor: "rejeitados", rotulo: "Rejeitados" },
  { valor: "enviados", rotulo: "Enviados" },
];

/**
 * Caixa de Aprovação (CONSTITUICAO §12.1, item 4; ADR 0014): editar em linha, aprovar, rejeitar com
 * motivo, e confirmar manualmente o envio — não há Mensageiro automático nesta fase.
 */
export default function CaixaAprovacao() {
  const [filtro, setFiltro] = useState<FiltroCaixa>("pendentes");
  const [itens, setItens] = useState<ItemCaixaAprovacao[] | null>(null);
  const [placar, setPlacar] = useState<PlacarCaixa | null>(null);
  const [erro, setErro] = useState("");
  const [anuncio, setAnuncio] = useState("");

  const carregar = useCallback(async (f: FiltroCaixa) => {
    try {
      const [lista, p] = await Promise.all([
        apiFetch<ItemCaixaAprovacao[]>(`/caixa-aprovacao?filtro=${f}`),
        apiFetch<PlacarCaixa>("/caixa-aprovacao/placar"),
      ]);
      setItens(lista);
      setPlacar(p);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar a Caixa de Aprovação.");
    }
  }, []);

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    void carregar(filtro);
  }, [carregar, filtro]);

  function aoAtualizar(atualizado: ItemCaixaAprovacao) {
    setAnuncio(`Mensagem para ${atualizado.contato_nome} atualizada.`);
    void carregar(filtro);
  }

  return (
    <>
      <h1>Caixa de Aprovação</h1>
      <p className="lead">
        Edite o texto se precisar, aprove ou rejeite com um motivo. Nada é enviado pela plataforma (ADR
        0014) — depois de aprovar, copie o texto e envie pela sua caixa de e-mail; volte aqui e marque como
        enviada para a linha do tempo não ficar sem esse registro.
      </p>
      <p className="hint">
        Atalhos de teclado (funcionam fora dos campos de texto): <kbd>A</kbd> aprovar, <kbd>R</kbd> rejeitar,{" "}
        <kbd>S</kbd> marcar como enviada. Todos têm um botão equivalente.
      </p>

      {placar && (
        <section className="card" aria-labelledby="titulo-placar-caixa">
          <h2 id="titulo-placar-caixa" style={{ marginTop: 0 }}>
            Placar da Fase 3
          </h2>
          <dl className="totais-auditoria">
            <div>
              <dt>Aprovados com menos de 20% de edição</dt>
              <dd>
                {placar.aprovados_dentro_da_meta} de {placar.meta}
              </dd>
            </div>
            <div>
              <dt>Total aprovados</dt>
              <dd>{placar.aprovados}</dd>
            </div>
            <div>
              <dt>Edição média</dt>
              <dd>{placar.percentual_medio_editado !== null ? `${placar.percentual_medio_editado}%` : "—"}</dd>
            </div>
          </dl>
          <p className={placar.atingido ? "situacao atingido" : "situacao"}>
            <strong>{placar.atingido ? "Critério atingido." : "Critério ainda não atingido."}</strong>{" "}
            {placar.atingido ? "A Fase 3 pode avançar." : `Pendências: ${placar.pendencias.join("; ")}.`}
          </p>
        </section>
      )}

      <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>
        {anuncio}
      </div>
      <div role="alert" className={erro ? "status error" : undefined}>
        {erro}
      </div>

      <div className="row" role="tablist" aria-label="Filtro da fila" style={{ margin: "1.2rem 0" }}>
        {ABAS.map((a) => (
          <button
            key={a.valor}
            type="button"
            role="tab"
            aria-selected={filtro === a.valor}
            className={filtro === a.valor ? undefined : "secundario"}
            onClick={() => setFiltro(a.valor)}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      {itens && itens.length === 0 && <p className="hint">Nada por aqui nesta aba.</p>}
      {itens?.map((item) => (
        <ItemCaixa key={item.toque_id} item={item} aoAtualizar={aoAtualizar} />
      ))}
    </>
  );
}
