"""Bounded dependency walks.

Hop limit 4 is frozen. A directed walk that reaches a repeated node is a
cycle. A simple path that reaches the end within the hop limit is a path.
A path that exists only past that limit, and at or before 8 hops, is
unknown. A search that finishes with no path is no_path.
"""

from __future__ import annotations

# Frozen before any live walk. A chain longer than this is unknown.
HOP_LIMIT = 4
# Searches stop here, so a finished empty walk is no_path rather than unknown.
PATH_CEILING = 8
WALK_GRAPH = "changeguard_walk"
EMPTY_GRAPH_ERROR = "Invalid graph operation on empty key"


def plant_checkout_chain(db) -> None:
    """Merge checkout-api -> payments -> ledger on the walk graph."""

    _merge_chain(db, ("checkout-api", "payments", "ledger"))


def plant_cycle(db) -> None:
    """Merge cycle-a and cycle-b with DEPENDS_ON both ways."""

    _merge_chain(db, ("cycle-a", "cycle-b"))
    _merge_chain(db, ("cycle-b", "cycle-a"))


def plant_over_depth(db) -> None:
    """Merge dependency nodes n0 through n5 in a single chain."""

    _merge_chain(db, tuple(f"n{index}" for index in range(6)))


def reset_walk(db) -> None:
    """Delete the walk graph. A missing graph is already empty."""

    graph = db.select_graph(WALK_GRAPH)
    try:
        graph.delete()
    except Exception as exc:
        if EMPTY_GRAPH_ERROR in str(exc):
            return
        raise


def walk(db, graph_name: str, start_id: str, end_id: str, hops: int = HOP_LIMIT) -> dict:
    """Classify a dependency walk as path, cycle, unknown, or no_path."""

    limit = _checked_hops(hops)
    graph = db.select_graph(graph_name)
    if limit >= 1:
        cycle = _directed_cycle(graph, start_id, limit)
        if cycle is not None:
            return {"result": "cycle", "nodes": cycle}
    if start_id == end_id and _node_exists(graph, start_id):
        return {"result": "path", "nodes": [start_id]}
    if limit >= 1:
        found = _simple_path(graph, start_id, end_id, 1, limit)
        if found is not None:
            return {"result": "path", "nodes": found}
    if limit < PATH_CEILING:
        longer = _simple_path(graph, start_id, end_id, limit + 1, PATH_CEILING)
        if longer is not None:
            return {"result": "unknown"}
    return {"result": "no_path", "nodes": []}


def _checked_hops(hops: int) -> int:
    if type(hops) is not int or hops < 0 or hops > PATH_CEILING:
        raise ValueError("hops must be an int from 0 through 8")
    return hops


def _span(low: int, high: int) -> str:
    if type(low) is not int or type(high) is not int:
        raise ValueError("hop span must be ints")
    if low < 1 or high > PATH_CEILING or low > high:
        raise ValueError("hop span is outside 1 through 8")
    return f"*{low}..{high}"


def _merge_chain(db, ids: tuple[str, ...]) -> None:
    graph = db.select_graph(WALK_GRAPH)
    for src, dst in zip(ids, ids[1:]):
        graph.query(
            "MERGE (a:dependency {id: $src}) "
            "MERGE (b:dependency {id: $dst}) "
            "MERGE (a)-[:DEPENDS_ON]->(b)",
            {"src": src, "dst": dst},
        )


def _node_exists(graph, node_id: str) -> bool:
    result = graph.query(
        "MATCH (n:dependency {id: $id}) RETURN n.id LIMIT 1",
        {"id": node_id},
    )
    return bool(result.result_set)


def _cell(value):
    if isinstance(value, bytes):
        return value.decode()
    return value


def _edges_within(graph, start_id: str, hops: int) -> list[tuple[str, str]]:
    """Directed edges whose destination is at most `hops` steps from start."""

    direct = graph.query(
        "MATCH (s:dependency {id: $start_id})-[:DEPENDS_ON]->(b:dependency) "
        "RETURN s.id, b.id",
        {"start_id": start_id},
    )
    rows = list(direct.result_set)
    if hops >= 2:
        span = _span(1, hops - 1)
        further = graph.query(
            "MATCH (s:dependency {id: $start_id})"
            f"-[:DEPENDS_ON{span}]->(a:dependency)-[:DEPENDS_ON]->(b:dependency) "
            "RETURN a.id, b.id",
            {"start_id": start_id},
        )
        rows.extend(further.result_set)
    edges = []
    for row in rows:
        if len(row) < 2 or row[0] is None or row[1] is None:
            continue
        edges.append((_cell(row[0]), _cell(row[1])))
    return edges


def _directed_cycle(graph, start_id: str, hops: int) -> list[str] | None:
    adjacent: dict[str, list[str]] = {}
    for src, dst in _edges_within(graph, start_id, hops):
        adjacent.setdefault(src, []).append(dst)
    expanded = {start_id}

    def expand(node: str, path: list[str]) -> list[str] | None:
        if len(path) - 1 >= hops:
            return None
        for nxt in adjacent.get(node, ()):
            if nxt in path:
                return path + [nxt]
            if nxt in expanded:
                continue
            expanded.add(nxt)
            found = expand(nxt, path + [nxt])
            if found is not None:
                return found
        return None

    return expand(start_id, [start_id])


def _simple_path(
    graph,
    start_id: str,
    end_id: str,
    low: int,
    high: int,
) -> list[str] | None:
    query = (
        "MATCH (s:dependency {id: $start_id}), (t:dependency {id: $end_id}) "
        f"MATCH p = (s)-[:DEPENDS_ON{_span(low, high)}]-(t) "
        "RETURN [n in nodes(p) | n.id] AS nodes "
        "ORDER BY length(p) "
        "LIMIT 1"
    )
    result = graph.query(query, {"start_id": start_id, "end_id": end_id})
    if not result.result_set:
        return None
    raw = result.result_set[0][0]
    if not raw:
        return None
    nodes = [_cell(item) for item in raw]
    if nodes[0] == end_id and nodes[-1] == start_id and start_id != end_id:
        nodes = list(reversed(nodes))
    if nodes[0] != start_id or nodes[-1] != end_id:
        return None
    if len(nodes) != len(set(nodes)):
        return None
    return nodes
