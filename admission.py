"""Admit or refuse the current contract edge.

No agent and no model call. The read is req.policy_action on
changeguard_checkout. The person does not supply the action.
Refuse writes nothing. run calls execute only when the approval
still matches that edge. The sealed manifest is not opened.
"""

from __future__ import annotations

GRAPH = "changeguard_checkout"

_READ = """
MATCH (op:operation {id: $operation_id})-[:BOUND_TO]->(cv:contract_version)-[req:REQUIRES]->(:policy)
RETURN req.policy_action, cv.id, op.tenant_id
"""

_APPROVAL = """
MATCH (approval:approval {id: $approval_id})
RETURN approval.operator_id, approval.tenant_id, approval.action,
       approval.effect_id, approval.evidence_state, approval.contract_version_id
"""

_MERGE = """
MERGE (approval:approval {id: $approval_id})
SET approval.operator_id = $operator_id,
    approval.tenant_id = $tenant_id,
    approval.action = $action,
    approval.effect_id = $effect_id,
    approval.evidence_state = $evidence_state,
    approval.contract_version_id = $contract_version_id,
    approval.operation_id = $operation_id
MERGE (attempt:attempt {id: $attempt_id})
MERGE (attempt)-[:AUTHORIZED_BY]->(approval)
MERGE (attempt)-[:OF]->(op)
"""


def admit(db, *, operation_id, effect_id, operator_id, tenant_id, choice, evidence) -> dict:
    from evidence import derive

    edge = _edge(db, operation_id)
    derived = derive(evidence)
    state = derived["state"]
    probe = derived["probe"]
    if _tenant_differs(edge["tenants"], tenant_id):
        return _refused(state, probe)
    if choice == "refuse":
        return _refused(state, probe)
    if state != "AVAILABLE":
        return _refused(state, probe)
    if choice == "admit" and edge["action"] != "" and edge["contract_version_id"] != "":
        approval_id = "approval-" + operation_id
        _write(
            db,
            claim_tenant=not edge["tenants"],
            operation_id=operation_id,
            approval_id=approval_id,
            attempt_id="attempt-" + operation_id,
            operator_id=operator_id,
            tenant_id=tenant_id,
            action=edge["action"],
            effect_id=effect_id,
            evidence_state=state,
            contract_version_id=edge["contract_version_id"],
        )
        return {
            "admitted": True,
            "action": edge["action"],
            "approval_id": approval_id,
            "state": "AVAILABLE",
            "probe": "",
            "wrote_store": False,
        }
    return _refused(state, probe)


def run(
    db,
    store_path,
    *,
    operation_id,
    effect_id,
    content,
    operator_id,
    tenant_id,
    evidence,
) -> dict:
    from evidence import derive

    edge = _edge(db, operation_id)
    derived = derive(evidence)
    state = derived["state"]
    probe = derived["probe"]
    approval = _approval(db, "approval-" + operation_id)
    if _matches(approval, operator_id, tenant_id, effect_id, edge, state):
        from gate import execute

        result = execute(
            db,
            store_path,
            operation_id,
            effect_id,
            content,
            approval["action"],
        )
        return {
            "executed": result["executed"],
            "proposal": result["proposal"],
            "agreed": result["agreed"],
            "store_rows": result["store_rows"],
            "admitted": True,
            "state": state,
            "probe": probe,
        }
    return {
        "executed": "",
        "admitted": False,
        "wrote": False,
        "state": state,
        "probe": probe,
    }


def _edge(db, operation_id) -> dict:
    result = db.select_graph(GRAPH).ro_query(_READ, {"operation_id": operation_id})
    actions = []
    versions = []
    tenants = []
    for row in result.result_set or []:
        if not row:
            continue
        action = row[0]
        version = row[1]
        tenant = row[2]
        if isinstance(action, str) and action != "":
            if action not in actions:
                actions.append(action)
            if isinstance(version, str) and version != "" and version not in versions:
                versions.append(version)
        if isinstance(tenant, str) and tenant != "" and tenant not in tenants:
            tenants.append(tenant)
    return {
        "action": actions[0] if len(actions) == 1 else "",
        "contract_version_id": versions[0] if len(versions) == 1 else "",
        "tenants": tenants,
    }


def _tenant_differs(tenants, tenant_id) -> bool:
    if not tenants:
        return False
    return tenants != [tenant_id]


def _write(db, *, claim_tenant, **params) -> None:
    cypher = "MATCH (op:operation {id: $operation_id})\n" + _MERGE
    if claim_tenant:
        cypher += "SET op.tenant_id = $tenant_id\n"
    db.select_graph(GRAPH).query(cypher, params)


def _approval(db, approval_id):
    result = db.select_graph(GRAPH).ro_query(
        _APPROVAL, {"approval_id": approval_id}
    )
    rows = [row for row in (result.result_set or []) if row]
    if len(rows) != 1:
        return None
    row = rows[0]
    return {
        "operator_id": row[0],
        "tenant_id": row[1],
        "action": row[2],
        "effect_id": row[3],
        "evidence_state": row[4],
        "contract_version_id": row[5],
    }


def _matches(approval, operator_id, tenant_id, effect_id, edge, state) -> bool:
    if approval is None:
        return False
    action = edge["action"]
    version = edge["contract_version_id"]
    return (
        approval["operator_id"] == operator_id
        and approval["tenant_id"] == tenant_id
        and action != ""
        and approval["action"] == action
        and version != ""
        and approval["contract_version_id"] == version
        and approval["effect_id"] == effect_id
        and state == "AVAILABLE"
        and approval["evidence_state"] == state
    )


def _refused(state, probe) -> dict:
    return {
        "admitted": False,
        "action": "",
        "approval_id": "",
        "state": state,
        "probe": probe,
        "wrote_store": False,
    }
