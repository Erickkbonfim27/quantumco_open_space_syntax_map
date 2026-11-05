from __future__ import annotations

import httpx
import pytest

from quantumco.road_network.infrastructure.overpass_source import OverpassError, OverpassWaySource


def source_with(statuses: list[int], waits: list[float]) -> OverpassWaySource:
    responses = iter(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(responses)
        return httpx.Response(status, json={"elements": []} if status == 200 else None)

    return OverpassWaySource(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=4,
        initial_backoff_s=1.0,
        sleep=waits.append,
    )


def test_retries_with_exponential_backoff_then_succeeds() -> None:
    waits: list[float] = []
    payload = source_with([502, 429, 200], waits)._query("way(1);out;")
    assert payload == {"elements": []}
    assert waits == [1.0, 2.0]


def test_gives_up_after_max_attempts() -> None:
    waits: list[float] = []
    with pytest.raises(OverpassError, match="504"):
        source_with([504, 504, 504, 504], waits)._query("way(1);out;")
    assert waits == [1.0, 2.0, 4.0]


def test_does_not_retry_client_errors() -> None:
    waits: list[float] = []
    with pytest.raises(OverpassError, match="400"):
        source_with([400], waits)._query("way(1);out;")
    assert waits == []
