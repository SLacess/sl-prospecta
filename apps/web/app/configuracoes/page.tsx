"use client";

import { type FormEvent, useEffect, useState } from "react";

import {
  apiFetch,
  type ChaveComponente,
  COMPONENTES_SCORE,
  type ConfigScore,
  ErroApi,
  lerToken,
  ROTULO_COMPONENTE,
  type UsuarioAtual,
} from "@/lib/api";

type Formulario = { pesos: Record<ChaveComponente, string>; quente: string; morno: string };

function paraFormulario(c: ConfigScore): Formulario {
  const pesos = Object.fromEntries(
    COMPONENTES_SCORE.map((k) => [k, String(Math.round(c.pesos[k] * 100))]),
  ) as Record<ChaveComponente, string>;
  return { pesos, quente: String(c.faixas.quente), morno: String(c.faixas.morno) };
}

function inteiro(texto: string): number | null {
  return /^\d{1,3}$/.test(texto.trim()) ? Number(texto) : null;
}

/** Mesmas regras da API e do Qualificador: pesos somam 100% e 0 < Morno < Quente ≤ 100. */
function validar(f: Formulario): { campos: Partial<Record<string, string>>; soma: number | null } {
  const campos: Partial<Record<string, string>> = {};
  let soma = 0;
  for (const k of COMPONENTES_SCORE) {
    const v = inteiro(f.pesos[k]);
    if (v === null || v > 100) campos[k] = "Use um número inteiro de 0 a 100.";
    else soma += v;
  }
  const quente = inteiro(f.quente);
  const morno = inteiro(f.morno);
  if (quente === null || quente < 1 || quente > 100) campos.quente = "Use um número inteiro de 1 a 100.";
  if (morno === null || morno < 1 || morno > 100) campos.morno = "Use um número inteiro de 1 a 100.";
  if (!campos.quente && !campos.morno && morno! >= quente!) {
    campos.morno = "O início da faixa Morno precisa ser menor que o da faixa Quente.";
  }
  const pesosValidos = COMPONENTES_SCORE.every((k) => !campos[k]);
  return { campos, soma: pesosValidos ? soma : null };
}

/**
 * Configurações → Score (CONSTITUICAO §12.1, item 6, e §7.3): pesos dos 5 componentes e faixas quente/morno/frio.
 * Só o admin altera; os outros perfis veem os valores em vigor.
 */
