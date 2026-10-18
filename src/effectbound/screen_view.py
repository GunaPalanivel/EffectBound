"""Show the live checkout screen.

No agent and no model call. The graph is changeguard_checkout.
The Cypher on screen is the contract-edge read. A redis connection
failure is a halt. Health is not evidence and does not change
recovered. This module does not write the store or insert a row.
"""

from __future__ import annotations

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from .counter import classify
from .evidence import derive
from .memory import recall
from .owner_policy import expired
from .proposer import propose

GRAPH = "changeguard_checkout"

EDGE_CYPHER = """
MATCH (:operation {id: $operation_id})-[:BOUND_TO]->(:contract_version)-[req:REQUIRES]->(:policy)
RETURN req.policy_action
"""

_CONTRACT = """
MATCH (op:operation {id: $operation_id})-[:BOUND_TO]->(cv:contract_version)-[req:REQUIRES]->(pol:policy)
RETURN cv.id, req.policy_action, pol.id
"""

_STATUS = """
MATCH (op:operation {id: $operation_id})
RETURN op.collector_status, op.tenant_id
"""

_EFFECT_COUNT = """
MATCH (:operation {id: $operation_id})-[:HAS_EFFECT]->(e:observed_effect)
RETURN count(e)
"""

_EFFECT_IDS = """
MATCH (:operation {id: $operation_id})-[:HAS_EFFECT]->(effect:observed_effect)
RETURN effect.id
"""

_DEPENDENCY_COUNT = """
MATCH (:operation {id: $operation_id})-[:DEPENDS_ON]->(dep:dependency)
RETURN count(dep)
"""

_DEPENDENCY_IDS = """
MATCH (:operation {id: $operation_id})-[:DEPENDS_ON]->(dep:dependency)
RETURN dep.id
"""

# Same connection failures as the action read. The screen halts.
_QUERY_ERRORS = (RedisConnectionError, RedisTimeoutError, TimeoutError, OSError)
EMPTY_GRAPH_ERROR = "Invalid graph operation on empty key"


def view(db, *, operation_id, store_path, manifest_path, health_ok: bool) -> dict:
    """Return the live screen, or a halt when a query cannot reach redis."""

    try:
        loaded = _load(db, operation_id)
    except _QUERY_ERRORS:
        return {"status": "halt", "action": ""}
    counter = classify(
        store_path,
        manifest_path,
        health_ok=health_ok,
        label=None,
    )
    return {
        "status": "live",
        "label": "TESTBED LIVE",
        "cypher": EDGE_CYPHER,
        "contract_version_id": loaded["contract_version_id"],
        "edge_action": loaded["edge_action"],
        "proposal": loaded["proposal"],
        "model_called": loaded["model_called"],
        "evidence_state": loaded["evidence_state"],
        "evidence_probe": loaded["evidence_probe"],
        "counter": counter,
        "recovered": counter["recovered"],
        "health_ok": health_ok,
        "on_path": loaded["on_path"],
        "dim": loaded["dim"],
        "outcome": loaded["outcome"],
        "owner_expired": loaded["owner_expired"],
    }


def _load(db, operation_id) -> dict:
    contract = _contract(_rows(db, _CONTRACT, operation_id))
    collector_status, tenant = _status(_rows(db, _STATUS, operation_id))
    effect_count = _counted(_rows(db, _EFFECT_COUNT, operation_id))
    effect_ids = _column(_rows(db, _EFFECT_IDS, operation_id))
    dependency_count = _counted(_rows(db, _DEPENDENCY_COUNT, operation_id))
    dependency_ids = _column(_rows(db, _DEPENDENCY_IDS, operation_id))
    derived = derive(
        _facts(
            effect_count,
            dependency_count,
            collector_status,
            contract["actions"],
            contract["versions"],
        )
    )
    proposal, model_called = _proposal(db, operation_id)
    if tenant == "":
        outcome = _no_outcome()
    else:
        outcome = _recall(
            db,
            operation_id,
            tenant,
            contract["contract_version_id"],
        )
    return {
        "contract_version_id": contract["contract_version_id"],
        "edge_action": contract["edge_action"],
        "proposal": proposal,
        "model_called": model_called,
        "evidence_state": derived["state"],
        "evidence_probe": derived["probe"],
        "on_path": _keep(
            [
                operation_id,
                contract["contract_version_id"],
                contract["policy_id"],
                *effect_ids,
            ]
        ),
        "dim": _keep(dependency_ids),
        "outcome": outcome,
        "owner_expired": _owner_expired(db, operation_id),
    }


