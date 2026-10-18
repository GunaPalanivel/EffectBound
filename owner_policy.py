"""Update an owner and expire an open approval.

No agent and no model call. The graph is changeguard_checkout.
A missing operation or approval still writes the owner. Outcome
nodes are not removed.
"""

from __future__ import annotations

GRAPH = "changeguard_checkout"

_OWNER = """
MERGE (owner:owner {id: $owner_id})
SET owner.source = $source, owner.effective = $effective
"""

_OWNS = """
MATCH (owner:owner {id: $owner_id})
MATCH (op:operation {id: $operation_id})
MERGE (owner)-[:OWNS]->(op)
"""

_EXPIRE = """
MATCH (approval:approval {id: $approval_id})
SET approval.evidence_state = "expired"
"""

_STATE = """
MATCH (approval:approval {id: $approval_id})
RETURN approval.evidence_state
"""

_OUTCOME = """
MATCH (outcome:outcome {id: $outcome_id})
RETURN outcome.id
"""


def update(db, *, operation_id, owner_id, source, effective, block: bool) -> dict:
    graph = db.select_graph(GRAPH)
    graph.query(
        _OWNER,
        {"owner_id": owner_id, "source": source, "effective": effective},
    )
    graph.query(
        _OWNS,
        {"owner_id": owner_id, "operation_id": operation_id},
    )
    if block:
        graph.query(_EXPIRE, {"approval_id": "approval-" + operation_id})
    return {
        "owner_id": owner_id,
        "expired": expired(db, operation_id) if block else False,
        "outcome_deleted": False,
    }


def expired(db, operation_id) -> bool:
    result = db.select_graph(GRAPH).ro_query(
        _STATE,
        {"approval_id": "approval-" + operation_id},
    )
    for row in result.result_set or []:
        if row and isinstance(row[0], str) and row[0] == "expired":
            return True
    return False


def outcome_remains(db, operation_id) -> bool:
    result = db.select_graph(GRAPH).ro_query(
        _OUTCOME,
        {"outcome_id": "outcome-" + operation_id},
    )
    for row in result.result_set or []:
        if row:
            return True
    return False
