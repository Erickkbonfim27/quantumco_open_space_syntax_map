from __future__ import annotations

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


def length_weighted_percentile(values: FloatArray, lengths: FloatArray) -> FloatArray:
    """Percentil (0–1) de cada valor, ponderado pela extensão (Q27).

    O percentil de um segmento é a fração da extensão total com valor estritamente menor,
    mais metade da extensão com valor igual (ponto médio). NaN fica NaN e não pesa.
    """
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(lengths, dtype=np.float64)
    out = np.full(v.shape, np.nan)
    ok = ~np.isnan(v) & (w > 0)
    if not ok.any():
        return out
    vv, ww = v[ok], w[ok]
    order = np.argsort(vv, kind="mergesort")
    sorted_v, sorted_w = vv[order], ww[order]
    cumulative = np.cumsum(sorted_w)
    total = cumulative[-1]
    # para empates, usa o bloco inteiro de valores iguais
    first = np.searchsorted(sorted_v, sorted_v, side="left")
    last = np.searchsorted(sorted_v, sorted_v, side="right") - 1
    below = np.where(first > 0, cumulative[first - 1], 0.0)
    equal = cumulative[last] - below
    ranked = np.empty_like(vv)
    ranked[order] = (below + equal / 2.0) / total
    out[ok] = ranked
    return out


def classify(percentiles: FloatArray, classes: int) -> npt.NDArray[np.float64]:
    """Classe 0..classes-1 a partir do percentil. NaN continua NaN."""
    p = np.asarray(percentiles, dtype=np.float64)
    out = np.floor(np.clip(p, 0.0, 1.0) * classes)
    out = np.minimum(out, classes - 1)
    out[np.isnan(p)] = np.nan
    return out


def class_cutoffs(values: FloatArray, lengths: FloatArray, classes: int) -> FloatArray:
    """Limites (classes-1 valores) dos quantis ponderados por extensão.

    Usado nos cenários: o cenário é classificado pelos cortes da BASE, para que uma rua que
    passa a ficar acima do corte do topo da cidade atual "suba de classe" (Q23).
    """
    v = np.asarray(values, dtype=np.float64)
    w = np.asarray(lengths, dtype=np.float64)
    ok = ~np.isnan(v) & (w > 0)
    order = np.argsort(v[ok], kind="mergesort")
    sorted_v, sorted_w = v[ok][order], w[ok][order]
    cumulative = np.cumsum(sorted_w) / sorted_w.sum()
    targets = np.arange(1, classes) / classes
    idx = np.minimum(np.searchsorted(cumulative, targets, side="left"), len(sorted_v) - 1)
    return sorted_v[idx]


def classify_by_cutoffs(values: FloatArray, cutoffs: FloatArray) -> FloatArray:
    v = np.asarray(values, dtype=np.float64)
    out = np.searchsorted(cutoffs, v, side="right").astype(np.float64)
    out[np.isnan(v)] = np.nan
    return out
