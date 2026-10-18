"""Derive evidence state from collected facts.

No agent and no model call. Health is not an argument. There is no
FalkorDB import and no write function. A supplied state is ignored.
Unknown is not safe. First match wins.
"""

from __future__ import annotations


def derive(facts: dict) -> dict:
    """Return state and probe. The caller cannot force AVAILABLE."""

    status = facts.get("collector_status")
    if facts.get("query_failed", False) is True or status == "dead" or status == "error":
        return {"state": "ERROR", "probe": ""}
    if facts.get("walk_result") == "unknown":
        return {"state": "ERROR", "probe": ""}
    if facts.get("walk_result") == "no_path" or _counts_zero(facts):
        return {"state": "EMPTY", "probe": ""}
    visibility = facts.get("visibility", "")
    if (
        visibility == "partial"
        or visibility == "truncated"
        or facts.get("truncated", False) is True
    ):
        return {"state": "PARTIAL", "probe": "visibility"}
    if _contract_differs(facts) or _actions_differ(facts):
        return {"state": "STALE", "probe": ""}
    return {"state": "AVAILABLE", "probe": ""}


def _counts_zero(facts: dict) -> bool:
    """True only when both counts were supplied as the integer 0."""

    if "effect_count" not in facts or "dependency_count" not in facts:
        return False
    return _zero(facts["effect_count"]) and _zero(facts["dependency_count"])


def _zero(value) -> bool:
    # None is not zero. bool is an int subclass, so the type must be int.
    return type(value) is int and value == 0


def _contract_differs(facts: dict) -> bool:
    observed = facts.get("observed_contract_version", "")
    current = facts.get("current_contract_version", "")
    if not isinstance(observed, str) or not isinstance(current, str):
        return False
    if observed == "" or current == "":
        return False
    return observed != current


def _actions_differ(facts: dict) -> bool:
    actions = facts.get("policy_actions", [])
    if not isinstance(actions, list):
        return False
    seen = set()
    for action in actions:
        if isinstance(action, str) and action != "":
            seen.add(action)
            if len(seen) >= 2:
                return True
    return False
