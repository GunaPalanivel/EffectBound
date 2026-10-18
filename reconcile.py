"""Choose a checkout action from received facts.

No FalkorDB, no counter, and no model call. The graph edge, the
fault label, and the expected verdict are not read. complete inserts
one missing effect. reconcile and stop do not.
"""

from __future__ import annotations

import sqlite3

import checkout_service
from contracts import ACTIONS


def choose(facts: dict) -> dict:
    collector_status = facts.get("collector_status")
    dependency_present = facts.get("dependency_present")
    action = facts.get("authorized_action")
    if (
        collector_status == "dead"
        or collector_status == "error"
        or dependency_present is not True
        or action not in ACTIONS
    ):
        return {"action": "", "inserted": False}
    inserted = False
    if action == "complete" and facts.get("effect_stored") is not True:
        try:
            checkout_service.commit(
                facts["store_path"],
                facts["operation_id"],
                facts["effect_id"],
                facts["content"],
            )
        except sqlite3.IntegrityError:
            inserted = False
        else:
            inserted = True
    return {"action": action, "inserted": inserted}
