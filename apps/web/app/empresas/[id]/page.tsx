"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AuditoriaTecnica } from "@/app/auditoria-tecnica";
import { MoverEstado } from "@/app/mover-estado";
import {
  apiFetch,
  baixarArquivo,
  ErroApi,
  type Evidencia,
  type Ficha,
  lerToken,
  ROTULO_ESTADO,
  ROTULO_SETOR,
  type UsuarioAtual,
} from "@/lib/api";

import { DecisoresDaEmpresa } from "./decisores";
import { QualificacaoDaEmpresa } from "./qualificacao";
import { RevisaoAuditoria } from "./revisao";

const TEMA: Record<string, string> = {
  inclusao: "Inclusão",
  diversidade: "Diversidade",
  pcd: "Pessoas com deficiência",
  acessibilidade: "Acessibilidade",
  esg: "ESG",
};

function horario(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function caminho(url: string): string {
  try {
    return new URL(url).pathname || "/";
  } catch {
    return url;
  }
}

/** Print protegido por login: baixado com o token e exibido como objeto local. */
function PrintDaEvidencia({ empresaId, evidencia }: { empresaId: string; evidencia: Evidencia }) {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    if (evidencia.print_indice === null) return;
    let ativo = true;
    let objeto: string | null = null;
    baixarArquivo(`/empresas/${empresaId}/prints/${evidencia.print_indice}`)
      .then((blob) => {
        if (!ativo) return;
        objeto = URL.createObjectURL(blob);
        setUrl(objeto);
      })
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
      if (objeto) URL.revokeObjectURL(objeto);
    };
  }, [empresaId, evidencia.print_indice]);

  if (evidencia.print_indice === null || erro) {
    return <p className="hint">Print não disponível para esta página.</p>;
  }
  if (!url) return <p className="hint">Carregando o print…</p>;
  return (
    <figure className="print-evidencia">
      <img src={url} alt={evidencia.alt} />
      {evidencia.caixa && (
        <div
          className="caixa-evidencia"
          aria-hidden="true"
          style={{
            left: `${evidencia.caixa.left}%`,
            top: `${evidencia.caixa.top}%`,
            width: `${evidencia.caixa.width}%`,
            height: `${evidencia.caixa.height}%`,
          }}
        >
          <span>{evidencia.numero}</span>
        </div>
      )}
    </figure>
  );
}

/**
 * Ficha do Prospect (CONSTITUICAO §12.1, tela 3): qualificação, dossiê, auditoria com evidências, linha do
 * tempo e o mini-relatório (§8.3) para baixar. Botões de outras fases (assumir conversa, proposta) ainda não existem.
 */
