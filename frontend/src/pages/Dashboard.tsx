import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { PlatformBar } from "../components/PlatformBar";
import { api, ApiError } from "../lib/api";
import {
  MEASURE_SHORT,
  STATUS_COLOR,
  STATUS_LABEL,
  type Workspace,
  type WorkspaceMeasure,
  type WorkspaceStatus,
} from "../lib/platformTypes";
import { useSession } from "../lib/session";

const FILTERS: ("todos" | WorkspaceStatus)[] = ["todos", "em_analise", "publicado", "rascunho"];
const relative = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });
const shortDate = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "short", year: "numeric" });

function updatedLabel(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "agora";
  if (diff < 3600) return relative.format(-Math.round(diff / 60), "minute");
  if (diff < 86400) return relative.format(-Math.round(diff / 3600), "hour");
  if (diff < 86400 * 7) return relative.format(-Math.round(diff / 86400), "day");
  return shortDate.format(new Date(iso));
}

function greeting(name: string): string {
  const h = new Date().getHours();
  const hello = h < 12 ? "BOM DIA" : h < 18 ? "BOA TARDE" : "BOA NOITE";
  return `${hello}, ${name.split(" ")[0]?.toUpperCase() ?? ""}`;
}

/** Miniatura com os polígonos reais do cenário (ou a marca vazia, se ainda não há nenhum). */
function Thumb({ workspace }: { workspace: Workspace }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const g = canvas?.getContext("2d");
    if (!canvas || !g) return;
    const dpr = window.devicePixelRatio || 1;
    const W = 88;
    const H = 56;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const rings = workspace.features.map((f) => f.geometry.coordinates[0] ?? []);
    const points = rings.flat();
    if (points.length === 0) {
      g.strokeStyle = "rgba(244,246,245,.18)";
      g.setLineDash([3, 3]);
      g.strokeRect(10.5, 10.5, W - 21, H - 21);
      return;
    }
    const xs = points.map((p) => p[0] ?? 0);
    const ys = points.map((p) => p[1] ?? 0);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const scale = Math.min((W - 16) / (x1 - x0 || 1), (H - 16) / (y1 - y0 || 1));
    const X = (x: number) => W / 2 + (x - (x0 + x1) / 2) * scale;
    const Y = (y: number) => H / 2 - (y - (y0 + y1) / 2) * scale;
    rings.forEach((ring) => {
      g.beginPath();
      ring.forEach(([x = 0, y = 0], i) => (i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y))));
      g.closePath();
      g.fillStyle = "rgba(43,212,107,.12)";
      g.fill();
      g.strokeStyle = "#2BD46B";
      g.lineWidth = 1.2;
      g.stroke();
    });
  }, [workspace]);
  return <canvas ref={ref} className="thumb" aria-hidden="true" />;
}

export function Dashboard() {
  const navigate = useNavigate();
  const { user } = useSession();
  const [items, setItems] = useState<Workspace[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("todos");
  const [newOpen, setNewOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newMeasure, setNewMeasure] = useState<WorkspaceMeasure>("nain");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api<Workspace[]>("workspaces")
      .then(setItems)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : String(err)));
  }, []);

  const counts = useMemo(() => {
    const all = items ?? [];
    return Object.fromEntries(
      FILTERS.map((f) => [f, f === "todos" ? all.length : all.filter((w) => w.status === f).length]),
    ) as Record<(typeof FILTERS)[number], number>;
  }, [items]);

  const rows = (items ?? []).filter((w) => {
    const q = query.trim().toLowerCase();
    return (
      (filter === "todos" || w.status === filter) &&
      (!q || `${w.name} ${w.area}`.toLowerCase().includes(q))
    );
  });

  const create = async () => {
    setCreating(true);
    try {
      const created = await api<Workspace>("workspaces", {
        method: "POST",
        json: { name: newName.trim() || "Cenário sem nome", measure: newMeasure },
      });
      navigate(`/painel/cenario/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setCreating(false);
    }
  };

  if (!user) return null;
  return (
    <div className="platform">
      <PlatformBar active="cenarios" />
      <main className="dash">
        <div className="dash-head">
          <div className="dash-title">
            <span className="label">{greeting(user.name)}</span>
            <h1>Cenários</h1>
          </div>
          <span className="spacer" />
          <input
            className="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar cenário"
            aria-label="Buscar cenário"
          />
          <button type="button" className="pill pill-green" onClick={() => setNewOpen(true)}>
            + Novo cenário
          </button>
        </div>

        <div className="filters" role="tablist" aria-label="Filtrar por status">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={filter === f}
              className={filter === f ? "chip chip-on" : "chip"}
              onClick={() => setFilter(f)}
            >
              {f === "todos" ? "Todos" : STATUS_LABEL[f]}
              <span className="mono chip-count">{counts[f]}</span>
            </button>
          ))}
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="table" role="table" aria-label="Seus cenários">
          <div className="table-head" role="row">
            <span />
            <span>CENÁRIO</span>
            <span>POLÍGONOS</span>
            <span>MEDIDA</span>
            <span>ATUALIZADO</span>
            <span>STATUS</span>
            <span />
          </div>
          <div className="table-body">
            {items === null && !error && <div className="table-empty">Carregando…</div>}
            {items !== null && rows.length === 0 && (
              <div className="table-empty">
                {items.length === 0
                  ? "Nenhum cenário ainda. Crie o primeiro para desenhar polígonos sobre o mapa."
                  : "Nenhum cenário encontrado."}
              </div>
            )}
            {rows.map((w) => (
              <button
                key={w.id}
                type="button"
                className="table-row"
                role="row"
                onClick={() => navigate(`/painel/cenario/${w.id}`)}
              >
                <Thumb workspace={w} />
                <span className="row-name">
                  <span className="row-title">{w.name}</span>
                  <span className="row-sub">{w.area}</span>
                </span>
                <span className="mono">{w.polygons === 0 ? "—" : w.polygons}</span>
                <span className="soft">{MEASURE_SHORT[w.measure]}</span>
                <span className="soft">{updatedLabel(w.updated_at)}</span>
                <span className="status">
                  <span className="status-dot" style={{ background: STATUS_COLOR[w.status] }} />
                  {STATUS_LABEL[w.status]}
                </span>
                <span className="row-go" aria-hidden="true">
                  →
                </span>
              </button>
            ))}
          </div>
        </div>
      </main>

      {newOpen && (
        <div className="modal-backdrop" onClick={() => setNewOpen(false)} role="presentation">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="new-title">Novo cenário</h2>
              <button type="button" className="icon-circle" onClick={() => setNewOpen(false)} aria-label="Fechar">
                ×
              </button>
            </div>
            <label className="input-field">
              <span className="label">NOME</span>
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void create()}
                placeholder="Ex.: Centro expandido 2030"
              />
            </label>
            <div className="input-field">
              <span className="label">ÁREA DE ESTUDO</span>
              <div className="fake-input">Brusque, SC</div>
            </div>
            <div className="input-field">
              <span className="label">MEDIDA INICIAL</span>
              <div className="segmented segmented-2" role="radiogroup">
                {(["nain", "nach"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={newMeasure === m}
                    onClick={() => setNewMeasure(m)}
                  >
                    {MEASURE_SHORT[m]}
                  </button>
                ))}
              </div>
            </div>
            <button type="button" className="cta cta-block" onClick={() => void create()} disabled={creating}>
              {creating ? "Criando…" : "Criar e abrir o mapa"}
              <span className="cta-arrow" aria-hidden="true">
                →
              </span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
