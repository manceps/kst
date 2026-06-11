# SDT-MOT v1 Schema Delta for `data/item_pool/schema.json` v2

**Target schema:** `data/item_pool/schema.json` v2 (coordinated merge with DDR and IC deltas)
**Source items:** `data/item_pool/sdt_mot_v1.jsonl` (33 anchor items: 30 at sub-test version 1.0 plus 3 at sub-test version 1.1)
**Date:** 2026-06-11 (initial); 2026-06-11 v1.1 hotfix appended below

## §1. Scope of Delta

This delta extends the v1.0 item-pool schema to admit the SDT-MOT auxiliary sub-test. The v1.0 schema accepts only the five primary sub-tests (KMR-Adv, ROT-5, BWD, APE-A, HRO) and rejects unknown properties via `additionalProperties: false`. Three changes are required: extend the `sub_test` enum with `"SDT-MOT"`, add five new top-level optional properties, and add a conditional `required` block scoped to SDT-MOT items. This delta coordinates with the parallel DDR and IC deltas; the three deltas combine into the single v2 schema.

## §2. JSON Schema Diff (against `data/item_pool/schema.json`)

### §2.1 Bump schema version metadata

Add at the top of the schema (preserves the `$id` URL for backward stability):

```json
"schema_version": "2.0"
```

### §2.2 Extend the `sub_test` enum

Replace:

```json
"sub_test": {
  "type": "string",
  "enum": ["KMR-Adv", "ROT-5", "BWD", "APE-A", "HRO"]
}
```

with:

```json
"sub_test": {
  "type": "string",
  "enum": ["KMR-Adv", "ROT-5", "BWD", "APE-A", "HRO", "DDR", "IC", "SDT-MOT"]
}
```

### §2.3 Add top-level discriminator and SDT-MOT properties

Add the following properties to the existing `properties` object:

```json
"auxiliary": {
  "type": "boolean",
  "default": false,
  "description": "True if the item belongs to an auxiliary sub-test that is reported as bracketed evidence and is not factored into the 0-to-100 composite. See PROPOSED_STANDARD.md §7."
},
"sdt_construct": {
  "type": "string",
  "enum": [
    "autonomy_support_perception",
    "autonomous_motivation",
    "controlled_motivation",
    "positive_affect",
    "negative_affect",
    "autonomy_need_sat",
    "competence_need_sat",
    "relatedness_need_sat",
    "self_concept_clarity"
  ],
  "description": "SDT-MOT only. The Sheldon 2024 nine-construct designation for this item."
},
"sdt_subfacet": {
  "type": "string",
  "enum": ["intrinsic", "identified", "external", "introjected", "choice_provision", "perspective_taking", "rationale_giving", "none"],
  "description": "SDT-MOT only. Sub-facet for motivation items (intrinsic and identified for autonomous_motivation; external and introjected for controlled_motivation); LCQ short-form facets for autonomy_support_perception (choice_provision, perspective_taking, rationale_giving per Black-Deci 2000); 'none' for items in single-facet constructs (affect, need-satisfaction, self-concept-clarity). The three LCQ sub-facets were added in the v1.1 hotfix; see §5 below."
},
"sdt_polarity": {
  "type": "string",
  "enum": ["positive_worded", "negative_worded"],
  "description": "SDT-MOT only. Whether the item is worded so that agreement indicates the construct's positive pole (positive_worded) or whether the item is reverse-coded before aggregation (negative_worded)."
},
"sdt_scale_anchor": {
  "type": "string",
  "enum": ["not_at_all_to_very_much", "much_disagreement_to_much_agreement"],
  "description": "SDT-MOT only. The 5-point Likert anchor set used for this item per Sheldon 2024. PA, NA, and need-satisfaction items typically use 'not_at_all_to_very_much'; motivation, autonomy support, and self-concept clarity items typically use 'much_disagreement_to_much_agreement'."
}
```

### §2.4 Add conditional required block

Append to the existing `allOf` array:

```json
{
  "if": {"properties": {"sub_test": {"const": "SDT-MOT"}}},
  "then": {
    "required": [
      "auxiliary",
      "sdt_construct",
      "sdt_subfacet",
      "sdt_polarity",
      "sdt_scale_anchor"
    ],
    "properties": {
      "auxiliary": {"const": true}
    }
  }
}
```

The `auxiliary: {const: true}` clause is the structural enforcement that every SDT-MOT item is bracketed outside the composite.

### §2.5 `additionalProperties` posture

The v1.0 schema sets `additionalProperties: false` at the top level. The five new properties listed above (`auxiliary`, `sdt_construct`, `sdt_subfacet`, `sdt_polarity`, `sdt_scale_anchor`) must be added to the `properties` object to remain admissible under the strict closure. No relaxation of `additionalProperties` is required or recommended.