export default function FichaDoProspect() {
  const { id } = useParams<{ id: string }>();
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [erro, setErro] = useState("");
  const [anuncio, setAnuncio] = useState("");
  const [baixando, setBaixando] = useState(false);
  const [usuario, setUsuario] = useState<UsuarioAtual | null>(null);
  const [movendo, setMovendo] = useState(false);

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    apiFetch<Ficha>(`/empresas/${id}/ficha`)
      .then(setFicha)
      .catch((e) => setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar a ficha."));
    apiFetch<UsuarioAtual>("/auth/me")
      .then(setUsuario)
      .catch(() => setUsuario(null));
  }, [id]);

  async function baixarPdf() {
    if (baixando || !ficha) return;
    setBaixando(true);
    setErro("");
    setAnuncio("Preparando o PDF…");
    try {
      const blob = await baixarArquivo(`/empresas/${id}/relatorio.pdf`);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `diagnostico-acessibilidade-${(ficha.empresa.dominio ?? "empresa").replace(/\./g, "-")}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
      setAnuncio("Download do relatório iniciado.");
    } catch (e) {
      setAnuncio("");
      setErro(e instanceof ErroApi ? e.message : "Não foi possível baixar o relatório.");
    } finally {
      setBaixando(false);
    }
  }

  async function abrirVersaoWeb() {
    setErro("");
    try {
      const blob = await baixarArquivo(`/empresas/${id}/relatorio`);
      window.open(URL.createObjectURL(blob), "_blank", "noopener");
      setAnuncio("Versão web do relatório aberta em nova aba.");
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível abrir o relatório.");
    }
  }

  if (!ficha) {
    return (
      <>
        <h1>Ficha do prospect</h1>
        <div role="status" aria-live="polite">{erro ? "" : "Carregando…"}</div>
        <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>
        <p><a href="/">Voltar ao painel</a></p>
      </>
    );
  }

  const { empresa, dossie, auditoria } = ficha;
  return (
    <>
      <p><a href="/">← Voltar ao painel</a></p>
      <h1>{empresa.nome}</h1>
      <dl className="resumo">
        <div>
          <dt>Site</dt>
          <dd>{empresa.dominio ?? "Ainda não identificado"}</dd>
        </div>
        <div>
          <dt>Estado</dt>
          <dd>
            {ROTULO_ESTADO[empresa.estado] ?? empresa.estado}
            {(usuario?.papel === "admin" || usuario?.papel === "vendedor") && (ficha.destinos?.length ?? 0) > 0 && (
              <>
                {" "}
                <button type="button" id="mudar-estado" className="link" onClick={() => setMovendo(true)}>
                  Mudar estado…
                </button>
              </>
            )}
          </dd>
        </div>
        {empresa.setor && (
          <div>
            <dt>Setor</dt>
            <dd>{ROTULO_SETOR[empresa.setor] ?? empresa.setor}</dd>
          </div>
        )}
        {(empresa.cidade || empresa.uf) && (
          <div>
            <dt>Localização</dt>
            <dd>{[empresa.cidade, empresa.uf].filter(Boolean).join(" / ")}</dd>
          </div>
        )}
      </dl>

      {ficha.qualificacao && <QualificacaoDaEmpresa qualificacao={ficha.qualificacao} />}
      {ficha.qualificacao && <DecisoresDaEmpresa decisores={ficha.decisores ?? []} />}

      <section className="card acoes-ficha" aria-labelledby="titulo-relatorio" style={{ marginTop: "1.5rem" }}>
        <h2 id="titulo-relatorio" style={{ marginTop: 0 }}>Mini-relatório</h2>
        {ficha.relatorio_disponivel ? (
          <div className="row">
            <button type="button" onClick={baixarPdf} aria-disabled={baixando}>
              Baixar relatório (PDF)
            </button>
            <button type="button" className="secundario" onClick={abrirVersaoWeb}>
              Ver versão web
            </button>
          </div>
        ) : (
          <p className="hint">O relatório fica disponível quando a análise da auditoria termina.</p>
        )}
        <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>{anuncio}</div>
        <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>
      </section>

      {dossie && (
        <section className="card" aria-labelledby="titulo-dossie" style={{ marginTop: "1.5rem" }}>
          <h2 id="titulo-dossie" style={{ marginTop: 0 }}>Dossiê</h2>
          <ul className="resumo-dossie">
            {dossie.resumo.map((linha, i) => (
              <li key={i}>{linha}</li>
            ))}
          </ul>
          {dossie.descricao && <p>{dossie.descricao}</p>}
          {dossie.produtos_servicos.length > 0 && (
            <>
              <h3>Produtos e serviços</h3>
              <p>{dossie.produtos_servicos.join(" · ")}</p>
            </>
          )}
          {dossie.publicos_atendidos.length > 0 && (
            <>
              <h3>Públicos atendidos</h3>
              <p>{dossie.publicos_atendidos.join(" · ")}</p>
            </>
          )}
          <h3>O que o site diz sobre inclusão e ESG</h3>
          {dossie.mencoes_inclusao.length ? (
            <ul>
              {dossie.mencoes_inclusao.map((m, i) => (
                <li key={i}>
                  <strong>{TEMA[m.tema] ?? m.tema}:</strong> “{m.trecho}”{" "}
                  <a href={m.url} target="_blank" rel="noopener noreferrer">
                    fonte: {caminho(m.url)}
                    <span className="visually-hidden"> (abre em nova aba)</span>
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">Nenhuma menção encontrada nas páginas lidas.</p>
          )}
          {dossie.sinais.length > 0 && (
            <>
              <h3>Sinais de interesse</h3>
              <ul>
                {dossie.sinais.map((s, i) => (
                  <li key={i}>{s.descricao}</li>
                ))}
              </ul>
            </>
          )}
          {dossie.lacunas.length > 0 && (
            <>
              <h3>O que não encontramos</h3>
              <ul>
                {dossie.lacunas.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            </>
          )}
          <details>
            <summary>Páginas lidas e tecnologia do site</summary>
            <ul>
              {dossie.paginas_lidas.map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
            {dossie.tecnologias_site.length > 0 && <p>Tecnologia: {dossie.tecnologias_site.join(", ")}</p>}
          </details>
        </section>
      )}

      {auditoria && (
        <section className="card" style={{ marginTop: "1.5rem" }} aria-label="Auditoria">
          <AuditoriaTecnica auditoria={auditoria} />
          {ficha.evidencias.length > 0 && (
            <>
              <h4>Evidências dos achados</h4>
              <ol className="evidencias">
                {ficha.evidencias.map((ev) => (
                  <li key={ev.numero}>
                    <p className="achado-titulo">
                      {ev.numero}. {ev.titulo} <span className="hint">(página {ev.pagina})</span>
                    </p>
                    <PrintDaEvidencia empresaId={id} evidencia={ev} />
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      )}

      {usuario?.papel === "admin" && auditoria?.nota !== null && auditoria?.analise && (
        <RevisaoAuditoria auditoriaId={auditoria.id} />
      )}

      {movendo && (
        <MoverEstado
          empresa={{ id: empresa.id, nome: empresa.nome, estado: empresa.estado }}
          destinos={ficha.destinos ?? []}
          aoMover={(novo) => {
            setMovendo(false);
            setAnuncio(`Estado alterado para ${ROTULO_ESTADO[novo.estado] ?? novo.estado}.`);
            apiFetch<Ficha>(`/empresas/${id}/ficha`)
              .then(setFicha)
              .catch(() => undefined);
            requestAnimationFrame(() => document.getElementById("mudar-estado")?.focus());
          }}
          aoConflito={(mensagem) => {
            setMovendo(false);
            setErro(mensagem);
            apiFetch<Ficha>(`/empresas/${id}/ficha`)
              .then(setFicha)
              .catch(() => undefined);
          }}
          aoFechar={() => {
            setMovendo(false);
            requestAnimationFrame(() => document.getElementById("mudar-estado")?.focus());
          }}
        />
      )}

      <section className="card" aria-labelledby="titulo-linha" style={{ marginTop: "1.5rem" }}>
        <h2 id="titulo-linha" style={{ marginTop: 0 }}>Linha do tempo</h2>
        <ol className="linha-do-tempo">
          {ficha.eventos.map((ev) => (
            <li key={ev.id}>
              <time dateTime={ev.ocorrido_em}>{horario(ev.ocorrido_em)}</time>
              <span>{ev.mensagem}</span>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
