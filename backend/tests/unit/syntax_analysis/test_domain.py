from __future__ import annotations

import math

import numpy as np
import pytest

from quantumco.syntax_analysis.domain.measures import nach, nain
from quantumco.syntax_analysis.domain.percentiles import classify, length_weighted_percentile
from quantumco.syntax_analysis.domain.radius import Radius
from quantumco.syntax_analysis.domain.segmentation import Link, explode


def test_nain_and_nach_follow_hillier_yang_turner() -> None:
    nc = np.array([10.0, 4.0])
    td = np.array([5.0, 0.0])
    ch = np.array([3.0, 0.0])
    got = nain(nc, td)
    assert got[0] == pytest.approx(10**1.2 / 5)
    assert math.isnan(got[1])  # TD = 0: indefinido
    assert nach(ch, td)[0] == pytest.approx(math.log(4) / math.log(8))
    assert nach(ch, td)[1] == pytest.approx(0.0)


def test_length_weighted_percentile_uses_extent_not_count() -> None:
    # um trecho longo de valor baixo pesa mais que muitos curtos de valor alto
    values = np.array([1.0, 2.0, 3.0, np.nan])
    lengths = np.array([800.0, 100.0, 100.0, 50.0])
    p = length_weighted_percentile(values, lengths)
    assert p[0] == pytest.approx(0.4)  # metade dos seus 80%
    assert p[1] == pytest.approx(0.85)
    assert p[2] == pytest.approx(0.95)
    assert math.isnan(p[3])


def test_ties_share_the_same_percentile() -> None:
    p = length_weighted_percentile(np.array([5.0, 5.0]), np.array([1.0, 3.0]))
    assert p[0] == p[1] == pytest.approx(0.5)


def test_equal_extent_per_class() -> None:
    rng = np.random.default_rng(7)
    values = rng.random(7000)
    lengths = rng.uniform(10, 200, 7000)
    classes = classify(length_weighted_percentile(values, lengths), 7)
    extent = [lengths[classes == k].sum() for k in range(7)]
    assert max(extent) / min(extent) < 1.1


def test_classify_bounds() -> None:
    got = classify(np.array([0.0, 0.5, 1.0, np.nan]), 7)
    assert got[:3].tolist() == [0.0, 3.0, 6.0]
    assert math.isnan(got[3])


def test_explode_keeps_endpoints_and_drops_noise() -> None:
    zigzag = Link("a", ((0.0, 0.0), (50.0, 0.5), (100.0, 0.0), (100.0, 100.0)), in_result_zone=True)
    pieces = explode([zigzag], tolerance_m=2.0)
    # o desvio de 0,5 m some; a curva de 90° fica
    assert [(p.start, p.end) for p in pieces] == [
        ((0.0, 0.0), (100.0, 0.0)),
        ((100.0, 0.0), (100.0, 100.0)),
    ]
    assert sum(p.length_m for p in pieces) == pytest.approx(200.0)
    assert {p.link_id for p in pieces} == {"a"}


def test_radius_keys() -> None:
    assert Radius(800).key == "800"
    assert Radius(None).key == "n"
    assert Radius(None).distance_m(100_000) == 100_000
    with pytest.raises(ValueError, match="positivo"):
        Radius(0)
