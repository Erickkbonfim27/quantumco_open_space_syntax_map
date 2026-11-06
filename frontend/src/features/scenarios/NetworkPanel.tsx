import { useState } from "react";

import { formatMeters } from "../../lib/format";
import type { NetworkEdit, ScenarioRun } from "../../lib/platformTypes";
import type { Measure, NetworkCollection, RadiusKey } from "../../lib/types";
import { EDIT_COLORS } from "../map/MapView";
import { DELTA_COLORS, MEASURE_LABEL, RADII } from "../map/syntaxPalette";
import { CONNECT_NOTE, EDIT_LABEL, type EditTool, lineLength, sameEdits, STAGE_LABEL, STAGES } from "./edits";
import { useTicker } from "./useScenarioRun";

export type ResultView = "atual" | "cenario" | "diferenca";

const TOOL_ICON: Record<EditTool, string> = {
  remove: "M6 6l12 12 M18 6L6 18",
  close: "M4 9h16v6H4z M8 9l-3 6 M13 9l-3 6 M18 9l-3 6",
  add: "M4 19L19 4 M4 19l0.1 0 M19 4l0.1 0 M14 4h5v5",
  reroute: "M4 18c4 0 4-12 8-12s4 12 8 12",
};

const km = (v: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${String(s % 60).padStart(2, "0")} s`;
}

interface NetworkPanelProps {
  edits: NetworkEdit[];
  tool: EditTool | null;
  rerouteTarget: string | null;
  draftVertices: number;
  saving: boolean;
  network: NetworkCollection;
  onTool: (tool: EditTool | null) => void;
  onRemoveEdit: (index: number) => void;
  onClear: () => void;
  onFocusEdit: (edit: NetworkEdit) => void;
}

/** Ferramentas e lista de edições da rede. */
export function EditsSection(props: NetworkPanelProps) {
  const { edits, tool, rerouteTarget, draftVertices, saving, network } = props;
  const lengthOf = (id: string | undefined) => network.features.find((f) => f.properties.link_id === id)?.properties;
  const hint = tool === "reroute" && rerouteTarget ? "Agora desenhe o novo traçado da via #" + rerouteTarget + "." : tool ? EDIT_LABEL[tool].hint : null;
  return (
    <div className="ws-section ws-section-first">
      <div className="row-between">
        <span className="label">EDITAR A REDE</span>
        {saving && <span className="muted-2 small">salvando…</span>}
      </div>
      <div className="edit-tools" role="toolbar" aria-label="Ferramentas de edição da rede">
        {(Object.keys(EDIT_LABEL) as EditTool[]).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={tool === key}
            className={tool === key ? "edit-tool edit-tool-on" : "edit-tool"}
            onClick={() => props.onTool(tool === key ? null : key)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={EDIT_COLORS[key]} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d={TOOL_ICON[key]} />
            </svg>
            {EDIT_LABEL[key].verb}
          </button>
        ))}
      </div>
      {hint && (
        <div className="draw-hint edit-hint">
          {hint}
          {(tool === "add" || (tool === "reroute" && rerouteTarget)) && (
            <>
              <br />
              <span className="muted small">{CONNECT_NOTE}</span>
              {draftVertices > 0 && <span className="mono small edit-count"> · {draftVertices} ponto(s)</span>}
            </>
          )}
        </div>
      )}

      <div className="row-between">
        <span className="label">EDIÇÕES ({edits.length})</span>
        {edits.length > 0 && (
          <button type="button" className="link-btn small" onClick={props.onClear}>
            Limpar tudo
          </button>
        )}
      </div>
      {edits.length === 0 ? (
        <p className="muted small edit-empty">
          Nenhuma edição. Escolha uma ferramenta acima e clique no mapa: remova ou interdite ruas, crie
          ligações novas ou mude o traçado de uma via. Depois, calcule o cenário.
        </p>
      ) : (
        <ul className="edit-list">
          {edits.map((edit, index) => {
            const base = lengthOf(edit.link_id);
            const detail =
              edit.type === "add"
                ? `${formatMeters(lineLength(edit.coords))} · ${edit.coords?.length ?? 0} pontos`
                : `#${edit.link_id}${base ? ` · ${formatMeters(base.length_m)}` : ""}${edit.type === "reroute" ? ` → ${formatMeters(lineLength(edit.coords))}` : ""}`;
            return (
              <li key={`${edit.type}-${edit.link_id ?? index}`}>
                <button type="button" className="edit-item" onClick={() => props.onFocusEdit(edit)}>
                  <span className="edit-swatch" style={{ background: EDIT_COLORS[edit.type] }} aria-hidden="true" />
                  <span className="poly-text">
                    <span>{edit.label || EDIT_LABEL[edit.type].noun}</span>
                    <span className="mono muted-2 small">{detail}</span>
                  </span>
                </button>
                <button type="button" className="poly-del" aria-label={`Desfazer ${EDIT_LABEL[edit.type].noun}`} onClick={() => props.onRemoveEdit(index)}>
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

interface RunSectionProps {
  edits: NetworkEdit[];
  run: ScenarioRun | null;
  offset: number;
  busy: boolean;
  error: string;
  measure: Measure;
  radius: RadiusKey;
  view: ResultView;
  resultReady: boolean;
  onRequest: (radii: RadiusKey[]) => void;
  onCancel: () => void;
  onView: (view: ResultView) => void;
}

/** Ordem da metodologia (a do pedido e a da lista personalizada). */
const ORDER: RadiusKey[] = ["400", "800", "1200", "2000", "n"];

type ScopeKey = "caminhada" | "bairro" | "cidade" | "personalizado";
const SCOPES: { key: ScopeKey; label: string; radii: RadiusKey[] | null; hint: string }[] = [
  { key: "caminhada", label: "Caminhada", radii: ["400", "800"], hint: "400 e 800 m · recalcula até 1,6 km em volta das edições · o mais rápido" },
  { key: "bairro", label: "Bairro", radii: ["400", "800", "1200", "2000"], hint: "400 m a 2 km · recalcula até 4 km em volta das edições · rápido" },
  { key: "cidade", label: "Cidade", radii: ORDER, hint: "todos os raios, inclusive n · a rede inteira · vários minutos" },
  { key: "personalizado", label: "Escolher", radii: null, hint: "marque os raios; com n, a rede inteira" },
];

const radiusText = (key: string) => RADII.find((r) => r.key === key)?.label ?? key;

/** Até onde um cálculo local muda valores: 2× o maior raio (um caminho que passa pela edição
 * pode desviar por trechos até um raio além da origem). Com n, a rede inteira. */
const reachText = (radii: readonly string[]) => {
  if (radii.length === 0 || radii.includes("n")) return null;
  const m = 2 * Math.max(...radii.map(Number));
  return m >= 1000 ? `${(m / 1000).toLocaleString("pt-BR")} km` : `${m} m`;
};

/** Cálculo do cenário: pedido, posição na fila, etapas com tempos e resultado. */
export function RunSection({ edits, run, offset, busy, error, measure, radius, view, resultReady, ...on }: RunSectionProps) {
  const isActive = run?.status === "queued" || run?.status === "running";
  const now = useTicker(isActive) + offset;
  const changed = run && !sameEdits(run.edit_list, edits);
  const canRequest = edits.length > 0 && !isActive && !busy;
  const current = run?.stages[run.stages.length - 1];
  const engine = run?.stages.find((s) => s.stage === "engine");
  const expected = run?.expected_engine_seconds ?? null;
  const engineElapsed = engine ? (engine.seconds ?? (now - Date.parse(engine.at)) / 1000) : 0;
  const total = run ? ((run.finished_at ? Date.parse(run.finished_at) : now) - Date.parse(run.created_at)) / 1000 : 0;
  // resumo de km: o raio do mapa se ele tem resumo; senão 800 m ou n (os que o motor resume)
  const summary = run?.result?.summary ?? {};
  const summaryKey = [`${measure}_${radius}`, `${measure}_800`, `${measure}_n`].find((k) => k in summary);
  const change = summaryKey ? summary[summaryKey] : undefined;
  const summaryRadius = summaryKey ? summaryKey.split("_")[1] ?? "" : "";
  const computed = run?.result?.radii ?? run?.radii ?? ORDER;
  const wholeCity = (run?.radii ?? ORDER).includes("n");

  const [scope, setScope] = useState<ScopeKey>("bairro");
  const [custom, setCustom] = useState<RadiusKey[]>(["400", "800"]);
  const chosen = SCOPES.find((s) => s.key === scope)?.radii ?? custom;
  const toggleCustom = (key: RadiusKey) =>
    setCustom((list) => (list.includes(key) ? list.filter((k) => k !== key) : ORDER.filter((k) => k === key || list.includes(k))));

  return (
    <div className="ws-section">
      <span className="label">CÁLCULO DO CENÁRIO</span>
      {!run && (
        <p className="muted small">
          Recalcula a sintaxe com as suas edições e compara com o mapa atual. Sem o raio n, só a região que a edição pode
          alterar é recalculada: o resultado é igual ao da cidade inteira, em bem menos tempo.
        </p>
      )}

      {run && (
        <div className={`run-card run-${run.status}`} aria-live="polite">
          <div className="row-between">
            <span className="run-status">
              {run.status === "queued" && "Na fila"}
              {run.status === "running" && "Processando"}
              {run.status === "done" && "Pronto"}
              {run.status === "failed" && "Não deu certo"}
              {run.status === "canceled" && "Cancelado"}
            </span>
            <span className="mono muted-2 small">{duration(total)}</span>
          </div>

          {run.status === "queued" && (
            <p className="small soft run-queue">
              {run.queue.position === 1 ? "Você é o próximo." : `Posição ${run.queue.position} na fila.`}{" "}
              {run.queue.running > 0 && `${run.queue.running} cálculo(s) em andamento. `}
              {run.queue.workers === 0
                ? "Nenhum processador ligado agora: o cálculo começa quando ele voltar."
                : run.queue.workers
                  ? `${run.queue.workers} processador(es) ativos.`
                  : ""}
            </p>
          )}

          {(isActive || run.status === "failed") && (
            <ol className="run-steps">
              {STAGES.map((stage) => {
                const record = run.stages.find((s) => s.stage === stage);
                const isCurrent = isActive && current?.stage === stage;
                const done = record && !isCurrent && record.seconds !== null;
                const state = isCurrent ? "run-step-now" : done ? "run-step-done" : "run-step-wait";
                const seconds = isCurrent && record ? (now - Date.parse(record.at)) / 1000 : record?.seconds;
                return (
                  <li key={stage} className={state}>
                    <span className="run-dot" aria-hidden="true" />
                    <span>{STAGE_LABEL[stage]}</span>
                    <span className="mono muted-2 small">{seconds != null && (done || isCurrent) ? duration(seconds) : ""}</span>
                  </li>
                );
              })}
            </ol>
          )}

          {run.status === "running" && current?.stage === "engine" && (
            <div className="run-progress">
              <div className="run-bar">
                <span style={{ width: `${expected ? Math.min(96, (engineElapsed / expected) * 100) : 30}%` }} className={expected ? "" : "run-bar-indeterminate"} />
              </div>
              <span className="muted-2 small">
                {expected
                  ? engineElapsed < expected
                    ? `estimativa: ~${duration(expected - engineElapsed)} restantes`
                    : "quase lá (passou da média)"
                  : wholeCity
                    ? "o motor leva vários minutos na cidade inteira"
                    : "só a região afetada: costuma ser rápido"}
              </span>
            </div>
          )}

          {run.status === "failed" && <div className="form-error">{run.error}</div>}

          {run.status === "done" && run.result && (
            <>
              {change ? (
                <div className="run-summary">
                  <div>
                    <span className="stat-value delta-up">+{km(change.km_up)}</span>
                    <span className="muted-2 small">km subiram de classe</span>
                  </div>
                  <div>
                    <span className="stat-value delta-down">−{km(change.km_down)}</span>
                    <span className="muted-2 small">km caíram de classe</span>
                  </div>
                </div>
              ) : null}
              <span className="muted-2 small">
                {summaryKey ? `${MEASURE_LABEL[measure]} · R ${radiusText(summaryRadius)} · em Brusque · ` : ""}motor{" "}
                {duration(run.result.engine_seconds)}
              </span>
              <span className="muted-2 small">
                Raios: {computed.map(radiusText).join(", ")} ·{" "}
                {run.result.scope === "regiao"
                  ? `só até ${reachText(computed) ?? "?"} em volta das edições (${(run.result.region_links ?? 0).toLocaleString("pt-BR")} trechos; o resto não muda)`
                  : "rede inteira"}
              </span>
              <div className="segmented segmented-3 run-views" role="radiogroup" aria-label="O que mostrar no mapa">
                {(
                  [
                    ["atual", "Mapa atual"],
                    ["cenario", "Cenário"],
                    ["diferenca", "Diferença"],
                  ] as const
                ).map(([key, label]) => (
                  <button key={key} type="button" role="radio" aria-checked={view === key} disabled={key !== "atual" && !resultReady} onClick={() => on.onView(key)}>
                    {label}
                  </button>
                ))}
              </div>
              {!resultReady && <span className="muted-2 small">carregando o resultado…</span>}
            </>
          )}

          {changed && !isActive && run.status === "done" && (
            <div className="run-stale small">As edições mudaram depois deste cálculo. Calcule de novo para ver o efeito.</div>
          )}
        </div>
      )}

      {error && <div className="form-error">{error}</div>}

      {!isActive && (
        <div className="run-scope">
          <span className="label ws-sublabel">ALCANCE</span>
          <div className="segmented segmented-4" role="radiogroup" aria-label="Alcance do cálculo">
            {SCOPES.map((s) => (
              <button key={s.key} type="button" role="radio" aria-checked={scope === s.key} onClick={() => setScope(s.key)}>
                {s.label}
              </button>
            ))}
          </div>
          {scope === "personalizado" && (
            <div className="run-radii" role="group" aria-label="Raios a calcular">
              {ORDER.map((key) => (
                <label key={key} className="run-radius">
                  <input type="checkbox" checked={custom.includes(key)} onChange={() => toggleCustom(key)} />
                  {key === "n" ? "n (cidade)" : radiusText(key)}
                </label>
              ))}
            </div>
          )}
          <span className="muted-2 small">
            {scope === "personalizado"
              ? reachText(custom)
                ? `recalcula até ${reachText(custom)} em volta das edições`
                : chosen.length > 0
                  ? "com n, a rede inteira · vários minutos"
                  : SCOPES.find((s) => s.key === scope)?.hint
              : SCOPES.find((s) => s.key === scope)?.hint}
          </span>
        </div>
      )}

      <div className="row-gap">
        {run?.status === "queued" && (
          <button type="button" className="pill pill-outline pill-sm" disabled={busy} onClick={on.onCancel}>
            Cancelar
          </button>
        )}
        {!isActive && (
          <button
            type="button"
            className="pill pill-green pill-sm"
            disabled={!canRequest || chosen.length === 0}
            onClick={() => on.onRequest(chosen)}
          >
            {run && run.status !== "canceled" ? "Calcular de novo" : "Calcular cenário"}
          </button>
        )}
        {!isActive && edits.length === 0 && <span className="muted-2 small">adicione uma edição primeiro</span>}
        {!isActive && edits.length > 0 && chosen.length === 0 && <span className="muted-2 small">marque pelo menos um raio</span>}
      </div>
      <p className="muted-2 small">Pode fechar a página; o resultado fica salvo no cenário.</p>
    </div>
  );
}

const DELTA_LEGEND: [string, string][] = [
  [DELTA_COLORS.gainStrong, "ganhou 2+ classes"],
  [DELTA_COLORS.gain, "ganhou 1 classe"],
  [DELTA_COLORS.same, "sem mudança"],
  [DELTA_COLORS.loss, "perdeu 1 classe"],
  [DELTA_COLORS.lossStrong, "perdeu 2+ classes"],
  [EDIT_COLORS.remove, "via removida"],
  [EDIT_COLORS.close, "via interditada"],
  [DELTA_COLORS.added, "via nova"],
];

/** Legenda das cores de mudança (fora da escala sintática). */
export function DeltaLegend() {
  return (
    <div className="ws-section">
      <span className="label">DIFERENÇA PARA O MAPA ATUAL</span>
      <ul className="legend">
        {DELTA_LEGEND.map(([color, label]) => (
          <li key={label}>
            <span className="swatch" style={{ height: 3, background: color }} aria-hidden="true" />
            {label}
          </li>
        ))}
      </ul>
      <span className="muted-2 small">Classes do cenário pelos mesmos cortes do mapa atual, para os ganhos e perdas aparecerem.</span>
    </div>
  );
}
