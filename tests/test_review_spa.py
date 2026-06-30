"""Tests that the review server serves the SPA assets (DESIGN.md §4.2)."""

from __future__ import annotations

from pathlib import Path

from blurscan.actions.review.server import ReviewState, create_app
from blurscan.models import ScanConfig


def _client(tmp_path: Path):
    state = ReviewState([], ScanConfig(scan_path=tmp_path))
    return create_app(state).test_client()


def test_index_is_the_spa(tmp_path: Path) -> None:
    html = _client(tmp_path).get("/").data
    assert b"/static/app.js" in html
    assert b"/static/styles.css" in html
    assert b'id="grid"' in html  # gallery mount point


def test_static_assets_served(tmp_path: Path) -> None:
    client = _client(tmp_path)
    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert b"/api/results" in js.data  # the SPA talks to the API
    assert b"X-Blurscan-Token" in js.data  # and sends the CSRF token

    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert b".grid" in css.data


def test_static_traversal_blocked(tmp_path: Path) -> None:
    # send_from_directory must not allow escaping the static dir.
    resp = _client(tmp_path).get("/static/..%2f..%2fserver.py")
    assert resp.status_code == 404