def _recall(db, operation_id, tenant_id, contract_version_id) -> dict:
    try:
        return recall(
            db,
            operation_id=operation_id,
            tenant_id=tenant_id,
            contract_version_id=contract_version_id,
        )
    except _QUERY_ERRORS:
        raise
    except Exception as exc:
        if EMPTY_GRAPH_ERROR in str(exc):
            return _no_outcome()
        raise


def _owner_expired(db, operation_id) -> bool:
    try:
        return expired(db, operation_id)
    except _QUERY_ERRORS:
        raise
    except Exception as exc:
        if EMPTY_GRAPH_ERROR in str(exc):
            return False
        raise


def _proposal(db, operation_id) -> tuple[str, bool]:
    try:
        proposed = propose(db, operation_id)
    except _QUERY_ERRORS:
        raise
    except Exception:
        return "", False
    return proposed["proposal"], proposed["model_called"]


def _facts(
    effect_count,
    dependency_count,
    collector_status,
    actions,
    versions,
) -> dict:
    # Two distinct actions stay in the list so derive can mark them stale.
    facts = {
        "effect_count": effect_count,
        "dependency_count": dependency_count,
        "collector_status": collector_status,
        "policy_actions": actions,
    }
    if len(versions) == 1:
        facts["observed_contract_version"] = versions[0]
        facts["current_contract_version"] = versions[0]
    return facts


def _contract(rows) -> dict:
    actions = []
    versions = []
    policies = []
    for row in rows:
        if not row:
            continue
        version = _text(row[0]) if len(row) > 0 else ""
        action = _text(row[1]) if len(row) > 1 else ""
        policy = _text(row[2]) if len(row) > 2 else ""
        if action != "" and action not in actions:
            actions.append(action)
        if version != "" and version not in versions:
            versions.append(version)
        if policy != "" and policy not in policies:
            policies.append(policy)
    return {
        "edge_action": actions[0] if len(actions) == 1 else "",
        "contract_version_id": versions[0] if len(versions) == 1 else "",
        "policy_id": policies[0] if len(policies) == 1 else "",
        "actions": actions,
        "versions": versions,
    }


def _status(rows) -> tuple[str, str]:
    for row in rows:
        if not row:
            continue
        collector = _text(row[0]) if len(row) > 0 else ""
        tenant = _text(row[1]) if len(row) > 1 else ""
        return collector, tenant
    return "", ""


def _column(rows) -> list[str]:
    found = []
    for row in rows:
        if not row:
            continue
        text = _text(row[0])
        if text != "" and text not in found:
            found.append(text)
    return found


def _counted(rows) -> int:
    if not rows or not rows[0] or rows[0][0] is None:
        return 0
    return int(rows[0][0])


def _rows(db, cypher, operation_id):
    try:
        result = db.select_graph(GRAPH).ro_query(
            cypher, {"operation_id": operation_id}
        )
    except _QUERY_ERRORS:
        raise
    except Exception as exc:
        if EMPTY_GRAPH_ERROR in str(exc):
            return []
        raise
    return result.result_set or []


def _keep(values) -> list[str]:
    found = []
    for value in values:
        if isinstance(value, str) and value != "" and value not in found:
            found.append(value)
    return found


def _text(value) -> str:
    if isinstance(value, bytes):
        value = value.decode()
    if isinstance(value, str):
        return value
    return ""


def _no_outcome() -> dict:
    return {
        "visible": False,
        "action": "",
        "contract_version_id": "",
        "authorized": False,
    }
