import { formatDateTime, formatInt, formatKm, percent } from "../../lib/format";
import type { Manifest } from "../../lib/types";

export function ReleaseInfo({ manifest }: { manifest: Manifest }) {
  const report = manifest.cleaning_report;
  return (
    <section className="panel-section" aria-labelledby="release-title">
      <h2 id="release-title" className="label">
        REDE ANALISADA
      </h2>
      <div className="stats">
        <div>
          <span className="stat-value">{formatInt(report.links_kept)}</span>
          <span className="stat-label">trechos</span>
        </div>
        <div>
          <span className="stat-value">{formatKm(report.length_kept_m)}</span>
          <span className="stat-label">de ruas</span>
        </div>
      </div>
      <dl className="facts">
        <dt>Dados do OSM</dt>
        <dd>{formatDateTime(manifest.osm_base_timestamp)}</dd>
        <dt>Fora da análise</dt>
        <dd>
          {formatKm(report.length_excluded_m)} ({percent(report.length_excluded_m, report.length_total_m)})
          desconectados da malha
        </dd>
        <dt>Metodologia</dt>
        <dd className="mono small">
          v{manifest.methodology_version} · {manifest.filter_version}
        </dd>
      </dl>
    </section>
  );
}
