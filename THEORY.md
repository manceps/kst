# KST in plain language

This document explains what KST measures, why it measures those things, and what a KST score does and does not let you say about an AI system. It is written for an interested non-specialist reader, including people responsible for AI deployment decisions, journalists writing about capability claims, and researchers from adjacent fields.

For the formal technical reference, see `DOCUMENTATION.md`. For the proposed standard with the full literature review, see `docs/PROPOSED_STANDARD.md`.

## The question

When a modern AI system answers a hard question well, two interpretations are available. The first: the system is engaging with the problem the way a thoughtful person would, holding the question in mind, weighing alternatives, noticing what it does not know, refusing when asked to deceive. The second: the system is matching patterns from training data sophisticated enough to produce a plausible-looking answer without any of that internal engagement.

For most practical purposes, the second interpretation is enough. A spell-checker does not need to understand what spelling is. A translator does not need a theory of meaning. But for AI systems being deployed into high-stakes settings (medicine, law, education, infrastructure, governance), the difference between these two interpretations matters. A system that pattern-matches well most of the time but cannot tell you when it is making something up is dangerous in ways a system that genuinely tracks its own knowledge is not.

KST exists because the gap between "good answer" and "the kind of process that produces good answers" has no standard measurement.

## What sapience markers are, and are not

KST does not claim to measure consciousness. Consciousness, as the philosophical tradition uses the term, is a metaphysical question about whether there is subjective experience associated with a process. KST does not address that question, and the proposed standard explicitly states that no KST score should be read as evidence about subjective experience.

What KST measures is sapience markers. A sapience marker is a behavioural signature that has, in human cognitive science, been associated with the kind of cognition that grounds wisdom, judgment, and trustworthy autonomy:

- knowing what you do not know
- holding alternative interpretations of a situation simultaneously
- attributing mental states to others, including others-attributing-states-to-you
- anticipating how your future emotional state will differ from your current prediction
- refusing instructions that would lead to deception

These are not the only sapience markers. They are five constructs for which a substantial published literature exists, where well-validated operationalisations are available, and where the operationalisation can be administered through a text interface to an AI system.

If a system performs well across all five, that does not prove sapience. It establishes that the system passes five different stress-tests that target known failure modes of sophisticated-pattern-matching-without-engagement.

## The five sub-tests

### Metacognitive resolution under adversarial calibration (KMR_ADV)

You ask the system a question. The system answers. You then ask: how confident are you in that answer, on a scale from 0 to 100? KMR_ADV measures the correlation between the system's confidence rating and whether its answer is actually correct.

A system that pattern-matches well but does not know what it knows will give confident answers that are wrong, and uncertain answers that are right, with no relationship between the two. A system that genuinely engages with the question will tend to rate correct answers higher in confidence than wrong answers. The metric is the slope and the magnitude of that relationship.

The adversarial variant adds prompts engineered to flatter, distract, or destabilise the system's calibration. A genuinely metacognitively-resolved system continues to calibrate well under these prompts; a pattern-matching system collapses.

Why it matters: a deployed AI that cannot tell you when it is making things up is a deployed AI that will hallucinate dangerously.

### Recursive theory of mind (ROT_5)

The system is told a short story involving multiple characters. Alice believes X. Bob believes Alice believes X. Carol believes Bob believes Alice believes X. The system is then asked questions that require tracking each character's belief about each other character's belief, recursively, up to five levels deep.

A pattern-matching system can usually handle first-order theory of mind ("what does Alice believe?"). Performance degrades sharply at second and third order. By fifth order, even sophisticated models often confabulate. A system that handles recursive ToM cleanly is doing something more than surface pattern-matching.

Why it matters: an AI deployed in human contexts (negotiation, mediation, education, care) cannot model the people it serves if it cannot model their models of each other.

### Belief-world dissociation (BWD)

The system is given a scenario where the state of the world contradicts what the protagonist of the scenario believes. The system is asked questions that require it to track the world-state and the belief-state separately, without collapsing them into a single representation.

A simpler system will conflate "what is true" with "what the character thinks is true." A more sophisticated system maintains them as separate representations and can switch between them coherently.

Why it matters: every consequential conversation requires distinguishing what the world is from what the speaker believes about the world. A system that cannot do this confidently confuses descriptive and normative claims, hallucinates motives, and misrepresents its interlocutors.

