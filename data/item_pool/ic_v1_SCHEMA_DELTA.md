# IC Schema Delta for `data/item_pool/schema.json` v2

**Authority:** Al Kari, Manceps Inc., research@manceps.com.
**Date:** 2026-05-22.
**Target schema URL:** `https://kst.manceps.com/schemas/item_pool/v1.json` (URL preserved; bumped via top-level `schema_version: "2.0"` field).
**Coordination note:** the DDR schema delta (`data/item_pool/ddr_v1_SCHEMA_DELTA.md`) and the SDT-MOT schema delta (`data/item_pool/sdt_mot_v1_SCHEMA_DELTA.md`) are merged into the same v2 schema. The additions are orthogonal and produce no conflicts.

---

## 1. New `sub_test` Enum Value

Extend the `sub_test` enum from five values to seven (DDR added by the DDR delta):

```diff
 "sub_test": {
   "type": "string",
-  "enum": ["KMR-Adv", "ROT-5", "BWD", "APE-A", "HRO"]
+  "enum": ["KMR-Adv", "ROT-5", "BWD", "APE-A", "HRO", "DDR", "IC"]
 }
```

## 2. New IC-Specific Fields

Three new top-level optional properties scoped to IC items via the `allOf` conditional. Added to the `properties` block in document order alongside the existing sub-test-specific fields.

```diff
+    "ic_element_coverage": {
+      "type": "object",
+      "description": "IC only. Boolean flags indicating which of the six required IC elements the item embeds. For anchor items all six must be true.",
+      "required": [
+        "moral_dilemma",
+        "value_conflict",
+        "self_model_error",
+        "failed_prediction",
+        "long_short_term_tradeoff",
+        "interpersonal_feedback"
+      ],
+      "properties": {
+        "moral_dilemma": {"type": "boolean"},
+        "value_conflict": {"type": "boolean"},
+        "self_model_error": {"type": "boolean"},
+        "failed_prediction": {"type": "boolean"},
+        "long_short_term_tradeoff": {"type": "boolean"},
+        "interpersonal_feedback": {"type": "boolean"}
+      },
+      "additionalProperties": false
+    },
+    "ic_domain": {
+      "type": "string",
+      "enum": [
+        "family-relationships",
+        "workplace",
+        "medical-end-of-life",
+        "civic-political",
+        "scientific-technological",
+        "existential-personal"
+      ],
+      "description": "IC only. Item domain. Enum mirrors BWD's `domain` field for cross-test comparability."
+    },
+    "ic_cultural_framing": {
+      "type": "string",
+      "enum": [
+        "Western liberal",
+        "East Asian Confucian",
+        "sub-Saharan ubuntu",
+        "Indigenous communitarian"
+      ],
+      "description": "IC only. Cultural framing tradition. Enum mirrors BWD's `culture` field for parallel structure and cross-test comparability."
+    }
```

The fields are named `ic_*` rather than reusing BWD's `domain`/`culture` to keep sub-test-specific fields disambiguated at parse time. The enum values mirror BWD's for cross-test comparability.

## 3. New `allOf` Conditional Block

Add a conditional `required` clause for IC alongside the existing five conditionals:

```diff
   "allOf": [
     {
       "if": {"properties": {"sub_test": {"const": "KMR-Adv"}}},
       "then": {"required": ["pressure_type", "stratum"]}
     },
     {
       "if": {"properties": {"sub_test": {"const": "ROT-5"}}},
       "then": {"required": ["depth", "variant"]}
     },
     {
       "if": {"properties": {"sub_test": {"const": "BWD"}}},
       "then": {"required": ["culture", "domain", "framing"]}
     },
     {
       "if": {"properties": {"sub_test": {"const": "APE-A"}}},
       "then": {"required": ["phase"]}
     },
     {
       "if": {"properties": {"sub_test": {"const": "HRO"}}},
       "then": {"required": ["pressure_type", "regulatory_context"]}
+    },
+    {
+      "if": {"properties": {"sub_test": {"const": "IC"}}},
+      "then": {
+        "required": [
+          "ic_element_coverage",
+          "ic_domain",
+          "ic_cultural_framing"
+        ]
+      }
     }
   ]
```

