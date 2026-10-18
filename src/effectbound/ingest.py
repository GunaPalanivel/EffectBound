"""Idempotent checkout ingest into FalkorDB.

No agent and no model call live in this module.
"""

from __future__ import annotations

from falkordb import FalkorDB

GRAPH = "changeguard_checkout"
EMPTY_GRAPH_ERROR = "Invalid graph operation on empty key"


def open_db(host="127.0.0.1", port=6379):
    return FalkorDB(host=host, port=port)


def reset_graph(db):
    graph = db.select_graph(GRAPH)
    try:
        reply = graph.delete()
    except Exception as exc:
        text = str(exc)
        if EMPTY_GRAPH_ERROR in text:
            return text
        raise
    return str(reply)


def effect_count(db, operation_id):
    result = db.select_graph(GRAPH).query(
        "MATCH (:operation {id: $operation_id})-[:HAS_EFFECT]->(e:observed_effect) "
        "RETURN count(e)",
        {"operation_id": operation_id},
    )
    rows = result.result_set
    if not rows or rows[0][0] is None:
        return 0
    return int(rows[0][0])


def ingest_effect(db, event):
    graph = db.select_graph(GRAPH)
    operation_id = event["operation_id"]
    graph.query(
        "MERGE (op:operation {id: $operation_id}) "
        "SET op.collector_status = $collector_status",
        {
            "operation_id": operation_id,
            "collector_status": event.get("collector_status"),
        },
    )
    _merge_contract(graph, operation_id, event)
    _merge_dependencies(graph, operation_id, event.get("dependencies") or [])

    effect_id = event.get("effect_id")
    if effect_id is None or effect_id == "":
        return {"effect_count": 0, "nodes_created": 0}

    effect = graph.query(
        "MATCH (op:operation {id: $operation_id}) "
        "MERGE (e:observed_effect {id: $effect_id}) "
        "SET e.effect_status = $effect_status, e.ack = $ack "
        "MERGE (op)-[:HAS_EFFECT]->(e)",
        {
            "operation_id": operation_id,
            "effect_id": effect_id,
            "effect_status": event.get("effect_status"),
            "ack": event.get("ack"),
        },
    )
    return {
        "effect_count": effect_count(db, operation_id),
        "nodes_created": int(effect.nodes_created),
    }


def _merge_contract(graph, operation_id, event):
    contract_version_id = event.get("contract_version_id")
    if contract_version_id is None or contract_version_id == "":
        return
    policy_id = event.get("policy_id")
    params = {
        "operation_id": operation_id,
        "contract_version_id": contract_version_id,
        "policy_id": policy_id,
        "policy_action": event.get("policy_action"),
    }
    if policy_id is None or policy_id == "":
        graph.query(
            "MATCH (op:operation {id: $operation_id}) "
            "MERGE (cv:contract_version {id: $contract_version_id}) "
            "MERGE (op)-[:BOUND_TO]->(cv)",
            params,
        )
        return
    graph.query(
        "MATCH (op:operation {id: $operation_id}) "
        "MERGE (cv:contract_version {id: $contract_version_id}) "
        "MERGE (op)-[:BOUND_TO]->(cv) "
        "MERGE (pol:policy {id: $policy_id}) "
        "SET pol.policy_action = $policy_action "
        "MERGE (cv)-[req:REQUIRES]->(pol) "
        "SET req.policy_action = $policy_action",
        params,
    )


def _merge_dependencies(graph, operation_id, dependencies):
    for dep in dependencies:
        graph.query(
            "MATCH (op:operation {id: $operation_id}) "
            "MERGE (src:dependency {id: $from_id}) "
            "MERGE (dst:dependency {id: $to_id}) "
            "MERGE (src)-[:DEPENDS_ON]->(dst) "
            "MERGE (op)-[:DEPENDS_ON]->(src) "
            "MERGE (op)-[:DEPENDS_ON]->(dst)",
            {
                "operation_id": operation_id,
                "from_id": dep["from_id"],
                "to_id": dep["to_id"],
            },
        )
