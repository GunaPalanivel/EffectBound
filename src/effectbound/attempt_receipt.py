"""Separate the committed effect from the attempt receipt.

No FalkorDB, no counter, and no model call. The effects table
belongs to checkout_service. resume does not insert a row.
"""

from __future__ import annotations

import json
import os
import sqlite3

from . import checkout_service


def commit_and_stop(store_path, receipt_path, operation_id, effect_id, content) -> dict:
    try:
        checkout_service.commit(store_path, operation_id, effect_id, content)
    except sqlite3.IntegrityError:
        committed = False
    else:
        committed = True
    return {
        "committed": committed,
        "receipt_written": False,
        "store_rows": _store_rows(store_path, operation_id),
    }


def resume(store_path, receipt_path, operation_id, effect_id, content) -> dict:
    if not _effect_stored(store_path, operation_id, effect_id):
        return {"inserted": False, "store_rows": 0, "receipt_written": False}
    _ensure_receipt(receipt_path, operation_id, effect_id)
    return {
        "inserted": False,
        "store_rows": _store_rows(store_path, operation_id),
        "receipt_written": True,
    }


def _store_rows(store_path, operation_id) -> int:
    row = _fetch(
        store_path,
        "SELECT COUNT(*) FROM effects WHERE operation_id = ?",
        (operation_id,),
    )
    if row is None:
        return 0
    return int(row[0])


def _effect_stored(store_path, operation_id, effect_id) -> bool:
    row = _fetch(
        store_path,
        "SELECT 1 FROM effects WHERE operation_id = ? AND effect_id = ?",
        (operation_id, effect_id),
    )
    return row is not None


def _fetch(store_path, sql, params):
    if not os.path.isfile(store_path):
        return None
    connection = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    try:
        found = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'effects'"
        ).fetchone()
        if found is None:
            return None
        return connection.execute(sql, params).fetchone()
    finally:
        connection.close()


def _ensure_receipt(receipt_path, operation_id, effect_id) -> None:
    kind, records = _read_receipt(receipt_path)
    if _has_operation(records, operation_id):
        return
    record = {
        "operation_id": operation_id,
        "effect_id": effect_id,
        "resumed": True,
    }
    if kind == "missing":
        _write_list(receipt_path, [record])
        return
    if kind == "list":
        records.append(record)
        _write_list(receipt_path, records)
        return
    _append_line(receipt_path, record)


def _has_operation(records, operation_id) -> bool:
    for item in records:
        if isinstance(item, dict) and item.get("operation_id") == operation_id:
            return True
    return False


def _read_receipt(receipt_path):
    if not os.path.isfile(receipt_path):
        return "missing", []
    with open(receipt_path, "r", encoding="utf-8") as handle:
        text = handle.read()
    if text.strip() == "":
        return "lines", []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return "list", parsed
    if isinstance(parsed, dict):
        return "lines", [parsed]
    records = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "":
            continue
        records.append(json.loads(stripped))
    return "lines", records


def _write_list(receipt_path, records) -> None:
    with open(receipt_path, "w", encoding="utf-8") as handle:
        json.dump(records, handle)
        handle.write("\n")


def _append_line(receipt_path, record) -> None:
    separator = ""
    if os.path.getsize(receipt_path) > 0:
        with open(receipt_path, "rb") as handle:
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                separator = "\n"
    with open(receipt_path, "a", encoding="utf-8") as handle:
        handle.write(separator + json.dumps(record) + "\n")
