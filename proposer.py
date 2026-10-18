"""Propose the checkout action from the contract edge.

No model call. Does not write a store, write a manifest, or execute
an action.
"""

from __future__ import annotations

# Frozen call budget. One proposal reads the graph at most this many times.
MAX_TURNS = 4


def propose(db, operation_id) -> dict:
    """Return the contract-edge policy_action. Probe only when visibility is partial."""

    from mcp_graph import probe, read_contract_edge, read_operation

    tools = []
    operation = _read(tools, "read_operation", read_operation, db, operation_id)
    probe_called = False
    if operation["visibility"] == "partial":
        _read(tools, "probe", probe, db, operation_id)
        probe_called = True
    edge = _read(tools, "read_contract_edge", read_contract_edge, db, operation_id)
    return {
        "proposal": edge["policy_action"],
        "turns": len(tools),
        "probe_called": probe_called,
        "model_called": False,
        "tools": tools,
    }


def _read(tools, name, fn, db, operation_id):
    if len(tools) >= MAX_TURNS:
        raise ValueError("graph reads stop at 4")
    tools.append(name)
    return fn(db, operation_id)
