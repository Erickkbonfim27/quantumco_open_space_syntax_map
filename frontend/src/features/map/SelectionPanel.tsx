import { formatMeters } from "../../lib/format";
import type { Measure, RadiusKey } from "../../lib/types";
import { groupFor } from "./highwayGroups";
import type { Selection } from "./MapView";
import { MEASURE_LABEL, RADII, SYNTAX_PALETTE } from "./syntaxPalette";

interface SelectionPanelProps {
  selection: Selection | null;
  measure: Measure;
  radius: RadiusKey;
  onClose: () => void;
}

const number = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

export function SelectionPanel({ selection, measure, radius, onClose }: SelectionPanelProps) {
  if (!selection) {
    return (
      <section className="panel-section">
        <div className="hint">Clique num trecho de rua para ver os detalhes.</div>
      </section>
    );
  }
  const { properties: link, lngLat } = selection;
  const [lng, lat] = lngLat;
  const other: Measure = measure === "nain" ? "nach" : "nain";
  const value = link[`${measure}_${radius}`];
  const otherValue = link[`${other}_${radius}`];
  const cls = link[`c_${measure}_${radius}`];
  const radiusLabel = RADII.find((r) => r.key === radius)?.label ?? radius;
  const noteUrl = `https://www.openstreetmap.org/note/new#map=19/${lat.toFixed(6)}/${lng.toFixed(6)}`;

  return (
    <section className="panel-section" aria-labelledby="selection-title">
      <div className="card">
        <div className="card-head">
          <span id="selection-title" className="mono card-title">
            TRECHO #{link.link_id}
          </span>
          <button type="button" className="close" onClick={onClose} aria-label="Fechar">
            ×
          </button>
        </div>
        {typeof value === "number" && (
          <div className="metric">
            <div>
              <span className="metric-label">
                {MEASURE_LABEL[measure]} · R {radiusLabel}
              </span>
              <span className="metric-value">{number.format(value)}</span>
            </div>
            {typeof cls === "number" && (
              <span
                className="metric-dot"
                style={{ background: SYNTAX_PALETTE[cls] }}
                title={`classe ${cls + 1} de ${SYNTAX_PALETTE.length}`}
              />
            )}
          </div>
        )}
        <dl className="facts">
          {typeof otherValue === "number" && (
            <>
              <dt>{MEASURE_LABEL[other]}</dt>
              <dd>{number.format(otherValue)}</dd>
            </>
          )}
          <dt>Hierarquia</dt>
          <dd>
            {groupFor(link.highway)?.label ?? "–"} <code>{link.highway}</code>
          </dd>
          <dt>Comprimento</dt>
          <dd>{formatMeters(link.length_m)}</dd>
          <dt>Zona</dt>
          <dd>{link.zone === "result" ? "Brusque" : "Entorno (só cálculo)"}</dd>
          {(link.is_bridge || link.is_tunnel) && (
            <>
              <dt>Estrutura</dt>
              <dd>{link.is_bridge ? "Ponte" : "Túnel"}</dd>
            </>
          )}
          <dt>Via no OSM</dt>
          <dd>
            <a href={`https://www.openstreetmap.org/way/${link.osm_way_id}`} target="_blank" rel="noreferrer">
              way/{link.osm_way_id}
            </a>
          </dd>
        </dl>
        <a className="button-ghost" href={noteUrl} target="_blank" rel="noreferrer">
          Reportar erro na rede →
        </a>
      </div>
    </section>
  );
}
