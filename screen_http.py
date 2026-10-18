"""Serve the checkout screen.

No agent and no model call. GET /screen returns HTML for one
operation. A FalkorDB connection failure is a halt page. Health is
read separately and does not choose the action.
"""

from __future__ import annotations

import json
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from ingest import open_db
from screen_page import render
from screen_view import view

_CONNECTION_ERRORS = (RedisConnectionError, RedisTimeoutError, TimeoutError, OSError)


def _operation_id(path: str) -> str | None:
    split = urlsplit(path)
    if split.path != "/screen":
        return None
    values = parse_qs(split.query).get("operation_id")
    if not values or values[0] == "":
        return None
    return values[0]


def _health_ok(url: str) -> bool:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    return payload == {"status": "ok"}


def _html(server, operation_id: str) -> str:
    health_ok = _health_ok(server.health_url)
    try:
        db = open_db(server.db_host, server.db_port)
    except _CONNECTION_ERRORS:
        return render({"status": "halt", "action": ""})
    try:
        document = view(
            db,
            operation_id=operation_id,
            store_path=server.store_path,
            manifest_path=server.manifest_path,
            health_ok=health_ok,
        )
    except _CONNECTION_ERRORS:
        document = {"status": "halt", "action": ""}
    finally:
        try:
            db.close()
        except _CONNECTION_ERRORS:
            pass
    return render(document)


class _ScreenHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        operation_id = _operation_id(self.path)
        if operation_id is None:
            self.send_error(404)
            return
        encoded = _html(self.server, operation_id).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        self.send_error(404)

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST
    do_HEAD = do_POST


def serve(
    store_path,
    manifest_path,
    *,
    host="127.0.0.1",
    port=8767,
    db_host="127.0.0.1",
    db_port=6379,
    health_url="http://127.0.0.1:8766/health",
) -> None:
    server = HTTPServer((host, port), _ScreenHandler)
    server.store_path = store_path
    server.manifest_path = manifest_path
    server.db_host = db_host
    server.db_port = db_port
    server.health_url = health_url
    server.serve_forever()