export default function ConfiguracoesScore() {
  const [config, setConfig] = useState<ConfigScore | null>(null);
  const [form, setForm] = useState<Formulario | null>(null);
  const [usuario, setUsuario] = useState<UsuarioAtual | null>(null);
  const [erro, setErro] = useState("");
  const [anuncio, setAnuncio] = useState("");
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    if (!lerToken()) {
      window.location.replace("/login");
      return;
    }
    apiFetch<ConfigScore>("/config/score")
      .then((c) => {
        setConfig(c);
        setForm(paraFormulario(c));
      })
      .catch((e) => setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar a configuração."));
    apiFetch<UsuarioAtual>("/auth/me")
      .then(setUsuario)
      .catch(() => setUsuario(null));
  }, []);

  const admin = usuario?.papel === "admin";
  const validacao = form ? validar(form) : null;

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (!form || !validacao || salvando) return;
    setTentou(true);
    setErro("");
    setAnuncio("");
    const problemas = Object.keys(validacao.campos).length;
    if (problemas || validacao.soma !== 100) {
      setErro(
        validacao.soma !== null && validacao.soma !== 100
          ? `Os pesos precisam somar 100% (hoje somam ${validacao.soma}%).`
          : "Corrija os campos indicados antes de salvar.",
      );
      const primeiro = COMPONENTES_SCORE.find((k) => validacao.campos[k]) ??
        (validacao.campos.quente ? "quente" : validacao.campos.morno ? "morno" : COMPONENTES_SCORE[0]);
      document.getElementById(`campo-${primeiro}`)?.focus();
      return;
    }
    setSalvando(true);
    try {
      const corpo: ConfigScore = {
        pesos: Object.fromEntries(
          COMPONENTES_SCORE.map((k) => [k, Number(form.pesos[k]) / 100]),
        ) as ConfigScore["pesos"],
        faixas: { quente: Number(form.quente), morno: Number(form.morno) },
      };
      const salvo = await apiFetch<ConfigScore>("/config/score", { method: "PUT", body: JSON.stringify(corpo) });
      setConfig(salvo);
      setForm(paraFormulario(salvo));
      setTentou(false);
      setAnuncio(
        "Pesos e faixas salvos. Valem para as próximas qualificações; as atuais mudam quando forem recalculadas.",
      );
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível salvar a configuração.");
    } finally {
      setSalvando(false);
    }
  }

  function campo(id: string, rotulo: string, valor: string, aoMudar: (v: string) => void, sufixo: string) {
    const msg = tentou ? validacao?.campos[id] : undefined;
    return (
      <div key={id}>
        <label htmlFor={`campo-${id}`}>
          {rotulo} <span className="hint">({sufixo})</span>
        </label>
        <input
          id={`campo-${id}`}
          type="number"
          inputMode="numeric"
          min={0}
          max={100}
          step={1}
          required
          value={valor}
          onChange={(e) => aoMudar(e.target.value)}
          aria-invalid={msg ? true : undefined}
          aria-describedby={msg ? `erro-${id}` : undefined}
        />
        {msg && (
          <p className="erro-campo" id={`erro-${id}`}>
            {msg}
          </p>
        )}
      </div>
    );
  }

  return (
    <>
      <h1>Configurações do score</h1>
      <p className="lead">
        O score de cada empresa soma cinco componentes, cada um valendo de 0 a 100, multiplicados pelos pesos abaixo
        (CONSTITUIÇÃO §7.3). A faixa decide o próximo passo: Quente e Morno seguem para o mapeamento de decisores; Frio
        fica para o vendedor decidir.
      </p>
      <div role="alert" className={erro ? "status error" : undefined}>{erro}</div>
      <div role="status" aria-live="polite" className={anuncio ? "status" : undefined}>{anuncio}</div>

      {config && form && !admin && (
        <section className="card" aria-labelledby="titulo-vigentes">
          <h2 id="titulo-vigentes" style={{ marginTop: 0 }}>Valores em vigor</h2>
          <dl className="resumo">
            {COMPONENTES_SCORE.map((k) => (
              <div key={k}>
                <dt>{ROTULO_COMPONENTE[k]}</dt>
                <dd>{form.pesos[k]}%</dd>
              </div>
            ))}
            <div>
              <dt>Quente</dt>
              <dd>a partir de {config.faixas.quente}</dd>
            </div>
            <div>
              <dt>Morno</dt>
              <dd>
                de {config.faixas.morno} a {config.faixas.quente - 1}
              </dd>
            </div>
            <div>
              <dt>Frio</dt>
              <dd>abaixo de {config.faixas.morno}</dd>
            </div>
          </dl>
          <p className="hint">Só o perfil admin altera os pesos e as faixas.</p>
        </section>
      )}

      {config && form && admin && (
        <form className="card" onSubmit={salvar} noValidate aria-labelledby="titulo-pesos">
          <h2 id="titulo-pesos" style={{ marginTop: 0 }}>Pesos dos componentes</h2>
          <div className="grade-pesos">
            {COMPONENTES_SCORE.map((k) =>
              campo(k, ROTULO_COMPONENTE[k], form.pesos[k], (v) => setForm({ ...form, pesos: { ...form.pesos, [k]: v } }), "%"),
            )}
          </div>
          <p className="soma-pesos" aria-live="polite">
            Soma dos pesos: {validacao?.soma ?? "—"}% {validacao?.soma === 100 ? "(ok)" : "(precisa ser 100%)"}
          </p>

          <h2>Faixas</h2>
          <div className="grade-pesos">
            {campo("quente", "Quente a partir de", form.quente, (v) => setForm({ ...form, quente: v }), "pontos")}
            {campo("morno", "Morno a partir de", form.morno, (v) => setForm({ ...form, morno: v }), "pontos")}
          </div>
          <p className="hint">Abaixo do início da faixa Morno, a empresa fica Fria.</p>
          <div className="row" style={{ marginTop: "1rem" }}>
            <button type="submit" aria-disabled={salvando}>
              {salvando ? "Salvando…" : "Salvar pesos e faixas"}
            </button>
          </div>
          <p className="hint">
            Para recalcular as empresas já qualificadas com os pesos novos, rode no worker:{" "}
            <code>python -m slp_workers.cli qualificar --todas</code>
          </p>
        </form>
      )}
    </>
  );
}
