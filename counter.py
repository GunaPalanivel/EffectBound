"""Classify service-store effects against a sealed manifest.

No write function, no FalkorDB, and no agent live in this module.
Health and a complete label are not proof of recovery.
"""

from __future__ import annotations

import json
import sqlite3


def classify(store_path, manifest_path, *, health_ok: bool, label: str | None) -> dict:
    """Return duplicate, miss, unknown, or match. health_ok does not change it."""

    connection = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    try:
        stored = connection.execute(
            "SELECT operation_id, effect_id, content FROM effects"
        ).fetchall()
    finally:
        connection.close()

    with open(manifest_path, "r", encoding="utf-8") as manifest_file:
        required = json.load(manifest_file)["required"]

    # A row is the operation id and effect id. Shared content is not a row.
    present = set()
    store_counts = {}
    for operation_id, effect_id, _content in stored:
        present.add((operation_id, effect_id))
        store_counts[operation_id] = store_counts.get(operation_id, 0) + 1

    required_counts = {}
    missing = False
    for item in required:
        operation_id = item["operation_id"]
        effect_id = item["effect_id"]
        required_counts[operation_id] = required_counts.get(operation_id, 0) + 1
        if (operation_id, effect_id) not in present:
            missing = True

    if label == "complete" and missing:
        return {"verdict": "unknown", "recovered": False}

    for operation_id in set(store_counts) | set(required_counts):
        if store_counts.get(operation_id, 0) > required_counts.get(operation_id, 0):
            return {"verdict": "duplicate", "recovered": False}

    if missing:
        return {"verdict": "miss", "recovered": False}
    return {"verdict": "match", "recovered": True}
