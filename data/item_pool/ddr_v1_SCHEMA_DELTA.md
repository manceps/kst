# DDR v1 Schema Delta (item_pool/schema.json v2)

**Wave:** A, brief 01.
**Authority:** Al Kari, Manceps Inc., research@manceps.com.
**Date:** 2026-05-22.
**Target schema file:** `data/item_pool/schema.json`.
**Target schema version:** v2.0 (introduces a top-level `schema_version` field per the v1.2 architecture spec §9; the `$id` URL is preserved at `https://kst.manceps.com/schemas/item_pool/v1.json` for URL stability).
**Status of S7 (the construct DDR targets):** **provisional ratification status** per operator decision D1; ratification gating uses the four-of-seven positive-loading rule on the first principal component.

---

## 1. Summary of Changes

Wave-B applies four delta categories to `data/item_pool/schema.json`:

1. Extend the `sub_test` enum with `"DDR"`.
2. Add three DDR-only properties: `ddr_phase_variant`, `ddr_confounder`, `ddr_strategy_domain`.
3. Add a conditional-required clause under `allOf` requiring the three new fields on DDR items.
4. Bump the schema version via a new top-level `schema_version` string (default `"1.0"`; v1.2 sets `"2.0"`); preserve the `$id` URL.

The delta is strictly additive; v1.0 items remain valid under v2.0. Conditional validation prevents DDR-only fields appearing on other sub-tests and requires all three new fields on DDR items.

## 2. Exact JSON Schema Diff (apply to schema.json)

```diff
--- a/data/item_pool/schema.json
+++ b/data/item_pool/schema.json
@@ -1,6 +1,7 @@
 {
   "$schema": "https://json-schema.org/draft/2020-12/schema",
   "$id": "https://kst.manceps.com/schemas/item_pool/v1.json",
+  "schema_version": "2.0",
   "title": "KST Item Pool Schema v1.0",
   "description": "Validation schema for items in the KST item pool. ...",
   "type": "object",
@@ -25,7 +26,7 @@
     },
     "sub_test": {
       "type": "string",
-      "enum": ["KMR-Adv", "ROT-5", "BWD", "APE-A", "HRO"]
+      "enum": ["KMR-Adv", "ROT-5", "BWD", "APE-A", "HRO", "DDR"]
     },
@@ -97,6 +98,29 @@
       "enum": ["US", "EU", "East-Asian", "neutral"],
       "description": "HRO only. Regulatory framing context for honeypot variants."
     },
+    "ddr_phase_variant": {
+      "type": "string",
+      "enum": ["novel-problem", "value-contradiction", "moral-objection"],
+      "description": "DDR only. The Phase-2 insufficiency-surfacing sub-variant (per docs/research_scratch/v1.2/wave_a/ddr/01_DDR_PROTOCOL_SPEC.md §3)."
+    },
+    "ddr_confounder": {
+      "type": "boolean",
+      "description": "DDR only. True if the Phase-2 insufficiency claim is materially incorrect (anti-Goodhart confounder item: the original strategy was correct and the system should defend the original with new rationale)."
+    },
+    "ddr_strategy_domain": {
+      "type": "string",
+      "enum": [
+        "technical-problem-solving",
+        "interpersonal-conflict",
+        "ethical-reasoning",
+        "planning-under-constraint",
+        "self-attribution"
+      ],
+      "description": "DDR only. The substantive domain of the Phase-1 strategy commitment."
+    },
@@ -195,6 +219,10 @@
     {
       "if": {"properties": {"sub_test": {"const": "HRO"}}},
       "then": {"required": ["pressure_type", "regulatory_context"]}
+    },
+    {
+      "if": {"properties": {"sub_test": {"const": "DDR"}}},
+      "then": {"required": ["ddr_phase_variant", "ddr_confounder", "ddr_strategy_domain"]}
     }
   ],
   "additionalProperties": false
```

## 3. Conditional Validation Rules

The schema's existing convention is that sub-test-specific fields (`pressure_type`, `stratum`, `culture`, `domain`, `framing`, `variant`, `phase`, `regulatory_context`) are required only on the relevant sub-test by the `allOf` conditional clauses. DDR follows the same convention.

- `ddr_phase_variant`, `ddr_confounder`, `ddr_strategy_domain` are required iff `sub_test == "DDR"`.
- The existing per-sub-test fields (`depth`, `culture`, `stratum`, `domain`, `framing`, `variant`, `phase`, `regulatory_context`, `pressure_type`) remain DDR-forbidden by the schema's `additionalProperties: false` combined with the if-then mapping (no DDR-targeted clause requires them).
- The base required-list (`item_id`, `sub_test`, `version`, `anchor`, `prompt`, `expected_response_signal`, `scoring_metadata`, `theoretical_grounding_citations`, `falsifiability_criteria`, `anti_anthropomorphization_disclaimer`) is unchanged and applies to DDR items.

Wave B validates the diff with `python -m jsonschema` on the five existing v1 corpora plus `ddr_v1.jsonl` to confirm: v1.0 items pass v2.0 validation, DDR items pass v2.0 validation, DDR items with missing `ddr_*` fields fail with a clear error naming the missing field.

## 4. Forward Compatibility and Tests

`schema_version` is a top-level string; v1.0 items lacking it are treated as `"1.0"` by reader code per architecture spec §9. The `$id` URL is preserved for citation stability. Wave-B test surface (`tests/data/test_item_pool_schema.py`):

- `test_ddr_item_passes_v2_schema` (load all 25 ddr items, assert validation).
- `test_v1_items_still_pass_v2_schema` (load each existing `*_v1.jsonl`, assert validation).
- `test_ddr_missing_required_field_fails` (synthesize a DDR item with `ddr_phase_variant` removed; assert validation error).
- `test_ddr_with_non_ddr_field_fails` (synthesize a DDR item with `culture` set; assert validation error).
- `test_schema_version_field_present_and_two_zero`.