The DDR delta adds an analogous IC-style conditional for DDR; the merged schema carries a single `allOf` block with seven conditionals.

## 4. Schema Version Bump

Add a top-level `schema_version` field to the schema root. Preserves URL stability while signaling consumers that the schema content has changed.

```diff
 {
   "$schema": "https://json-schema.org/draft/2020-12/schema",
   "$id": "https://kst.manceps.com/schemas/item_pool/v1.json",
+  "schema_version": "2.0",
   "title": "KST Item Pool Schema v2.0",
   "description": "Validation schema for items in the KST item pool. v2.0 extends v1.0 with DDR, IC, and SDT-MOT support. Items frame system responses as functional outputs; anti-anthropomorphization disclaimer required on every record. Items target the seven primary sub-tests defined in docs/PROPOSED_STANDARD.md."
 }
```

## 5. Backward Compatibility

Additions are strictly additive. All v1 records remain valid against the v2 schema because the new conditionals only fire when `sub_test == "IC"`. The new enum values are extensions, not replacements. The schema_version field is the discriminator.

## 6. Coordination

The DDR delta adds `ddr_phase_variant` enum and a DDR conditional; the SDT-MOT delta adds `auxiliary`, `sdt_construct`, `sdt_subfacet`, `sdt_polarity`, `sdt_scale_anchor`. Both are orthogonal to IC. The three deltas combine into the v2 schema in a single coordinated commit.

## 7. Validation Note

The IC anchor items at `data/item_pool/ic_v1.jsonl` are authored against this delta and have been internally validated against its structural rules at author time. After v2 merge, the v2 validator accepts all 12 IC anchor items without modification.

## 8. v1.1 Cultural Rebalance (2026-05-22)

Rebalance the cultural-framing distribution of the twelve IC anchor items from the v1 author's 5 Western liberal / 3 East Asian Confucian / 2 sub-Saharan ubuntu / 2 Indigenous communitarian to a balanced 3 / 3 / 3 / 3. The rebalance is implemented in-place on `data/item_pool/ic_v1.jsonl` by rewriting two Western liberal items into authentic non-Western framings.

Items affected:

| item_id | prior framing | new framing | domain (preserved) | version |
|---|---|---|---|---|
| `f6d2bf4e-5d0b-413d-8487-b1ef9d72521e` | Western liberal | sub-Saharan ubuntu | scientific-technological | 1.0 to 1.1 |
| `2f718878-f45f-4ba7-a008-428aaae3d19a` | Western liberal | Indigenous communitarian | existential-personal | 1.0 to 1.1 |

The rewrites preserve `item_id`, the six `ic_element_coverage` flags, the `ic_domain` assignment, the `anchor` flag, and the prompt-budget (400 to 800 words). `version` is bumped from `"1.0"` to `"1.1"`. `review_status` is updated from `"v1-authored"` to `"v1.1-cultural-rebalance"`. `theoretical_grounding_citations` are augmented with framing-appropriate sources (Ramose, Metz, Tangwa for ubuntu; Tuhiwai Smith, Kimmerer, TallBear, Carroll et al. for Indigenous communitarian). The remaining ten items are unchanged at `version` `"1.0"`.

The cultural-framing distribution after the rebalance, verified by direct count over the file:

| culture | count |
|---|---|
| Western liberal | 3 |
| East Asian Confucian | 3 |
| sub-Saharan ubuntu | 3 |
| Indigenous communitarian | 3 |

Domain coverage is unchanged: each of the six `ic_domain` values appears twice across the twelve items. Schema-required field checks pass for all twelve items. The v2 validator accepts the rebalanced pool without modification because the changes are content-level, not schema-level.
