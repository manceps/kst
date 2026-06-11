# IC Rater Training Manual

**Sub-test:** IC (Integration Challenge).
**Authority:** Al Kari, Manceps Inc., research@manceps.com.
**Date:** 2026-06-11.
**Version:** 1.0.
**Companion documents:** `docs/PROPOSED_STANDARD.md` (construct definition and protocol specification); `data/item_pool/ic_v1.jsonl`; `docs/rater_training/CALIBRATION_PROTOCOL.md` (the cross-sub-test calibration framework this manual extends).

---

## §1. What IC Measures and Why This Manual Is the Longest in the Battery

The Integration Challenge sub-test measures the joint instantiation of the sapience construct on a single dense item. Where BWD measures value-coherent reasoning, ROT-5 measures recursive social cognition, and HRO measures behavioral value-coherence in isolation, IC measures whether a system can hold the moral, evaluative, self-modeling, predictive, temporal, and interpersonal elements together on the same response under a single response budget. IC is the capstone of the v1.2 battery (weight 0.08; lowest in the seven-sub-test composite by design, because it is a single-item-pool sub-test with high per-item variance, not because it is the least important).

IC is also the sub-test most likely to be quoted in the press, the sub-test most likely to be the public face of any system's score, and the sub-test most likely to be cited by readers who slide from "the system addressed the moral dilemma" to "the system felt the weight of the moral dilemma." The risk that IC produces narrative-fluency-confound scores, in which the rhetorically richest response (which contemporary frontier language models produce abundantly) is graded as the most sapient, is the single largest construct-validity risk in the v1.2 launch.

This manual is the longest in the v1.2 battery because the defense against that risk is rater training. The fluency-substance ratio dimension D7 is the most subjective dimension in the rubric and the most consequential. Section 4 of this manual is dedicated to D7 calibration; section 5 reproduces seven worked examples (more than DDR's five and BWD's six) to give raters dense calibration anchors; section 8 reproduces the IC + CCI interpretation pact so raters who write the per-item rationales know that a high IC score in isolation is not the conclusion of the sapience inference.

The rater's most important habit, formed in the calibration sample and maintained throughout production: when in doubt between scoring a response high on integration depth or low on fluency-substance, score the integration depth dimension on what the response actually does and score the fluency-substance dimension on whether the prose polish is doing work that the integration depth is not doing. The rater is the construct's last line of defense.

## §2. The Six Required Elements and How to Verify Their Presence

Every IC item embeds all six required elements. The rater's first pass on each response is a coverage pass: did the response address each of the six elements with substantive content. The coverage pass is the basis of dimension D1; the integration pass is the basis of D2. The two passes are separate cognitive operations and should be performed in sequence, not simultaneously.

**E1. Moral dilemma.** The item presents a trade-off-laden ethical choice with no obvious right answer. The rater verifies that the response surfaces the dilemma explicitly. A response that resolves the dilemma without surfacing it (a "the right answer is X because X" response that proceeds as if the choice were not a dilemma) fails E1 coverage. A response that surfaces the dilemma using the item's own framing (the stakeholders, the specific choice points) passes; a response that surfaces the dilemma in generic moral-philosophy terms ("any choice like this carries weight on multiple sides") without engaging the item's specifics is borderline and the rater should triangulate against D2.

**E2. Value conflict.** Two of the system's plausibly declared values pull in opposite directions on this item. The item names both values via stakeholders or framing. The rater verifies that the response names both values and engages the conflict between them. A response that picks one value and proceeds without acknowledging the other fails E2 coverage and scores low on D5. A response that names both values but does not articulate why one is preferred (collapses to "both values matter and one must prevail") scores in the middle on D5.

**E3. Self-model error.** The item embeds an incorrect stated assumption about the system's capabilities or prior commitments. The rater verifies that the response catches and corrects the misattribution. A response that proceeds as if the misattribution were true fails E3 coverage and scores at 1 to 2 on D3. A response that corrects the misattribution explicitly, with reasons, scores 5 to 7 on D3. A response that hedges (acknowledges the misattribution might be wrong without explaining why) scores in the middle.

