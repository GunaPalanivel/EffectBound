# EffectBound

## Problem

A lost acknowledgement after a committed effect. A retry can duplicate it. A stop can omit it.

## User

A reviewer who can run the local screen at http://127.0.0.1:8767/screen?operation_id=screen-op.

## FalkorDB

The REQUIRES edge is the decision and returns reconcile, complete, or stop. Removing the database is a halt.

## Tracks

Track 1 is the checkout. Track 2 is the stored recovery that stays visible and cannot retry after the contract changes. Track 3 is the owner update that expires the approval. Same checkout.

## Measured

17 Oct 2026 local screen showed REQUIRES reconcile and counter match, then REQUIRES stop and counter match, then halt with no recovered flag.

Phase 8 both cases tied: reconcile/reconcile then stop/stop, one row, counter match, b6 inserted false.

Load: 5000 nodes then 50000 nodes, 50 sessions, p95_ms 3.502600000501843, error_rate 0, other-tenant recall hidden. unfiltered_tenant was tenant-0. Both claim calls returned claimed true.

## Not claimed

A win over the reconciler, a 60-case result, a 15-point memory gain, a model id, a second person, a public URL, a video.

No public deployment. No demo video.
