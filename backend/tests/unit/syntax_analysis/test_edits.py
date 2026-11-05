from __future__ import annotations

import numpy as np
import pytest

from quantumco.syntax_analysis.domain.edits import (
    AddStreet,
    InvalidEditError,
    RemoveLink,
    apply_edits,
)
from quantumco.syntax_analysis.domain.percentiles import class_cutoffs, classify_by_cutoffs
from quantumco.syntax_analysis.domain.segmentation import Link

A = Link("a", ((0.0, 0.0), (100.0, 0.0)), True)
B = Link("b", ((100.0, 0.0), (100.0, 100.0)), True)
C = Link("c", ((0.0, 50.0), (0.0, 150.0)), True)


def test_remove_requires_existing_link() -> None:
    edited = apply_edits([A, B], [RemoveLink("a")])
    assert [link.link_id for link in edited.links] == ["b"]
    with pytest.raises(InvalidEditError, match="não existe"):
        apply_edits([A, B], [RemoveLink("zzz")])


def test_new_street_snaps_to_endpoint_and_splits_midblock() -> None:
    # da ponta (100,100) de B até o meio de C (0,100), com pontas um pouco fora
    edited = apply_edits([A, B, C], [AddStreet(((103.0, 102.0), (4.0, 100.0)))])
    new = next(link for link in edited.links if link.link_id == "novo:0")
    assert new.coords[0] == (100.0, 100.0)  # encaixou na ponta de B
    assert new.coords[-1] == (0.0, 100.0)  # encaixou no meio de C…
    ids = {link.link_id for link in edited.links}
    assert {"c/a", "c/b"} <= ids  # …que foi dividido em dois
    assert "c" not in ids
    assert edited.report_id("c/a") == "c"
    assert edited.added == ["novo:0"]


def test_snap_too_far_is_rejected() -> None:
    with pytest.raises(InvalidEditError, match="máximo"):
        apply_edits([A], [AddStreet(((500.0, 500.0), (100.0, 0.0)))], snap_tolerance_m=30)


def test_cutoffs_split_extent_evenly_and_classify_new_values() -> None:
    values = np.arange(1.0, 101.0)
    lengths = np.ones(100)
    cutoffs = class_cutoffs(values, lengths, 4)
    assert cutoffs.tolist() == [25.0, 50.0, 75.0]
    got = classify_by_cutoffs(np.array([1.0, 30.0, 80.0, 1000.0, np.nan]), cutoffs)
    assert got[:4].tolist() == [0.0, 1.0, 3.0, 3.0]
    assert np.isnan(got[4])
