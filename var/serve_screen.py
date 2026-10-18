"""Start the screen for the Phase 7 browser cases. Not a product module."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from checkout_service import commit, init_store
from checkout_service import serve as health_serve
from ingest import ingest_effect, open_db, reset_graph
from screen_http import serve

ROOT = Path(__file__).resolve().parents[1]
VAR = ROOT / "var"
STORE = VAR / "screen.sqlite"
MANIFEST = VAR / "screen-manifest.json"
OPERATION = "screen-op"
EFFECT = "screen-effect"


def _ready() -> None:
    last = None
    for _ in range(40):
        try:
            db = open_db()
            try:
                db.select_graph("changeguard_checkout").query("RETURN 1")
            except Exception as exc:
                if "Invalid graph operation on empty key" not in str(exc):
                    raise
            db.close()
            return
        except Exception as exc:
            last = exc
            time.sleep(0.5)
    raise SystemExit(f"falkordb not ready: {last}")


def _plant() -> None:
    db = open_db()
    reset_graph(db)
    ingest_effect(
        db,
        {
            "operation_id": OPERATION,
            "effect_id": EFFECT,
            "effect_status": "committed",
            "ack": "lost",
            "contract_version_id": "cv-screen-op",
            "policy_id": "policy-screen-op",
            "policy_action": "reconcile",
            "dependencies": [
                {"from_id": "screen-op-api", "to_id": "screen-op-pay"}
            ],
            "collector_status": "available",
        },
    )
    db.select_graph("changeguard_checkout").query(
        "MATCH (op:operation {id: $operation_id}) SET op.tenant_id = $tenant_id",
        {"operation_id": OPERATION, "tenant_id": "tenant-a"},
    )
    db.close()
    if STORE.exists():
        STORE.unlink()
    init_store(str(STORE))
    commit(str(STORE), OPERATION, EFFECT, "charged")
    MANIFEST.write_text(
        json.dumps(
            {"required": [{"operation_id": OPERATION, "effect_id": EFFECT}]}
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    _ready()
    _plant()
    thread = threading.Thread(
        target=health_serve,
        args=(str(STORE), "127.0.0.1", 8766),
        daemon=True,
    )
    thread.start()
    serve(str(STORE), str(MANIFEST))


if __name__ == "__main__":
    main()