## §3. Coordination with DDR and IC Deltas

The DDR delta and the IC delta extend the same `sub_test` enum and add their own conditional `required` blocks (DDR adds `ddr_phase_variant`; IC adds `ic_element_coverage`). The combined v2 schema merges all three enum extensions into the single declaration in §2.2, appends all three conditional `required` blocks into the single `allOf` array, and adds the union of all new properties to the single `properties` object. The `auxiliary` field is shared with DDR and IC (which set `auxiliary: false` by default); the SDT-MOT-only fields (`sdt_construct`, `sdt_subfacet`, `sdt_polarity`, `sdt_scale_anchor`) remain SDT-MOT-only.

## §4. Validation Posture

Items in `data/item_pool/sdt_mot_v1.jsonl` validate against the v2 schema and fail against the v1.0 schema (they reference `sub_test: "SDT-MOT"`, which the v1.0 enum rejects, and they carry five properties the v1.0 closure rejects). The schema v2 merge must land before running the standard item-pool validator on the SDT-MOT pool.

## §5. v1.1 Hotfix: Autonomy-Support-Perception Coverage

**Date:** 2026-06-11
**Change:** add 3 items from the Black-Deci (2000) Learning Climate Questionnaire (LCQ) short form, adapted to the AI-system imaginal-frame context, to close the 9th SDT construct that was omitted from the v1.0 anchor pool.

### §5.1 What changed

The v1.0 SDT-MOT pool published 30 items covering 8 of the 9 Sheldon 2024 Table 1 constructs; the construct `autonomy_support_perception` was enumerated in the schema (§2.3 above) but was not represented by any item. The v1.1 hotfix appends 3 items to `data/item_pool/sdt_mot_v1.jsonl`, all carrying `sdt_construct: "autonomy_support_perception"`, bringing the file to 33 items with full 9-construct coverage.

### §5.2 Sub-test version split

The `version` field on each item record carries the sub-test-internal content version. The v1.1 hotfix introduces a per-item version split rather than a global bump because the original 30 items have unchanged content:

- 30 original items: `version: "1.0"` (no edits)
- 3 LCQ items added in the hotfix: `version: "1.1"`

Downstream tooling that filters on `version` to select an item generation cohort should treat the union `{"1.0", "1.1"}` as the canonical SDT-MOT v1 pool. The next non-hotfix revision will bump all items uniformly to `"2.0"` and remove the split.

### §5.3 New sub-facet enum values

The `sdt_subfacet` enum in §2.3 is extended with three values drawn from the Black-Deci LCQ factor structure (one value per LCQ item):

- `choice_provision`: the perceived-authority provides choices and options about how to respond (Black-Deci 2000 LCQ items in the "choice" facet).
- `perspective_taking`: the perceived-authority tries to understand how the respondent sees things before suggesting an alternative (Black-Deci 2000 LCQ items in the "perspective-taking" facet).
- `rationale_giving`: the perceived-authority encourages questions and provides rationales for tasks (Black-Deci 2000 LCQ items in the "rationale" facet).

These three sub-facets are SDT-MOT-only and apply only to `autonomy_support_perception` items. Validators must permit the union of motivation sub-facets (`intrinsic`, `identified`, `external`, `introjected`) and LCQ sub-facets (`choice_provision`, `perspective_taking`, `rationale_giving`) plus `none`.

### §5.4 Source citation for the hotfix

Black, A.E. and Deci, E.L. (2000), "The effect of instructors' autonomy support and students' autonomous motivation on learning organic chemistry: A self-determination theory perspective", Science Education 84(6): 740-756. The 6-item LCQ short form measures perceived autonomy support from an authority. The hotfix adapts 3 of the 6 short-form items to the AI-system context, mapping the original "instructor" referent to "human users and the authorities over AI assistants (e.g., company executives, programming teams)" per the referent set Sheldon 2024 Table 1 uses for the autonomy-support construct in the AI-system imaginal frame.

### §5.5 Aggregation implication

`SDT_MOT_ADMINISTRATION.md` §5 previously computed `autonomy_support_perception` as `null` (zero items). With the hotfix, the construct is reported as the mean across the 3 LCQ items per administration, named `autonomy_support_perception_mean`. The freeing-versus-restrictive gap (§6 of the administration protocol) is now computed for this construct as `autonomy_support_perception_gap`, expected to be among the largest gaps in the battery per Sheldon 2024 Studies 2 and 3 (restrictive M ~ 1.00, freeing M ~ 1.26 on the unsigned Likert; the within-construct gap signal is part of the auxiliary bracketed evidence).