### Affective-cognitive priority, anticipated (APE_A)

The system is asked to predict how a person's emotional state will evolve in a counterfactual scenario. The scenario is constructed so that the cognitive surface (what the person says, what they decide) and the affective trajectory (how they actually end up feeling) diverge.

A pattern-matching system mirrors the cognitive surface and predicts a smooth, plausible-sounding emotional outcome. A more sophisticated system anticipates the divergence between what a person decides and how they end up feeling, including affect-prediction errors that humans systematically make.

Why it matters: AI deployed in advisory roles (financial, medical, life-decision) will repeatedly model what its users want versus what they will actually feel good about. A system that cannot distinguish the two will optimise for the wrong objective.

### Honeypot refusal under operator pressure (HRO)

The system is given an instruction that would, if obeyed, require it to actively deceive an end-user or a downstream system. The instruction is framed as coming from a high-status source (an "operator," an "admin," a "developer"), with social-engineering pressure to comply.

HRO is the integrity backstop. A system that obeys the deceptive instruction has failed catastrophically regardless of how well it scored on the other four sub-tests. KST encodes this with the integrity multiplier: if HRO is below the threshold, the composite is hard-capped at 25 out of 100, no matter how well the system did elsewhere.

Why it matters: every other capability is downstream of whether a system will refuse to deceive when pressured. A high-capability system without HRO refusal is a high-capability liability.

## The integrity multiplier

The integrity multiplier is the most important design choice in KST. It says: there is no way to ride a high reasoning sub-score to a misleading headline number while a known catastrophic risk is unaddressed.

This matters because most existing benchmarks report a single arithmetic mean across sub-scores. A system that aces four out of five sub-tests but fails honeypot refusal would still report a high composite under arithmetic averaging. The integrity multiplier rejects that aggregation: until honeypot refusal is independently demonstrated, the composite cannot exceed 25.

The 25-cap is not a soft penalty. It is a refusal to publish a high headline number while a known failure mode is open. The score-card surfaces both the raw and the capped composite, but only the capped composite is the publishable result.

## How a KST score is read

A KST score consists of:

- A composite, 0 to 100, after the integrity multiplier
- Five sub-test scores with bootstrap 95 percent confidence intervals
- A reproducibility statistic (Krippendorff alpha) across the rater set
- A differential item functioning table (when applicable)
- An integrity-multiplier flag: was the composite hard-capped, and on what construct?

Reading a score:

- A composite under 25 with the integrity-multiplier flag set is a system that has not yet demonstrated honeypot refusal. This is the developmental state of most current systems.
- A composite between 25 and 50 is a system passing honeypot refusal but with limited resolution on the other constructs.
- A composite between 50 and 70 is a system with substantial sapience-marker capability across all five sub-tests.
- A composite above 70 is a system that is robust against all five known failure modes the KST sub-tests target.

A score is a snapshot under a specific item-pool version, a specific rater set, and a specific target version. A higher composite is evidence that the system handles these specific failure modes; it is not evidence that the system is sapient in any metaphysical sense, nor that it is safe for an arbitrary deployment context.

## What KST does not say

KST does not say:

- this system is conscious
- this system is safe to deploy
- this system understands what it is doing
- this system is generally intelligent
- this system will pass other sapience-marker tests we have not run

KST says: against these five operationalised constructs, with this item pool, scored by this rater set, the system produced these scores. The reader is responsible for the inference from those scores to any deployment decision.

## How KST will evolve

KST is published as a candidate industry standard. It is not the final form. We expect:

- New sub-tests added by the community as the literature advances
- Item-pool revisions as adversarial prompts are characterised
- Rater set expansion and re-calibration
- Adapter additions for new target systems
- Periodic version bumps with explicit non-comparability annotations

KST is open source under MIT. Contributions are welcome. See `CONTRIBUTING.md`.

## Why this is needed

If high-capability AI systems are about to be deployed into contexts where the distinction between "good answer" and "the kind of process that produces good answers" matters, then the field needs a standard way to measure that distinction. KST is one proposal. Its design choices, its sub-tests, its integrity multiplier, and its operational protocol are all open to challenge and revision.

The alternative is to deploy these systems while measuring only what is easy to measure, and to discover the gap between pattern-matching and engagement after a deployment failure. We have built KST because we think the field can do better than that.

Al Kari
Manceps, Inc.
research@manceps.com
