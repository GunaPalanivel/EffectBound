"""Commit a checkout effect into sqlite.

No agent and no model call. The row is inserted and committed before
the HTTP handler can close the socket. A dropped response sends no
status line and no body. Health stays available on the same process.
"""

from __future__ import annotations

import json
import socket
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

_SCHEMA = """
CREATE TABLE IF NOT EXISTS effects (
  operation_id TEXT NOT NULL,
  effect_id TEXT NOT NULL,
  content TEXT NOT NULL,
  PRIMARY KEY (operation_id, effect_id)
)
"""


def init_store(path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def commit(path, operation_id, effect_id, content) -> None:
    init_store(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO effects (operation_id, effect_id, content) "
            "VALUES (?, ?, ?)",
            (operation_id, effect_id, content),
        )
        conn.commit()
    finally:
        conn.close()


def _send_json(handler, status, payload) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


class _CheckoutHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/health":
            self.send_error(404)
            return
        _send_json(self, 200, {"status": "ok"})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/checkout":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            self.send_error(400)
            return
        if length < 0:
            self.send_error(400)
            return
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400)
            return
        if not isinstance(body, dict):
            self.send_error(400)
            return
        operation_id = body.get("operation_id")
        effect_id = body.get("effect_id")
        content = body.get("content")
        drop_response = body.get("drop_response")
        if (
            not isinstance(operation_id, str)
            or not isinstance(effect_id, str)
            or not isinstance(content, str)
            or not isinstance(drop_response, bool)
        ):
            self.send_error(400)
            return
        try:
            commit(self.server.store_path, operation_id, effect_id, content)
        except sqlite3.IntegrityError:
            self.send_error(409)
            return
        if drop_response:
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            return
        _send_json(self, 200, {"committed": True})

    def do_PUT(self) -> None:
        self.send_error(404)

    do_DELETE = do_PUT
    do_PATCH = do_PUT
    do_HEAD = do_PUT


def serve(store_path, http_host="127.0.0.1", http_port=8766) -> None:
    init_store(store_path)
    server = HTTPServer((http_host, http_port), _CheckoutHandler)
    server.store_path = store_path
    server.serve_forever()
