"""Read the checkout action from FalkorDB.

No agent and no model call. Every call opens a new connection to
changeguard_checkout. The action string is the REQUIRES property
policy_action. A connection failure returns a refusal.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlsplit

from falkordb import FalkorDB
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

GRAPH = "changeguard_checkout"

_READ = """
MATCH (op:operation {id: $operation_id})
OPTIONAL MATCH (op)-[:HAS_EFFECT]->(effect:observed_effect)
WITH op, count(effect) AS effect_count
OPTIONAL MATCH (op)-[:DEPENDS_ON]->(dep:dependency)
WITH op, effect_count, count(dep) AS dep_count
OPTIONAL MATCH (op)-[:BOUND_TO]->(:contract_version)-[req:REQUIRES]->(:policy)
RETURN op.collector_status, effect_count, dep_count,
       collect(DISTINCT req.policy_action)
"""

_CONNECTION_ERRORS = (RedisConnectionError, RedisTimeoutError, TimeoutError, OSError)


def _policy_action(values) -> str:
    if isinstance(values, str):
        return values
    if isinstance(values, list):
        for value in values:
            if isinstance(value, str):
                return value
    return ""


def _from_row(collector_status, effect_count, dep_count, policy_actions) -> dict:
    if (
        not isinstance(effect_count, int)
        or effect_count < 1
        or not isinstance(dep_count, int)
        or dep_count < 1
        or collector_status == "dead"
    ):
        return {"status": "unavailable", "action": ""}
    return {"status": "available", "action": _policy_action(policy_actions)}


def read_action(operation_id, host="127.0.0.1", port=6379) -> dict:
    try:
        with FalkorDB(host=host, port=port) as db:
            result = db.select_graph(GRAPH).query(
                _READ, {"operation_id": operation_id}
            )
    except _CONNECTION_ERRORS:
        return {"status": "refused", "action": ""}
    rows = result.result_set
    if not rows:
        return {"status": "unavailable", "action": ""}
    return _from_row(*rows[0])


def _operation_id(path: str) -> str | None:
    parts = urlsplit(path).path.split("/")
    if len(parts) != 3 or parts[0] != "" or parts[1] != "action" or parts[2] == "":
        return None
    return unquote(parts[2])


class _ActionHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        operation_id = _operation_id(self.path)
        if operation_id is None:
            self.send_error(404)
            return
        body = read_action(
            operation_id,
            host=self.server.db_host,
            port=self.server.db_port,
        )
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
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
    http_host="127.0.0.1",
    http_port=8765,
    db_host="127.0.0.1",
    db_port=6379,
) -> None:
    server = HTTPServer((http_host, http_port), _ActionHandler)
    server.db_host = db_host
    server.db_port = db_port
    server.serve_forever()
