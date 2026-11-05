"""Medidas normalizadas de Hillier, Yang & Turner (2012), calculadas por código próprio.

Entradas no padrão do depthmapX:
- `node_count` (NC) inclui o segmento de origem;
- `total_depth` (TD) é a profundidade angular total, com 90° = 1;
- `choice` é a escolha angular bruta.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


def nain(node_count: FloatArray, total_depth: FloatArray) -> FloatArray:
    """NAIN = NC^1.2 / TD. Indefinido (NaN) quando TD ≤ 0 (segmento isolado no raio)."""
    nc = np.asarray(node_count, dtype=np.float64)
    td = np.asarray(total_depth, dtype=np.float64)
    out = np.full(nc.shape, np.nan)
    ok = td > 0
    out[ok] = np.power(nc[ok], 1.2) / td[ok]
    return out


def nach(choice: FloatArray, total_depth: FloatArray) -> FloatArray:
    """NACH = log(CH + 1) / log(TD + 3)."""
    ch = np.asarray(choice, dtype=np.float64)
    td = np.asarray(total_depth, dtype=np.float64)
    out = np.full(ch.shape, np.nan)
    ok = td >= 0
    out[ok] = np.log(ch[ok] + 1.0) / np.log(td[ok] + 3.0)
    return out
