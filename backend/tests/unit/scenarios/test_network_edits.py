from __future__ import annotations

import pytest

from quantumco.bootstrap.scenario_runs import to_analysis_edits
from quantumco.scenarios.domain.network_edits import EditKind, NetworkEdit, check_edits
from quantumco.scenarios.domain.workspace import InvalidWorkspaceError
from quantumco.syntax_analysis.domain.edits import AddStreet, RemoveLink

LINE = ((-48.92, -27.10), (-48.915, -27.095))


def test_kinds_need_the_right_fields() -> None:
    NetworkEdit(EditKind.REMOVE, link_id="12")
    NetworkEdit(EditKind.ADD, coords=LINE)
    NetworkEdit(EditKind.REROUTE, link_id="12", coords=LINE)
    with pytest.raises(InvalidWorkspaceError, match="Escolha a via"):
        NetworkEdit(EditKind.CLOSE)
    with pytest.raises(InvalidWorkspaceError, match="2 pontos"):
        NetworkEdit(EditKind.ADD, coords=(LINE[0],))
    with pytest.raises(InvalidWorkspaceError, match="não leva traçado"):
        NetworkEdit(EditKind.REMOVE, link_id="1", coords=LINE)
    with pytest.raises(InvalidWorkspaceError, match="Brusque"):
        NetworkEdit(EditKind.ADD, coords=((-50.0, -27.1), (-48.9, -27.1)))


def test_json_round_trip_and_unknown_type() -> None:
    edit = NetworkEdit(EditKind.REROUTE, link_id="7", coords=LINE, label="  ponte   nova ")
    data = edit.to_json()
    assert data == {"type": "reroute", "link_id": "7", "coords": [list(c) for c in LINE],
                    "label": "ponte nova"}  # fmt: skip
    assert NetworkEdit.from_json(data) == edit
    with pytest.raises(InvalidWorkspaceError, match="desconhecido"):
        NetworkEdit.from_json({"type": "explodir"})


def test_one_change_per_existing_link() -> None:
    with pytest.raises(InvalidWorkspaceError, match="já tem uma alteração"):
        check_edits(
            [NetworkEdit(EditKind.REMOVE, link_id="3"), NetworkEdit(EditKind.CLOSE, link_id="3")]
        )
    check_edits([NetworkEdit(EditKind.ADD, coords=LINE), NetworkEdit(EditKind.ADD, coords=LINE)])


def test_translation_to_the_analysis() -> None:
    edits = to_analysis_edits(
        [
            NetworkEdit(EditKind.REMOVE, link_id="1"),
            NetworkEdit(EditKind.CLOSE, link_id="2"),
            NetworkEdit(EditKind.REROUTE, link_id="3", coords=LINE),
            NetworkEdit(EditKind.ADD, coords=LINE),
        ]
    )
    assert edits[:3] == [RemoveLink("1"), RemoveLink("2", closed=True), RemoveLink("3")]
    assert isinstance(edits[3], AddStreet)
    assert isinstance(edits[4], AddStreet)
    x, y = edits[3].coords[0]
    assert 690_000 < x < 720_000
    assert 6_990_000 < y < 7_010_000
