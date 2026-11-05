import { useState } from "react";

import { QuantumcoIcon } from "./brand/QuantumcoIcon";
import { Footer } from "./components/Footer";
import { AnalysisPanel } from "./features/map/AnalysisPanel";
import { MapView, type Selection } from "./features/map/MapView";
import { ScenarioPanel } from "./features/map/ScenarioPanel";
import { SelectionPanel } from "./features/map/SelectionPanel";
import { ReleaseInfo } from "./features/release/ReleaseInfo";
import { useSnapshotData } from "./features/release/useSnapshotData";
import type { Measure, RadiusKey } from "./lib/types";

export function App() {
  const state = useSnapshotData();
  const [selection, setSelection] = useState<Selection | null>(null);
  const [measure, setMeasure] = useState<Measure>("nain");
  const [radius, setRadius] = useState<RadiusKey>("n");

  return (
    <div className="app">
      <main className="map-area">
        {state.status === "ready" && (
          <MapView
            data={state.data}
            measure={measure}
            radius={radius}
            selectedId={selection?.properties.link_id ?? null}
            onSelect={setSelection}
          />
        )}
      </main>

      <aside className="panel" aria-label="Painel do mapa sintático">
        <header className="panel-section brand">
          <div className="brand-row">
            <QuantumcoIcon size={34} />
            <span className="wordmark">QUANTUMCO</span>
            <span className="city">Brusque</span>
          </div>
          <p>Mapa sintático aberto, construído sobre o OpenStreetMap.</p>
        </header>

        {state.status === "loading" && (
          <section className="panel-section" aria-live="polite">
            <div className="hint">Carregando a rede…</div>
          </section>
        )}
        {state.status === "error" && (
          <section className="panel-section" role="alert">
            <div className="card card-error">
              <span className="label">ERRO AO CARREGAR</span>
              <p>{state.message}</p>
              <p className="muted">
                Confira se a API está no ar (<code>uv run quantumco serve</code>). Sem snapshot, rode
                o cold start: <code>uv run quantumco snapshot build</code>.
              </p>
            </div>
          </section>
        )}
        {state.status === "ready" && (
          <>
            {state.data.scenario && (
              <ScenarioPanel scenario={state.data.scenario} measure={measure} radius={radius} />
            )}
            <AnalysisPanel
              analysis={state.data.analysis}
              measure={measure}
              radius={radius}
              onMeasure={setMeasure}
              onRadius={setRadius}
            />
            <SelectionPanel
              selection={selection}
              measure={measure}
              radius={radius}
              onClose={() => setSelection(null)}
            />
            <ReleaseInfo manifest={state.data.manifest} />
          </>
        )}

        <Footer />
      </aside>
    </div>
  );
}
