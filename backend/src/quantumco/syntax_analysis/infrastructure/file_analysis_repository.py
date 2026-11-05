from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quantumco.syntax_analysis.application.ports import AnalysisResult


class FileAnalysisRepository:
    """Grava `data/analyses/analysis-<snapshot>/` com measures.parquet + manifest.json."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, result: AnalysisResult) -> str:
        folder = self._root / f"analysis-{result.snapshot_name.removeprefix('snapshot-')}"
        folder.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame({"link_id": list(result.link_ids), **result.columns})
        frame.to_parquet(folder / "measures.parquet", index=False)
        (folder / "manifest.json").write_text(
            json.dumps(dict(result.manifest), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return str(folder)
