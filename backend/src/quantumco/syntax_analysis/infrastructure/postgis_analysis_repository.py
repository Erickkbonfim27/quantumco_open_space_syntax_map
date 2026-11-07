"""Adaptador `AnalysisRepository` no PostGIS: grava e publica a análise numa transação só.

Publicar troca só a análise atual DA MESMA CIDADE.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from uuid import uuid4

from psycopg.types.json import Jsonb

from quantumco.platform.postgres import connect
from quantumco.syntax_analysis.application.ports import AnalysisResult

log = logging.getLogger(__name__)


def _clean(key: str, value: float) -> float | int | None:
    if math.isnan(value):
        return None
    return int(value) if key.startswith("c_") else round(float(value), 5)


class PostgisAnalysisRepository:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def save(self, result: AnalysisResult) -> str:
        analysis_id = uuid4()
        created = datetime.fromisoformat(str(result.manifest["created_at"]))
        name = f"analysis-{result.snapshot_name.removeprefix('snapshot-')}-{created:%Y%m%dT%H%M%S}"
        keys = list(result.columns)
        with connect(self._url) as conn, conn.transaction():
            conn.execute(
                "insert into syntax_analysis.analyses "
                "(analysis_id, ibge_code, snapshot_id, name, created_at, manifest) "
                "values (%s, %s, %s, %s, %s, %s)",
                (
                    analysis_id,
                    result.ibge_code,
                    result.snapshot_id,
                    name,
                    created,
                    Jsonb(dict(result.manifest)),
                ),
            )
            log.info("gravando medidas de %d trechos no PostGIS (COPY)…", len(result.link_ids))
            with conn.cursor().copy(
                "copy syntax_analysis.link_measures (analysis_id, link_id, measures) from stdin"
            ) as copy:
                for i, link_id in enumerate(result.link_ids):
                    measures = {k: _clean(k, float(result.columns[k][i])) for k in keys}
                    copy.write_row((analysis_id, link_id, json.dumps(measures)))
            conn.execute(
                "update syntax_analysis.analyses set is_current = false "
                "where is_current and ibge_code = %s",
                (result.ibge_code,),
            )
            conn.execute(
                "update syntax_analysis.analyses set is_current = true where analysis_id = %s",
                (analysis_id,),
            )
        log.info("análise %s publicada no PostGIS", name)
        return f"postgis:syntax_analysis.analyses/{name}"
