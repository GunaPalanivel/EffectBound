"""Render the checkout screen as one HTML document.

A halt document is one heading. The live document shows the query, the
edge, the evidence, and the counter boolean. Health is a separate line.
"""

from __future__ import annotations

import html


def render(doc: dict) -> str:
    """Return one complete HTML document."""

    if doc.get("status") == "halt":
        parts = ["<h1>halt</h1>"]
        if doc.get("action") == "":
            parts.append("<p>" + html.escape(doc["action"], quote=True) + "</p>")
        inner = "\n".join(parts)
        return (
            "<!DOCTYPE html>\n"
            "<html>\n"
            '<head><meta charset="utf-8"><title>halt</title></head>\n'
            "<body>\n" + inner + "\n</body>\n</html>\n"
        )

    quote = True
    cypher = html.escape(str(doc["cypher"]), quote=quote)
    edge_action = html.escape(str(doc["edge_action"]), quote=quote)
    version = html.escape(str(doc["contract_version_id"]), quote=quote)
    proposal = html.escape(str(doc["proposal"]), quote=quote)
    evidence = html.escape(str(doc["evidence_state"]), quote=quote)
    verdict = html.escape(str(doc["counter"]["verdict"]), quote=quote)
    recovered = "true" if doc["recovered"] is True else "false"
    health = "ok" if doc["health_ok"] is True else "down"
    parts = [
        "<h1>TESTBED LIVE</h1>",
        "<p>" + cypher + "</p>",
        "<p>REQUIRES " + edge_action + "</p>",
        "<p>" + version + "</p>",
        "<p>proposal " + proposal + "</p>",
        "<p>evidence " + evidence + "</p>",
        "<p>counter " + verdict + "</p>",
        "<p>recovered " + recovered + "</p>",
        "<p>health " + health + "</p>",
    ]
    for node_id in doc["on_path"]:
        parts.append("<p>" + html.escape(str(node_id), quote=quote) + "</p>")
    for node_id in doc["dim"]:
        parts.append(
            '<p style="opacity:0.4">'
            + html.escape(str(node_id), quote=quote)
            + "</p>"
        )
    outcome = doc["outcome"]
    if outcome["visible"] is True:
        action = html.escape(str(outcome["action"]), quote=quote)
        authorized = "true" if outcome["authorized"] is True else "false"
        parts.append("<p>" + action + " authorized " + authorized + "</p>")
    if doc["owner_expired"] is True:
        parts.append("<p>expired</p>")
    inner = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        '<head><meta charset="utf-8"><title>TESTBED LIVE</title></head>\n'
        "<body>\n" + inner + "\n</body>\n</html>\n"
    )
