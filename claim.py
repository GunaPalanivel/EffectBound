"""Claim one session for a checkout and insert its effect once.

No agent and no model call. The graph is changeguard_checkout.
A different stored session writes nothing. A failed claim does not
call commit. An existing effect row is not inserted again.
"""

from __future__ import annotations

import os
import sqlite3

import checkout_service

GRAPH = "changeguard_checkout"

_READ = """
MATCH (c:claim {id: $claim_id})
RETURN c.session_id
"""

_MERGE = """
MERGE (c:claim {id: $claim_id})
SET c.session_id = $session_id
"""

_CLAIMS = """
MATCH (c:claim {id: $claim_id})
MATCH (op:operation {id: $operation_id})
MERGE (c)-[:CLAIMS]->(op)
"""


def claim(db, *, operation_id, session_id) -> dict:
    claim_id = "claim-" + operation_id
    stored = _stored_session(db, claim_id)
    if stored != "" and stored != session_id:
        return {"claimed": False, "session_id": stored}
    graph = db.select_graph(GRAPH)
    graph.query(
        _MERGE,
        {"claim_id": claim_id, "session_id": session_id},
    )
    graph.query(
        _CLAIMS,
        {"claim_id": claim_id, "operation_id": operation_id},
    )
    return {"claimed": True, "session_id": session_id}


def complete_once(store_path, operation_id, effect_id, content, claimed: bool) -> dict:
    if not claimed:
        return {"inserted": False, "store_rows": _store_rows(store_path, operation_id)}
    if _effect_stored(store_path, operation_id, effect_id):
        return {"inserted": False, "store_rows": _store_rows(store_path, operation_id)}
    try:
        checkout_service.commit(store_path, operation_id, effect_id, content)
    except sqlite3.IntegrityError:
        inserted = False
    else:
        inserted = True
    return {"inserted": inserted, "store_rows": _store_rows(store_path, operation_id)}


def _stored_session(db, claim_id) -> str:
    result = db.select_graph(GRAPH).ro_query(_READ, {"claim_id": claim_id})
    for row in result.result_set or []:
        if row and isinstance(row[0], str) and row[0] != "":
            return row[0]
    return ""


def _store_rows(store_path, operation_id) -> int:
    row = _fetch(
        store_path,
        "SELECT COUNT(*) FROM effects WHERE operation_id = ?",
        (operation_id,),
    )
    if row is None:
        return 0
    return int(row[0])


def _effect_stored(store_path, operation_id, effect_id) -> bool:
    row = _fetch(
        store_path,
        "SELECT 1 FROM effects WHERE operation_id = ? AND effect_id = ?",
        (operation_id, effect_id),
    )
    return row is not None


def _fetch(store_path, sql, params):
    if not os.path.isfile(store_path):
        return None
    connection = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    try:
        found = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'effects'"
        ).fetchone()
        if found is None:
            return None
        return connection.execute(sql, params).fetchone()
    finally:
        connection.close()
