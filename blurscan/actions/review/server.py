"""Local Flask review server and API.

See DESIGN.md §4. Serves a small JSON API + static UI for triaging flagged images.
Runs only on loopback and never trusts client-supplied paths.

Security controls:
- **Loopback only:** ``serve`` binds ``127.0.0.1`` on an ephemeral port.
- **No path traversal:** images are addressed by opaque ids that map server-side
  to the exact paths produced by the scan; clients never supply filesystem paths.
- **CSRF/Origin:** state-changing endpoints require a per-run token header and
  reject cross-origin requests, so a random web page can't drive the local server.
"""

from __future__ import annotations

import secrets
import threading
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from blurscan.actions.quarantine import quarantine
from blurscan.actions.review.heatmap import heatmap_jpeg
from blurscan.actions.review.store import DecisionStore
from blurscan.actions.tag import ExiftoolNotFound, tag
from blurscan.cache import default_cache_path
from blurscan.models import ImageResult, ScanConfig
from blurscan.thumbs import thumbnail_bytes

KEEP, QUARANTINE, TAG = "keep", "quarantine", "tag"
VALID_DECISIONS = frozenset({KEEP, QUARANTINE, TAG})
_STATIC_DIR = Path(__file__).with_name("static")
_THUMB_EDGE = 256
_PREVIEW_EDGE = 1400


class ReviewState:
    """Server-side state: the id->result map, staged decisions, and the token."""

    def __init__(
        self, results: list[ImageResult], cfg: ScanConfig, store: DecisionStore | None = None
    ) -> None:
        self.cfg = cfg
        self.items: dict[str, ImageResult] = {str(i): r for i, r in enumerate(results)}
        self.store = store
        self.token = secrets.token_urlsafe(24)
        self._shutdown = threading.Event()
        # Restore any previously staged decisions (resumable session).
        persisted = store.load() if store is not None else {}
        self.decisions: dict[str, str] = {
            item_id: persisted[str(r.path)]
            for item_id, r in self.items.items()
            if str(r.path) in persisted
        }

    def get(self, item_id: str) -> ImageResult | None:
        return self.items.get(item_id)

    def set_decision(self, item_id: str, decision: str) -> None:
        self.decisions[item_id] = decision
        if self.store is not None:
            self.store.set(str(self.items[item_id].path), decision)

    def request_shutdown(self) -> None:
        self._shutdown.set()

    @property
    def shutdown_event(self) -> threading.Event:
        return self._shutdown


def _item_json(item_id: str, r: ImageResult, decision: str | None) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": r.path.name,
        "path": str(r.path),
        "classification": r.classification,
        "method": r.method,
        "score": r.score_max_tile,
        "score_global": r.score_global,
        "fft_ratio": r.fft_ratio,
        "error": r.error,
        "decision": decision or KEEP,
    }


def create_app(state: ReviewState) -> Flask:
    """Build the Flask app for ``state`` (testable via ``app.test_client()``)."""
    app = Flask(__name__, static_folder=None)

    def _authorized() -> bool:
        token = request.headers.get("X-Blurscan-Token", "")
        if not token or not secrets.compare_digest(token, state.token):
            return False
        # Reject cross-origin POSTs (defense in depth beyond the token).
        origin = request.headers.get("Origin")
        if origin is not None and not origin.startswith(("http://127.0.0.1", "http://localhost")):
            return False
        return True

    @app.get("/")
    def index() -> Response:
        return send_from_directory(_STATIC_DIR, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name: str) -> Response:
        return send_from_directory(_STATIC_DIR, name)

    @app.get("/api/results")
    def results() -> Response:
        items = [_item_json(i, r, state.decisions.get(i)) for i, r in state.items.items()]
        return jsonify({"token": state.token, "dry_run": state.cfg.dry_run, "items": items})

    @app.get("/api/thumb/<item_id>")
    def thumb(item_id: str) -> Response:
        return _serve_image(state, item_id, _THUMB_EDGE)

    @app.get("/api/image/<item_id>")
    def image(item_id: str) -> Response:
        return _serve_image(state, item_id, _PREVIEW_EDGE)

    @app.get("/api/heatmap/<item_id>")
    def heatmap(item_id: str) -> Response:
        result = state.get(item_id)
        if result is None or result.error is not None:
            return _err("not found", 404)
        try:
            data = heatmap_jpeg(result, state.cfg)
        except Exception:  # noqa: BLE001 - render failure -> 404, never 500
            return _err("not renderable", 404)
        if data is None:
            return _err("no heatmap for this method", 404)
        return Response(data, mimetype="image/jpeg")

    @app.post("/api/decision")
    def decision() -> Response:
        if not _authorized():
            return _err("unauthorized", 403)
        body = request.get_json(silent=True) or {}
        item_id, value = body.get("id"), body.get("decision")
        if item_id not in state.items:
            return _err("unknown id", 404)
        if value not in VALID_DECISIONS:
            return _err("invalid decision", 400)
        state.set_decision(item_id, value)
        return jsonify({"ok": True})

    @app.post("/api/apply")
    def apply() -> Response:
        if not _authorized():
            return _err("unauthorized", 403)
        return jsonify(_apply_decisions(state))

    @app.post("/api/shutdown")
    def shutdown() -> Response:
        if not _authorized():
            return _err("unauthorized", 403)
        state.request_shutdown()
        return jsonify({"ok": True})

    return app


def _serve_image(state: ReviewState, item_id: str, edge: int) -> Response:
    result = state.get(item_id)
    if result is None or result.error is not None:
        return _err("not found", 404)
    try:
        data = thumbnail_bytes(result.path, max_edge=edge)
    except Exception:  # noqa: BLE001 - missing/unreadable file -> 404, never 500
        return _err("not renderable", 404)
    return Response(data, mimetype="image/jpeg")


def _apply_decisions(state: ReviewState) -> dict[str, Any]:
    to_quarantine = [state.items[i] for i, d in state.decisions.items() if d == QUARANTINE]
    to_tag = [state.items[i] for i, d in state.decisions.items() if d == TAG]
    summary: dict[str, Any] = {"dry_run": state.cfg.dry_run, "quarantined": 0, "tagged": 0}

    if to_quarantine:
        dest = state.cfg.scan_path / "_blurscan_quarantine"
        # The user explicitly staged each of these, so honor the decision as-is
        # rather than re-applying the classification filter (which would silently
        # drop borderline/sharp/errored selections).
        actions = quarantine(
            to_quarantine, dest, move=False, dry_run=state.cfg.dry_run, filter_results=False
        )
        summary["quarantined"] = len(actions)
    if to_tag:
        try:
            cmds = tag(to_tag, dry_run=state.cfg.dry_run)
            summary["tagged"] = sum(len(c.targets) for c in cmds)
        except ExiftoolNotFound as exc:
            summary["tag_error"] = str(exc)
    return summary


def _err(message: str, code: int) -> Response:
    response = jsonify({"error": message})
    response.status_code = code
    return response


def serve(
    results: list[ImageResult],
    cfg: ScanConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> str:
    """Start the review server on loopback and block until shutdown. Returns the URL."""
    import webbrowser

    from werkzeug.serving import make_server

    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("review server only binds loopback (127.0.0.1)")

    store = DecisionStore(default_cache_path(cfg.scan_path)) if cfg.use_cache else None
    state = ReviewState(results, cfg, store=store)
    app = create_app(state)
    server = make_server(host, port, app)
    url = f"http://{host}:{server.server_port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"blurscan review UI: {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        state.shutdown_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return url
