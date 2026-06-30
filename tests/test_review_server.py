"""Tests for the review server API (DESIGN.md §4)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from flask.testing import FlaskClient
from numpy.typing import NDArray
from PIL import Image

from blurscan.actions.review.server import ReviewState, create_app, serve
from blurscan.models import BLURRY, BORDERLINE, SHARP, ImageResult, ScanConfig


def _img(path: Path) -> Path:
    arr: NDArray[np.uint8] = np.random.default_rng(0).integers(
        0, 256, (32, 32, 3), dtype=np.uint8
    )
    Image.fromarray(arr, "RGB").save(path)
    return path


def _state(tmp_path: Path) -> ReviewState:
    a = _img(tmp_path / "blur.png")
    results = [
        ImageResult(a, 32, 32, 5.0, 2.0, 0.1, BLURRY),
        ImageResult(tmp_path / "missing.png", 0, 0, 0.0, 0.0, 0.0, BLURRY, error="gone"),
        ImageResult(_img(tmp_path / "sharp.png"), 32, 32, 900.0, 400.0, 0.5, SHARP),
    ]
    return ReviewState(results, ScanConfig(scan_path=tmp_path, dry_run=True))


@pytest.fixture
def client_and_state(tmp_path: Path) -> tuple[FlaskClient, ReviewState]:
    state = _state(tmp_path)
    return create_app(state).test_client(), state


def _decide(
    client: FlaskClient, state: ReviewState, item_id: str, value: str, **kw: object
) -> int:
    headers = {"X-Blurscan-Token": state.token}
    headers.update(kw.pop("headers", {}))  # type: ignore[arg-type]
    body = {"id": item_id, "decision": value}
    return client.post("/api/decision", json=body, headers=headers).status_code


def test_results_lists_items_and_token(client_and_state: tuple[FlaskClient, ReviewState]) -> None:
    client, state = client_and_state
    data = client.get("/api/results").get_json()
    assert data["token"] == state.token
    assert len(data["items"]) == 3
    assert data["dry_run"] is True


def test_index_served(client_and_state: tuple[FlaskClient, ReviewState]) -> None:
    client, _ = client_and_state
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"blurscan review" in resp.data


def test_thumb_ok_and_unknown(client_and_state: tuple[FlaskClient, ReviewState]) -> None:
    client, _ = client_and_state
    assert client.get("/api/thumb/0").status_code == 200
    assert client.get("/api/thumb/999").status_code == 404  # unknown id, no traversal
    assert client.get("/api/thumb/1").status_code == 404  # errored item not renderable


def test_decision_requires_token(client_and_state: tuple[FlaskClient, ReviewState]) -> None:
    client, state = client_and_state
    no_token = client.post("/api/decision", json={"id": "0", "decision": "keep"})
    assert no_token.status_code == 403
    assert _decide(client, state, "0", "quarantine") == 200
    assert state.decisions["0"] == "quarantine"


def test_decision_validation(client_and_state: tuple[FlaskClient, ReviewState]) -> None:
    client, state = client_and_state
    assert _decide(client, state, "999", "keep") == 404  # unknown id
    assert _decide(client, state, "0", "bogus") == 400  # invalid decision


def test_cross_origin_rejected(client_and_state: tuple[FlaskClient, ReviewState]) -> None:
    client, state = client_and_state
    status = _decide(client, state, "0", "keep", headers={"Origin": "http://evil.example"})
    assert status == 403


def test_apply_dry_run(client_and_state: tuple[FlaskClient, ReviewState]) -> None:
    client, state = client_and_state
    hdr = {"X-Blurscan-Token": state.token}
    _decide(client, state, "0", "quarantine")
    summary = client.post("/api/apply", headers=hdr).get_json()
    assert summary["dry_run"] is True
    assert summary["quarantined"] == 1
    # dry-run created nothing
    assert not (state.cfg.scan_path / "_blurscan_quarantine").exists()


def test_apply_quarantines_explicit_borderline(tmp_path: Path) -> None:
    # A borderline image the user explicitly stages for quarantine must be acted
    # on — the apply path must not re-apply the blurry-only classification filter.
    border = _img(tmp_path / "border.png")
    state = ReviewState(
        [ImageResult(border, 32, 32, 120.0, 60.0, 0.3, BORDERLINE)],
        ScanConfig(scan_path=tmp_path),  # not dry-run: actually copies
    )
    client = create_app(state).test_client()
    hdr = {"X-Blurscan-Token": state.token}
    assert _decide(client, state, "0", "quarantine") == 200
    summary = client.post("/api/apply", headers=hdr).get_json()
    assert summary["quarantined"] == 1
    assert (tmp_path / "_blurscan_quarantine" / "border.png").exists()


def test_shutdown_sets_event(client_and_state: tuple[FlaskClient, ReviewState]) -> None:
    client, state = client_and_state
    hdr = {"X-Blurscan-Token": state.token}
    assert client.post("/api/shutdown", headers=hdr).status_code == 200
    assert state.shutdown_event.is_set()


def test_serve_rejects_non_loopback(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        serve([], ScanConfig(scan_path=tmp_path), host="0.0.0.0")
