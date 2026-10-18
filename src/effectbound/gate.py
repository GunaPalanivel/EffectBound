"""Execute the checkout action from the contract edge.

No agent and no model call. The read is req.policy_action on
changeguard_checkout. A proposal is compared and is not executed.
complete inserts one missing effect. reconcile and stop do not.
The sealed manifest is not opened.
"""

from __future__ import annotations

import os
import sqlite3

from .checkout_service import commit

GRAPH = "changeguard_checkout"

_READ = """
MATCH (:operation {id: $operation_id})-[:BOUND_TO]->(:contract_version)-[req:REQUIRES]->(:policy)
RETURN req.policy_action
"""


def execute(db, store_path, operation_id, effect_id, content, proposal: str) -> dict:
    executed = _edge_action(db, operation_id)
    if (
        executed == "complete"
        and not _effect_stored(store_path, effect_id)
    ):
        commit(store_path, operation_id, effect_id, content)
    return {
        "executed": executed,
        "proposal": proposal,
        "agreed": proposal == executed,
        "store_rows": _store_rows(store_path, operation_id),
    }


def _edge_action(db, operation_id) -> str:
    result = db.select_graph(GRAPH).ro_query(_READ, {"operation_id": operation_id})
    seen = []
    for row in result.result_set or []:
        if not row:
            continue
        value = row[0]
        if isinstance(value, str) and value != "" and value not in seen:
            seen.append(value)
    if len(seen) == 1:
        return seen[0]
    return ""


def _effect_stored(store_path, effect_id) -> bool:
    row = _fetch(
        store_path,
        "SELECT 1 FROM effects WHERE effect_id = ?",
        (effect_id,),
    )
    return row is not None


def _store_rows(store_path, operation_id) -> int:
    row = _fetch(
        store_path,
        "SELECT COUNT(*) FROM effects WHERE operation_id = ?",
        (operation_id,),
    )
    if row is None:
        return 0
    return int(row[0])


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
