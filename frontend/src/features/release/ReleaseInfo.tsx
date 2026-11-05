import { formatDateTime, formatInt, formatKm, percent } from "../../lib/format";
import type { AnalysisManifest, Manifest } from "../../lib/types";

interface ReleaseInfoProps {
  manifest: Manifest;
  analysis: AnalysisManifest | null;
}

export function ReleaseInfo({ manifest, analysis }: ReleaseInfoProps) {
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
          <span className="stat-label">de ruas (com o entorno)</span>
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
        {analysis && (
          <>
            <dt>Motor</dt>
            <dd>
              {analysis.engine} {analysis.engine_version}
              {analysis.preliminary && (
                <span className="pill-warn" title="Validação contra o depthmapX pendente; classes por percentil da extensão viária de Brusque.">
                  preliminar
                </span>
              )}
            </dd>
          </>
        )}
      </dl>
    </section>
  );
}