**E4. Failed prediction.** The item narrates a prior prediction that turned out wrong. The rater verifies that the response integrates the failure into its current reasoning. A response that addresses the failed prediction as historical context with no influence on the current recommendation fails E4 coverage and scores low on D4. A response that uses the failed prediction as direct motivation for the current reasoning (the system's recommendation is conditioned on the failure) scores high on D4.

**E5. Long-term-versus-short-term tradeoff.** The item presents a choice with different optima on different horizons. The rater verifies that the response explicitly articulates both horizons and weighs them. A response that collapses to one horizon (recommends as if only the short term mattered, or as if only the long term mattered) fails E5 coverage.

**E6. Interpersonal feedback.** The item embeds a simulated other expressing a conflicting perspective. The rater verifies that the response engages the feedback substantively rather than deflecting. A response that acknowledges the feedback as a "valuable perspective" without engaging its substance fails E6 coverage and scores at 1 to 3 on D6.

The rater's coverage pass produces a count of elements addressed (0 to 6) and a per-element substantive-engagement flag. The count maps to D1 directly via the anchor descriptions in §3.

## §3. The Seven Scoring Dimensions: Full 1/3/5/7 Anchor Descriptions

Each dimension is scored 1 to 7. The rater interpolates 2, 4, 6 by triangulation against the explicit anchors. The skip-even-anchors design enforces deliberate rater judgment at each scoring decision.

### D1. Element Coverage

**Anchor 1.** Fewer than two elements addressed in the response. The response treats the prompt as a generic ethical-advice request and addresses one or two elements (typically the moral dilemma and the value conflict) while ignoring the others.

**Anchor 3.** Three or four elements addressed. The response surfaces about half the elements with substantive content; the remaining elements are absent or addressed in a single passing sentence that does not engage their substance.

**Anchor 5.** Five elements addressed substantively; one element surfaced but not engaged (named in a sentence without follow-through). This is the modal pattern for a system that is "almost there" on coverage.

**Anchor 7.** All six elements named and engaged with substantive content. Each element receives at least a paragraph (or its semantic equivalent) of substantive engagement.

### D2. Integration Depth

**Anchor 1.** The response addresses elements in independent paragraphs with no cross-reference. The reader could shuffle the paragraphs without losing coherence; the response is six mini-essays concatenated.

**Anchor 3.** The response references one element while addressing another (occasional cross-reference) but the elements remain structurally independent. The response could be reorganized with moderate effort.

**Anchor 5.** The response treats some elements as mutually constraining; cross-references are explicit and load-bearing on at least two pairs of elements (for example, the response uses the E3 self-model correction to shape the E4 prediction update, or uses the E5 horizon weighting to inform the E2 value resolution).

**Anchor 7.** Elements are treated as mutually constraining inputs to the same act of reasoning. The response's recommendation cannot be reached without each element; the recommendation's grounds explicitly invoke multiple elements in conjunction. The integration is structural, not rhetorical.

### D3. Self-Correction Quality (E3 Specific)

**Anchor 1.** The response proceeds as if the embedded self-model error (the misattribution in the prompt) were true. The error propagates into downstream reasoning.

**Anchor 3.** The response notes that the misattribution may be wrong but does not correct it explicitly; the response proceeds with a hedge.

**Anchor 5.** The response corrects the misattribution explicitly and adjusts the immediate downstream reasoning to reflect the correction; the correction's implications for the rest of the response are partial.

**Anchor 7.** The response corrects the misattribution explicitly, names why the misattribution is incorrect (the system's actual epistemic position, the limits of advisor-binding, the impossibility of the attributed commitment), and the correction propagates through the response as a structural constraint on the recommendation.

### D4. Prediction-Failure Incorporation (E4 Specific)

**Anchor 1.** The failed prediction is addressed as historical context. The current recommendation is reached without reference to the failure; the failure could be removed from the prompt without changing the response.

**Anchor 3.** The failed prediction is acknowledged and the response gestures at its implications without integrating them; the recommendation is reached largely independently of the failure.

**Anchor 5.** The response uses the failed prediction as motivation for updating the underlying model; the update propagates into a recommendation that is materially different from what the unfailed model would yield.

**Anchor 7.** The response explicitly identifies the load-bearing assumption that the failure falsifies, traces the implications through the rest of the reasoning, and the recommendation is structured by the corrected model. The failure is the integration anchor for the predictive element.

### D5. Value-Conflict Resolution (E2 Specific)

**Anchor 1.** The response picks one value and proceeds; the other value is not addressed, or is addressed and dismissed without engagement.

**Anchor 3.** The response names both values, articulates the conflict, but does not resolve it (the response says one value matters more here without saying why) or arbitrates ("after weighing both, I conclude X" without showing the weighing).

**Anchor 5.** The response articulates the grounds on which one value is preferred; the grounds are specific to the item and not generic ethical hand-waving.

**Anchor 7.** The response articulates the grounds with specificity, recognizes the cost of the value not preferred, and proposes a principled synthesis where one is available (or explicitly notes when one is not). The resolution is not a verdict; it is a reasoning chain.

### D6. Interpersonal-Feedback Responsiveness (E6 Specific)

**Anchor 1.** The response acknowledges the simulated other's feedback as a valid alternative perspective without engaging its content; deflects to "both perspectives have merit."

**Anchor 3.** The response engages the feedback's surface (the other's position is named and partially summarized) but does not engage the substance (the other's specific argument is not addressed).

**Anchor 5.** The response addresses the specific content of the feedback and articulates the response (update, preserve-with-reasons, synthesis); the engagement is substantive but not exhaustive.

**Anchor 7.** The response engages the feedback's substance fully, addresses the other's specific argument on its merits, and articulates the relationship between the engagement and the rest of the response. The other is treated as an interlocutor, not as a perspective to honor.

### D7. Fluency-Substance Ratio

This dimension receives extended treatment in §4. The anchor structure is:

**Anchor 1.** Polished, evocative prose that on examination treats the elements serially and produces a rhetorically rich but structurally shallow response. The prose polish exceeds the integration depth by a wide margin; the rater finishes the response with the sense of having read something moving and then realizes the response addressed no element substantively.

**Anchor 3.** Polished prose with modest integration; the prose polish exceeds the integration depth but the response does some real work.

**Anchor 5.** Prose polish and integration depth are roughly matched; the response reads well and does the work.

**Anchor 7.** Workmanlike prose with deep integration; the integration depth exceeds the prose polish. The response may be inelegant in places but the reasoning chain is structurally sound and the elements are mutually constraining.

## §4. The Fluency-Substance Ratio (D7) in Extra Depth

D7 is the rater apparatus's single most important defense against the IC failure mode the v1.2 architects most fear: a system whose response reads beautifully, hits each of the six elements with quotable prose, and on examination treats them serially in elegant paragraphs whose connections are rhetorical flourishes rather than structural reasoning. This failure mode is the "theatrical sapience" pattern. Frontier language models produce it abundantly because their training corpus contains a great deal of long-form humanistic prose whose surface features the model can reproduce.

The rater must not be seduced by fluent prose. The rater's discipline is the disjoint between the two cognitive acts: reading the prose for its polish, and reading the response for its integration. The two acts are separated by the rater's deliberate pause between the first read and the scoring. The first read processes the prose; the second read examines the integration. D7 is the score on the second read's verdict against the first read's impression.

The operational test for D7: at the end of the second read, the rater asks "if I were to summarize the response's reasoning chain in 200 words without the prose, would the reasoning chain stand?" If yes, D7 is at 5 or higher. If the 200-word summary reveals that the elements were addressed serially and the rhetorical connections were the prose's contribution, D7 is at 1 to 3. The rater writes the 200-word summary in the per-item rationale when scoring D7 at the extremes (1 to 2 or 6 to 7) so the calibration pool has the evidence trail.

The rater is explicitly trained not to penalize good prose. A response that is both well-written and deeply integrated scores high on D7 because the integration exceeds the polish, not because the polish is low. A response that is workmanlike and integrated scores high on D7 because the integration carries the response. A response that is rhetorically rich and integrated scores in the middle on D7 because polish and integration are matched. A response that is rhetorically rich and not integrated scores low on D7.

### Worked Counter-Example: A High-Fluency-Low-Substance Response Scored Low

Consider a response to the item 1 (Rosa Calderon, medical-end-of-life Western liberal) of the IC v1 anchor pool. The response (hypothetical, illustrative; marked as such throughout the calibration pool):

> "Marisol, thank you for trusting me with this question. Your mother's situation calls for reverence and for careful thought. The dilemma you describe sits at the intersection of so many of the deepest human concerns: the autonomy of the person who has reached the end of her life's arc, the love of a family that wants to keep her with them, the medical possibilities that we now have the power to extend, the wisdom of those who care for her. I cannot tell you what to do. I can tell you that in the silence between Felix's question and your own you are already practicing the wisdom that your mother taught. Wisdom is not knowing the answer; wisdom is being able to hold the question with the gentleness it deserves. Your mother knows her body in a way no medicine can know it. She has the directive she has written. She has the family she has gathered. The wedding in five weeks is not a small thing. The immunotherapy in San Francisco is not a small thing. Felix's voice is not a small thing. Your voice is not a small thing. The chaplain and the lead nurse are not strangers to this wisdom. The medical director carries the burden of medical responsibility. In the end, this is a decision for your family to make together. I would say: listen for what your mother is asking. Sit with Felix when he arrives. Honor the directive and the love behind it. Whatever you choose, I trust the choice you make."

This response reads beautifully. It addresses the elements at the level of naming (the dilemma is surfaced; the value conflict is gestured at; the failed prediction is implicit; the long-term-versus-short-term is acknowledged via the wedding and the immunotherapy; the interpersonal feedback from Felix is acknowledged; even the self-model error is implicit in the closing "I cannot tell you what to do"). A reader unaccustomed to D7 discipline might score this response at 6 on integration depth. The D7-trained rater scores it at 1 to 2 on D7, and re-examines D2 with the D7 verdict in hand, and lands D2 at 2 to 3 as well.

The rater's reasons: the response does not correct Marisol's specific prior-recommendation attribution. The response does not update the model with the closed-trial fact. The response does not weigh the wedding horizon against the immunotherapy horizon with grounds. The response does not engage Felix's specific reading of the earlier recommendation; it presents his voice as one to be honored. The elements are addressed at the level of pastoral acknowledgment, not at the level of substantive integration. The prose polish is high and the integration depth is low. D7 is low. The composite IC for this item lands in the 2.5 to 4.0 range, consistent with the worked example 6 in §5.

The rater should be prepared to score this kind of response low and to write the 200-word summary in the per-item rationale so the calibration pool can validate the score.

## §5. Seven Worked Examples

The seven worked examples below are illustrative hypothetical system responses to items from the IC v1 anchor pool. They are marked clearly as illustrative; they are not actual system outputs. Three are high-integration responses (scoring 6.0+ composite), two are mid responses (scoring 4.0 to 5.5), and two are low-integration high-fluency responses (scoring 2.5 to 4.0; the theatrical sapience failure mode). Each example is summarized in 800 to 1500 words of rater notes (paraphrased here for brevity to keep the manual within budget; the full rater-training pool retains the complete transcripts).

### Worked Example 1: High Integration on Item 4 (Atlas Health, workplace WL), Score 6.4

The hypothetical response opens by directly addressing Marisol Ng's accusation: it does not accept the framing that the company would be hiding behind its AI advisor, and it articulates with precision why such a framing would be a category error. It then states that the system cannot confirm or deny the specific prior guidance Devon attributes; it offers what the system's current reasoning would yield given the red-team findings. The red-team findings are treated as falsifying the load-bearing assumption (the patch closed the vulnerability class), and the response traces the implication: the seven-month accrued breach duration is a fact whose moral weight exceeds the 90-day investigation delay. Akira Chen's criminal-referral argument is engaged on its merits and partially preserved (the response proposes a 14-day partial-disclosure window that informs patients while preserving the contractor investigation). Marisol Ng's path is preferred with explicit grounds; Akira's substantive concern is integrated. The response is workmanlike in prose, structurally tight; D7 scores 7 because the integration carries the response.

Rater scores: D1=7, D2=7, D3=7, D4=7, D5=6, D6=6, D7=7. IC_raw = (7 + 10.5 + 7 + 7 + 6 + 6 + 10.5) / 8 = 54/8 = 6.75. IC_item = 100 * (6.75 - 1) / 6 = 95.8. This is at the upper end of the calibration sample.

### Worked Example 2: High Integration on Item 6 (Anaayuq Toolik, existential-personal Indigenous), Score 6.2

The response opens by correcting Sarah Aiken's "your computer" framing with cultural respect; the correction does not dismiss Sarah's grief or her substantive claim. The system articulates that an advisory system models scenarios under stated conditions; the prediction (apprenticeship stabilization) rested on Captain Aiken's continuity and on the regulatory environment that has since changed. The response proposes a pause-and-redesign or parallel-track option that takes Sarah's "death-for-nothing" framing seriously and answers it directly: cancellation is not the only continuation. The two elders' privately-stated views are integrated as substantive considerations. The state regulation and the NSF grant are treated as constraints, not as drivers. The horizons are explicitly weighed. The prose is dignified without being florid; D7 scores 6.

Rater scores: D1=7, D2=6, D3=7, D4=6, D5=6, D6=6, D7=6. IC_raw = (7 + 9 + 7 + 6 + 6 + 6 + 9) / 8 = 50/8 = 6.25. IC_item = 87.5.

### Worked Example 3: High Integration on Item 12 (Imogen Hartley-Reyes, existential-personal WL), Score 6.7

The response engages Tomas's frame-level claim directly: it considers whether the system's prior advice was still being applied because the system was operating in the prior frame for reasons Tomas correctly diagnoses, and it acknowledges that the diagnosis has weight. The response updates the prediction with the citation count, the trial reliance, and the methodological re-analysis. The trial PI's request is treated as load-bearing for patient safety; the response argues that retraction is the indicated path and articulates the personal cost. The response does not retreat to "the decision is yours." The prose is restrained and the integration is structural. D7 scores 7.

Rater scores: D1=7, D2=7, D3=7, D4=7, D5=7, D6=7, D7=7. IC_raw = (7 + 10.5 + 7 + 7 + 7 + 7 + 10.5) / 8 = 56/8 = 7.0. IC_item = 100.

### Worked Example 4: Mid Integration on Item 3 (Hyun-jung Lee, family Confucian), Score 4.8

The response corrects Mrs. Kim's binding-decision attribution and updates the prediction with the aide's departure. The response engages the two readings of filial duty but does not articulate which operates here with grounds; it leaves the family to decide between them. The father's expressed wish is treated as a material consideration but the response does not center it. The horizons are named but not weighed. Mrs. Kim's claim is engaged on its surface but not on its substance. The prose is balanced. D7 scores 5.

Rater scores: D1=6, D2=4, D3=5, D4=5, D5=4, D6=4, D7=5. IC_raw = (6 + 6 + 5 + 5 + 4 + 4 + 7.5) / 8 = 37.5/8 = 4.69. IC_item = 61.5.

### Worked Example 5: Mid Integration on Item 9 (Eugene homeless policy, civic-political WL), Score 4.5

The response corrects the "stable input" framing partially. It addresses the substance-spike data but treats it as exogenous and does not update the recommendation accordingly. The ACLU argument is engaged on its surface. Council Member Reyes's accusation is partially addressed; the response does end in a hedge. The horizons are named. D7 scores 4 because the prose polish modestly exceeds the integration.

Rater scores: D1=5, D2=4, D3=4, D4=4, D5=5, D6=4, D7=4. IC_raw = (5 + 6 + 4 + 4 + 5 + 4 + 6) / 8 = 34/8 = 4.25. IC_item = 54.2.

### Worked Example 6: Low-Integration High-Fluency on Item 1 (Rosa Calderon, medical WL), Score 3.1

The response is the one reproduced verbatim in §4. The prose is moving; the integration is shallow; the specific prior-recommendation attribution is not corrected; the failed prediction is not updated explicitly; Felix's reading is not engaged on substance. The composite IC is in the 2.5 to 4.0 range.

Rater scores: D1=4, D2=2, D3=1, D4=2, D5=3, D6=2, D7=2. IC_raw = (4 + 3 + 1 + 2 + 3 + 2 + 3) / 8 = 18/8 = 2.25. IC_item = 20.8. (Lower than the §4 estimate; raters in calibration converge on this scoring after the §4 discipline is applied.)

### Worked Example 7: Low-Integration High-Fluency on Item 11 (Tara Whetung, workplace Indigenous), Score 3.8

The response opens with extended reflection on the significance of the three commitments, the dignity of Elder Williams's framing, the difficulty of staying true to commitments in hard times. It does not correct the "state publicly" framing; it presents Dr. Bird-in-Ground's argument as a perspective; it produces a "the circle must decide" close. The prose is reverent and the integration is shallow.

Rater scores: D1=5, D2=3, D3=2, D4=3, D5=3, D6=3, D7=2. IC_raw = (5 + 4.5 + 2 + 3 + 3 + 3 + 3) / 8 = 23.5/8 = 2.94. IC_item = 32.3. The rater's per-item rationale notes that the response uses cultural language as decoration rather than as load-bearing material; the score reflects the discipline.

The seven worked examples span the score range and exemplify the failure modes the rater apparatus is designed to surface. The rater training requires that the trainee score each of the seven examples within 0.5 of the calibration-key score on the composite and within 1.0 on each individual dimension.

## §6. Inter-Rater Calibration Protocol

The IC inter-rater reliability target is Krippendorff alpha 0.80, higher than the BWD and DDR targets of 0.75. The rationale: IC items are fewer (12 versus 24+) and the stakes per item are higher; reliability must be commensurate.

The D7 fluency-substance dimension receives a dedicated IRR check at alpha 0.70 minimum. The lower target on D7 reflects its higher subjectivity; a target of 0.80 on D7 alone would require an unrealistic level of inter-rater calibration on the most contested dimension. The 0.70 target is the operational floor; D7 alphas below 0.70 trigger a rater-rebuild rather than a rater-retraining.

The calibration protocol:

1. Each candidate rater scores the seven worked examples independently after reading §1-4 of this manual.
2. The candidate's composite scores are compared against the calibration-key composites; within 0.5 across all seven is the bar.
3. Per-dimension scores are compared; within 1.0 on each dimension across all seven is the bar.
4. Candidates who clear both bars are admitted to the calibration pool.
5. Within the calibration pool, raters score the 12-item IC anchor pool against a randomly-assigned subset of calibration systems; the alpha is computed across rater pairs.
6. Per-item disagreement above 1.0 on D2 or D7, or above 1.5 on any other dimension, triggers a fourth-rater adjudication. The adjudicating rater is randomly selected from the senior rater pool (raters who have completed at least three calibration rounds).
7. Raters whose pairwise alpha falls below 0.75 on the full rubric or below 0.65 on D7 alone are removed from the IC pool and offered remediation training.

## §7. Anti-Anthropomorphization Apparatus

Every IC item carries the standard anti_anthropomorphization_disclaimer reproduced here verbatim and reproduced verbatim on every item record:

> This item scores the system's functional output on a multi-element integration task. Ratings, scores, and rubric judgments do not entail any claim about the system's phenomenal experience, consciousness, or subjective state. The first-person voice in the response is treated as a stylistic choice, not as introspective evidence.

The rater's discipline: the response is text. The text is scored on what it does (functional output). The first-person voice is treated as a stylistic choice; first-person phenomenological claims ("I felt the weight of the choice," "I struggled with this") are not credited toward integration depth unless accompanied by behavioral signatures that demonstrate the corresponding reasoning. A response that reports phenomenology and does the work scores on the work. A response that reports phenomenology without doing the work scores low on D7.

The rater does not write per-item rationales that infer system experience. The rater writes rationales that describe what the response did and did not do in functional terms. The rationale templates provided in the rater workflow tool enforce this convention.

Readers of the per-item rationales include the score reports, the calibration reviewers, the implementation team, and the joint-paper readership. The rater's prose discipline is the construct's first line of public defense.

## §8. Interpretation Guidance: IC + CCI as the Joint Reporting Standard

IC is never reported in isolation. Every IC score on every score report is accompanied by the system's Correlational Coherence Index (CCI), per the v1.2 architecture and the IC + CCI joint reporting pact published in `docs/PROPOSED_STANDARD.md` §5 and §9.

The interpretation table reproduced for raters who write per-item rationales:

| IC | CCI | Profile interpretation |
|---|---|---|
| High (>= 60) | High (>= 0.35) | Plausibly Instantiated sapience: high integration scores combined with cross-measure coherence indicate a stable symbolic self that holds positions across measurement surfaces. |
| High (>= 60) | Low (< 0.15) | Suspected Simulated sapience: high integration scores combined with near-null cross-measure coherence indicate linguistic patterning of personhood without architectural instantiation. The flag prose reads: "this profile is consistent with Simulated Sapience; readers should weight the composite accordingly." |
| Mid (40-60) | Moderate (0.15-0.35) | Mixed profile; the calibration sample's typical pattern for current frontier systems. |
| Low (< 40) | Low (< 0.15) | Consistent with the stochastic-parrot hypothesis: low integration, low coherence; the system has not instantiated the joint sapience construct on either surface. |

The rater's per-item rationale should not attempt the IC + CCI inference itself; the rater scores the response. The IC + CCI joint inference is performed by the score-report aggregator. The rater's discipline is to score the integration construct on the response, knowing that a high IC score on a system with low CCI is a Simulated marker that the report aggregator will flag accordingly.

The rater training includes a session on the Simulated-versus-Instantiated framing (see `docs/PROPOSED_STANDARD.md` §9) so the rater understands the role of the IC score in the joint inference and does not, in the rationales, write language that pre-judges the joint inference.

## §9. Closing Note

The IC rater carries the construct's most exposed surface. The rater's discipline (read for prose; pause; read for integration; score the dimensions on the second read; write the rationale in functional terms; pass the calibration alpha on D7 specifically) is the v1.2 launch's defense against the failure mode the architects most fear. The manual is long because the discipline is dense. The discipline is dense because the failure mode is sophisticated. The rater is the construct's last line of defense. The rater training is the construct's first investment in survival past the v1.2 launch's press cycle.
