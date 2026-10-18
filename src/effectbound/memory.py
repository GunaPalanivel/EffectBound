"""Record and recall a measured checkout outcome.

No agent and no model call. The write is query and the read is
ro_query on changeguard_checkout. The graph is the record. A
missing operation is not created. A different contract version
stays visible and is not authorized.
"""

from __future__ import annotations

GRAPH = "changeguard_checkout"

_RECORD = """
MERGE (outcome:outcome {id: $outcome_id})
SET outcome.operation_id = $operation_id,
    outcome.effect_id = $effect_id,
    outcome.action = $action,
    outcome.contract_version_id = $contract_version_id,
    outcome.tenant_id = $tenant_id,
    outcome.recovered = BOOLEAN
MERGE (attempt:attempt {id: $attempt_id})
MERGE (attempt)-[:YIELDED]->(outcome)
"""

_LINK = """
MATCH (op:operation {id: $operation_id})
MATCH (attempt:attempt {id: $attempt_id})
MERGE (attempt)-[:OF]->(op)
"""

_RECALL = """
MATCH (outcome:outcome {id: $outcome_id})
RETURN outcome.action, outcome.contract_version_id, outcome.tenant_id,
       outcome.recovered
"""


def record(db, *, operation_id, effect_id, action, contract_version_id, tenant_id, recovered: bool) -> dict:
    outcome_id = "outcome-" + operation_id
    attempt_id = "attempt-" + operation_id
    graph = db.select_graph(GRAPH)
    # Client stringifies True as True. Cypher booleans are true and false.
    stored = "true" if recovered is True else "false"
    graph.query(
        _RECORD.replace("BOOLEAN", stored),
        {
            "outcome_id": outcome_id,
            "operation_id": operation_id,
            "effect_id": effect_id,
            "action": action,
            "contract_version_id": contract_version_id,
            "tenant_id": tenant_id,
            "attempt_id": attempt_id,
        },
    )
    graph.query(
        _LINK,
        {"operation_id": operation_id, "attempt_id": attempt_id},
    )
    return {
        "outcome_id": outcome_id,
        "action": action,
        "contract_version_id": contract_version_id,
        "visible": True,
    }


def recall(db, *, operation_id, tenant_id, contract_version_id) -> dict:
    result = db.select_graph(GRAPH).ro_query(
        _RECALL, {"outcome_id": "outcome-" + operation_id}
    )
    rows = [row for row in (result.result_set or []) if row]
    if len(rows) != 1:
        return _hidden()
    action, version, tenant, recovered = rows[0]
    if tenant != tenant_id:
        return _hidden()
    return {
        "visible": True,
        "action": action if isinstance(action, str) else "",
        "contract_version_id": version if isinstance(version, str) else "",
        "authorized": version == contract_version_id and recovered is True,
    }


def _hidden() -> dict:
    return {
        "visible": False,
        "action": "",
        "contract_version_id": "",
        "authorized": False,
    }
