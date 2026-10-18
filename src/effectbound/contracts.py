"""Phase 1 schema, action catalog, and effect-counter contract.

No agent, no holdout, and no model call live in this module.
"""

ACTIONS = ("reconcile", "complete", "stop")

NODES = (
    "operation",
    "observed_effect",
    "dependency",
    "contract_version",
    "policy",
    "approval",
    "attempt",
    "outcome",
)

EDGES = (
    ("operation", "HAS_EFFECT", "observed_effect"),
    ("operation", "DEPENDS_ON", "dependency"),
    ("operation", "BOUND_TO", "contract_version"),
    ("contract_version", "REQUIRES", "policy"),
    ("attempt", "AUTHORIZED_BY", "approval"),
    ("attempt", "OF", "operation"),
    ("attempt", "YIELDED", "outcome"),
)

EFFECT_COUNTER = {
    "reads": ("service_store", "sealed_manifest"),
    "agent_can_write": (),
    "unknown_is_recovered": False,
}
