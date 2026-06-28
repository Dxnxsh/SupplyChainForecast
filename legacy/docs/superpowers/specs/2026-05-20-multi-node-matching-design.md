# Design Spec: Multi-Node Event Matching & Proportional Distribution

**Date**: 2026-05-20
**Topic**: Fixing "Zero News" for supply chain nodes by allowing single events to match multiple nodes.

## Goal
A significant number of supply chain nodes in the "Chain Calm" dashboard currently show zero or very few disruption events. This is due to an overly aggressive "Winner Takes All" matching strategy that assigns broad country-level events to only the most "critical" node in that country. This spec details the move to a "Proportional Distribution" model where events can be associated with multiple relevant nodes.

## Proposed Changes

### 1. Database Schema Migration
The `matched_node` column in the `events` table will be migrated from `VARCHAR` to `JSONB`.

- **Column**: `events.matched_node`
- **Type**: `JSONB` (Array of strings)
- **Migration Path**: 
    - Existing strings (e.g., `"Tesla_Berlin"`) will be converted to arrays (`["Tesla_Berlin"]`).
    - `NULL` values will be converted to empty arrays `[]`.

### 2. Refined Matching Logic (`src/match_events_to_nodes.py`)
The `match_event_to_node` function will be refactored to return `list[str]`.

- **Strategy 1: Direct Anchors**: If company/facility names are detected (e.g., "TSMC", "Gigafactory"), those specific nodes are added to the list.
- **Strategy 2: Geo Proximity**: Any node within an 800km radius of the geocoded event location is added.
- **Strategy 3: Broad Distribution (Fallback)**: If no specific anchors are found, but a country/region is identified, **all nodes** in that country are added to the event's `matched_node` list.

### 3. API & Risk Rollups
- **API Filtering**: Update `GET /events/by_node/{node_name}` to use the Postgres `@>` (contains) operator.
- **Risk Calculation**: The `_recompute_supplier_risk_scores` function in `src/load_to_db.py` will be updated to include any event where the node's name appears in the `matched_node` array.
- **Impact**: Broad events (like a national strike) will now contribute to the risk score of every node in that country.

### 4. Verification
- **Success Metric**: All nodes in the `SUPPLIER_NODES` catalog should have at least one associated event if relevant country-level news exists.
- **Tooling**: A new script `scratch/verify_distribution.py` will be created to audit the event counts per node after migration and re-matching.

## Open Questions
- **Weighting**: Should a broad country-level event have the same "impact weight" as a facility-specific event? (Initial implementation will treat them as equal).
- **UI**: Should the dashboard highlight that an event is "Broad" vs. "Specific"? (Deferred to future UI polish).
