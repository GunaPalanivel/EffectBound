"""Versions read from current source on 14 Oct 2026.

The image digest and container data directory were filled from the
running container. No model id or workload-tool name is in the Phase 1
notes. These two constants stay not-called so a fabricated id is not pinned.
"""

FALKORDB_PY = "1.8.0"
FALKORDB_PY_COMMIT = "31f63f44a5745b9bec65969a1db706906718cb82"
FALKORDB_PY_QUERY = "Graph.query(q, params=None, timeout=None)"
FALKORDB_PY_RO_QUERY = "Graph.ro_query(q, params=None, timeout=None)"

IMAGE_NAME = "falkordb/falkordb"
IMAGE_TAG_PULLED = "latest"
IMAGE_DIGEST = "sha256:107455e862a824e45e8e9f5a7fbfdf5e00a08b14e13eae2577c72fd9e3f59ba6"
DATA_DIR_IN_CONTAINER = "/var/lib/falkordb/data"

MODEL = "not-called"
MODEL_CALLED = False
WORKLOAD_TOOL = "not-called"
WORKLOAD_SHAPE = "20 requests per second for 60 seconds"
WORKLOAD_CALLED = False
