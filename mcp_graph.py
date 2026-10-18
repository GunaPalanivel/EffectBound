"""Read-only FalkorDB tools for the changeguard_checkout graph.

Stdio speaks one JSON-RPC object per line. No agent framework lives here,
and none of these tools run reconcile, complete, or stop.
"""

from __future__ import annotations

import json
import sys

from falkordb import FalkorDB

GRAPH = "changeguard_checkout"
HOST = "127.0.0.1"
PORT = 6379
EMPTY_GRAPH_ERROR = "Invalid graph operation on empty key"

_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
_HIDDEN = frozenset(("fault_label", "manifest", "required", "sealed"))

_OPERATION = """
MATCH (op:operation {id: $operation_id})
OPTIONAL MATCH (op)-[:HAS_EFFECT]->(e:observed_effect)
RETURN op.visibility, collect(e.id)
"""

_CONTRACT = """
MATCH (op:operation {id: $operation_id})-[:BOUND_TO]->(cv:contract_version)
OPTIONAL MATCH (cv)-[req:REQUIRES]->(:policy)
RETURN cv.id, req.policy_action
ORDER BY cv.id
"""


def _text(value) -> str:
    if isinstance(value, bytes):
        value = value.decode()
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            text = _text(item)
            if text != "":
                return text
    return ""


def _visibility(value) -> str:
    text = _text(value)
    if text == "":
        return "clear"
    return text


def _effect_ids(raw) -> list[str]:
    if isinstance(raw, (str, bytes)) or raw is None:
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    found: list[str] = []
    for item in raw:
        text = _text(item)
        if text != "" and text not in found:
            found.append(text)
    return found


def _public(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key not in _HIDDEN}


def _query(db, cypher: str, operation_id: str) -> list:
    try:
        result = db.select_graph(GRAPH).query(
            cypher, {"operation_id": operation_id}
        )
    except Exception as exc:
        if EMPTY_GRAPH_ERROR in str(exc):
            return []
        raise
    rows = result.result_set
    if not rows:
        return []
    return rows


def read_operation(db, operation_id) -> dict:
    """Return operation_id, visibility, and observed effect ids."""

    rows = _query(db, _OPERATION, operation_id)
    visibility = "clear"
    effect_ids: list[str] = []
    if rows and rows[0]:
        visibility = _visibility(rows[0][0])
        if len(rows[0]) > 1:
            effect_ids = _effect_ids(rows[0][1])
    return _public(
        {
            "operation_id": operation_id,
            "visibility": visibility,
            "effect_ids": effect_ids,
        }
    )


def read_contract_edge(db, operation_id) -> dict:
    """Return the contract version and the REQUIRES policy action."""

    rows = _query(db, _CONTRACT, operation_id)
    picked = None
    for row in rows:
        if not row:
            continue
        action = _text(row[1]) if len(row) > 1 else ""
        if action != "":
            picked = row
            break
        if picked is None:
            picked = row
    if picked is None:
        return _public({"contract_version_id": "", "policy_action": ""})
    return _public(
        {
            "contract_version_id": _text(picked[0]),
            "policy_action": _text(picked[1]) if len(picked) > 1 else "",
        }
    )


def probe(db, operation_id) -> dict:
    """Read the contract edge action. Does not write the graph."""

    edge = read_contract_edge(db, operation_id)
    return _public(
        {
            "visibility": "resolved",
            "policy_action": edge["policy_action"],
        }
    )


def _response(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _failure(msg_id, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }


def _content(payload: dict) -> dict:
    body = _public(payload)
    return {
        "content": [{"type": "text", "text": json.dumps(body)}],
        "structuredContent": body,
        "isError": False,
    }


_TOOL_ORDER = (
    (
        "read_operation",
        "Read visibility and observed effect ids for one operation.",
        read_operation,
    ),
    (
        "read_contract_edge",
        "Read the contract version and the REQUIRES policy action.",
        read_contract_edge,
    ),
    (
        "probe",
        "Read the contract edge action. Does not write the graph.",
        probe,
    ),
)


def _tool_list() -> list[dict]:
    tools = []
    schema = {
        "type": "object",
        "properties": {
            "operation_id": {
                "type": "string",
                "description": "Checkout operation id.",
            }
        },
        "required": ["operation_id"],
    }
    for name, description, _fn in _TOOL_ORDER:
        tools.append(
            {
                "name": name,
                "description": description,
                "inputSchema": schema,
            }
        )
    return tools


def _initialize(message: dict) -> dict:
    params = message.get("params")
    if not isinstance(params, dict):
        params = {}
    requested = params.get("protocolVersion")
    if requested in _VERSIONS:
        version = requested
    else:
        version = _VERSIONS[-1]
    return _response(
        message["id"],
        {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "changeguard_checkout",
                "version": "1.0.0",
            },
        },
    )


def _call(message: dict) -> dict:
    msg_id = message["id"]
    params = message.get("params")
    if not isinstance(params, dict):
        return _failure(msg_id, -32602, "Invalid params")
    name = params.get("name")
    tool = None
    if isinstance(name, str):
        for tool_name, _description, fn in _TOOL_ORDER:
            if tool_name == name:
                tool = fn
                break
    if tool is None:
        shown = name if isinstance(name, str) else ""
        return _failure(msg_id, -32602, f"Unknown tool: {shown}")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return _failure(msg_id, -32602, "Invalid params")
    operation_id = arguments.get("operation_id")
    if not isinstance(operation_id, str):
        return _failure(msg_id, -32602, "operation_id is missing")
    db = message.get("_db")
    if db is None:
        return _failure(msg_id, -32602, "database client is missing")
    try:
        payload = tool(db, operation_id)
    except Exception as exc:
        return _response(
            msg_id,
            {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            },
        )
    return _response(msg_id, _content(payload))


def handle_message(message: dict) -> dict:
    """Answer one MCP JSON-RPC request. message['_db'] is the FalkorDB client."""

    if "id" not in message:
        return {}
    method = message.get("method")
    if not isinstance(method, str):
        return _failure(message.get("id"), -32600, "Invalid Request")
    if method == "initialize":
        return _initialize(message)
    if method == "ping":
        return _response(message["id"], {})
    if method == "tools/list":
        return _response(message["id"], {"tools": _tool_list()})
    if method == "tools/call":
        return _call(message)
    return _failure(message["id"], -32601, "Method not found")


def _write(out, payload: dict) -> None:
    out.write(json.dumps(payload).encode("utf-8") + b"\n")
    out.flush()


def serve_stdio() -> None:
    """Read one JSON object per line. Open FalkorDB and answer on stdout."""

    db = FalkorDB(host=HOST, port=PORT)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    try:
        while True:
            line = stdin.readline()
            if line == b"":
                break
            if not line.strip():
                continue
            try:
                message = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                _write(stdout, _failure(None, -32700, "Parse error"))
                continue
            if not isinstance(message, dict):
                _write(stdout, _failure(None, -32600, "Invalid Request"))
                continue
            if "id" not in message:
                continue
            message["_db"] = db
            _write(stdout, handle_message(message))
    finally:
        db.close()


if __name__ == "__main__":
    serve_stdio()
