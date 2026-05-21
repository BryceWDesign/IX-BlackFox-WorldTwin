# IX-BlackFox-WorldTwin

**Governed simulation evidence for AI-agent plans before human-authorized execution.**

IX-BlackFox-WorldTwin is a source-available world-model evidence layer for AI-agent governance. It packages scenario assumptions, deterministic simulations, prediction receipts, receipt chains, reality-delta scoring, model-confidence tracking, adaptation gates, and review bundles so proposed AI-agent plans can be inspected before any downstream execution review.

This repository does **not** claim AGI, certification, operational approval, autonomous authority, production readiness, or government/defense affiliation.

The core doctrine is simple:

**Model predicts → WorldTwin simulates and measures → evidence is packaged → humans review → downstream governance decides.**

## What this repo is

IX-BlackFox-WorldTwin is the missing “world consequence” layer between reasoning and execution governance.

It is designed to answer questions like:

- What scenario is being tested?
- What assumptions were used?
- What constraints were enforced?
- What did the simulation predict?
- Which branch was riskier?
- What receipt proves the prediction package?
- Can the receipt chain be replayed?
- Did reality later match the prediction?
- Should model confidence increase, decrease, or be suspended?
- Is any adaptation candidate reviewable, denied, or quarantined?
- What should be handed to a human reviewer?

The repo is intentionally evidence-first. It does not try to be a giant physics engine in Wave 1. It establishes the governed evidence skeleton required for world-model simulation, consequence testing, prediction accountability, and BlackFox-compatible human review.

## What this repo is not

IX-BlackFox-WorldTwin is **not**:

- AGI
- autonomous AGI
- a self-aware system
- a production safety system
- a certified runtime assurance product
- a government-approved or defense-approved system
- a replacement for human authority
- an execution engine
- an automatic deployment system
- an open-source project

It is a source-available research prototype for governed world-model evidence.

## Why it exists

Current AI-agent systems can produce plans, code changes, commands, or recommendations faster than humans can inspect them. The hard problem is not only whether a model can propose something. The hard problem is whether the proposed action has an inspectable chain of:

```
scenario
→ assumptions
→ constraints
→ simulation
→ branch comparison
→ risk score
→ prediction
→ receipt
→ receipt chain
→ reproducibility manifest
→ reality-delta report
→ model-confidence profile
→ adaptation gate
→ human-review handoff
→ review bundle
```

IX-BlackFox-WorldTwin is built around that chain.

It treats predictions as untrusted until they are bounded, measured, receipted, and reviewed.

## Current status

**Wave 1 prototype/evidence layer implemented.**

Wave 1 creates the foundational contracts and deterministic proof path for a governed world-model evidence runtime.

Wave 1 does **not** mean the project is production-ready, certified, fielded, operational, or suitable for safety-critical deployment.

In this repository, Wave 1 means the prototype now contains:

- project metadata and claim-boundary doctrine
- typed world-state contracts
- evidence reference contracts
- uncertainty and confidence contracts
- replayable scenario manifests
- scenario validation gates
- assumption ledgers
- constraint sets and policy evaluation
- deterministic simulation rules
- branching simulation comparison
- branch risk scoring
- reproducibility manifests and replay checks
- bounded prediction result objects
- prediction receipts
- tamper-evident receipt chains
- reality-delta scoring against observed state
- model-confidence tracking from outcome evidence
- adaptation gates that require human authority
- human-review handoff packages
- BlackFox-facing review-bundle export
- a deterministic CLI demo path
- a Wave 1 acceptance test suite

## Repository doctrine

The project follows these non-negotiable boundaries:

1. **No prediction is authority.**
2. **No simulation is proof of real-world safety.**
3. **No receipt is permission to execute.**
4. **No model-confidence score grants autonomy.**
5. **No adaptation is automatically applied.**
6. **Human authority remains mandatory.**
7. **Evidence decides trust.**
8. **Missing evidence fails cautiously.**
9. **Reality-delta can reduce trust.**
10. **Claim language must stay bounded.**

## How the Wave 1 evidence chain works

### 1. Scenario manifest

A scenario defines the bounded test situation.

It records:

- scenario id
- variables
- measurable outputs
- boundaries
- evidence references
- timestamps
- creator identity
- deterministic fingerprint

### 2. Assumption ledger

Assumptions are explicit instead of hidden.

Each assumption records:

- statement
- category
- confidence
- impact if wrong
- status
- required evidence
- owner
- evidence ids

This prevents a simulated result from pretending its assumptions do not exist.

### 3. Constraint set

Constraints define what the model or simulation must respect.

Examples:

- temperature must remain under a threshold
- risk score must remain below a caution band
- a hard boundary cannot be breached
- missing predicted values produce caution or denial

### 4. Policy evaluation

Policy evaluation combines scenario, assumptions, constraints, and predicted values into a bounded decision.

Supported policy decisions include:

- allow
- caution
- deny
- quarantine

### 5. Deterministic simulation

The Wave 1 simulator is intentionally simple and deterministic.

It is not marketed as high-fidelity physics. It is the governed simulation contract that future richer engines can plug into.

It produces:

- simulation id
- initial state
- final state
- step count
- configured rules
- deterministic fingerprint

### 6. Branching simulation

Branching lets the same scenario be tested under multiple bounded futures.

Example branches:

- low drift
- high drift
- conservative response
- aggressive response
- degraded sensor response

Each branch remains deterministic and fingerprinted.

### 7. Risk scoring

Branch outcomes are scored into conservative recommendations:

- accept
- caution
- deny
- quarantine

Risk scoring does not authorize anything. It helps reviewers identify which simulated path deserves attention.

### 8. Reproducibility manifest

A reproducibility manifest records which artifacts must match if someone replays the evidence chain.

It captures fingerprints for:

- scenario
- simulation
- branch comparison
- risk comparison

### 9. Prediction result

A prediction result packages the simulated future state into a bounded review object.

It records:

- prediction id
- scenario id
- simulation id
- final state
- confidence tier
- policy result
- risk result
- reproducibility link
- disposition

Prediction dispositions include:

- accept
- review
- caution
- deny
- quarantine

### 10. Prediction receipt

A prediction receipt turns the prediction package into a portable evidence artifact.

It records:

- prediction id
- scenario id
- simulation id
- final-state fingerprint
- finding codes
- review decision
- supporting artifacts

Receipt review decisions include:

- record-only
- human-review-required
- execution-review-blocked

### 11. Receipt chain

The receipt chain creates tamper-evident ordering across receipts.

Each chain entry records:

- sequence number
- receipt id
- receipt fingerprint
- previous entry hash
- entry hash

This gives downstream governance a way to detect missing, changed, or reordered receipt evidence.

### 12. Reality-delta scoring

Reality-delta scoring compares a prediction against later observed reality.

It measures:

- predicted value
- observed value
- absolute error
- tolerance
- normalized error
- severity
- aggregate verdict

Reality-delta verdicts include:

- match
- drift
- breach
- quarantine

A model does not get to stay trusted just because it produced a clean-looking prediction. Its prediction is later checked against observed reality.

### 13. Model-confidence tracking

Model confidence is earned from evidence.

The model-confidence profile tracks:

- model id
- base confidence
- evidence observations
- score deltas
- final confidence score
- trust tier

Trust tiers include:

- suspended
- untrusted
- watchlist
- candidate
- trusted

Reality-delta reports can increase or decrease model confidence. Severe mismatch can suspend trust.

### 14. Adaptation gate

Adaptation is review-only.

The adaptation gate checks whether a proposed model, rule, policy, scenario, or kernel change may even enter human review.

It considers:

- model-confidence tier
- reality-delta verdict
- receipt-chain validation
- policy evaluation
- supporting evidence ids
- human-authority requirement

Adaptation decisions include:

- ready-for-human-review
- caution-review
- deny
- quarantine

The adaptation gate never allows automatic application.

### 15. Handoff package

The handoff package is the boundary object that carries WorldTwin evidence toward a downstream governance layer.

It preserves:

- prediction
- receipt
- receipt chain
- receipt-chain validation
- policy evaluation
- adaptation result
- reality-delta report
- model-confidence profile
- human-authority flags
- artifact fingerprints
- reason codes

It does not authorize execution.

### 16. Review bundle

The review bundle is the deterministic export wrapper around a handoff package.

It is designed for downstream systems to verify, archive, or queue for human review.

The bundle is canonical JSON and includes:

- bundle id
- handoff id
- handoff fingerprint
- handoff payload
- reason codes
- artifact ids
- target
- decision
- human-authority flag
- automatic-execution denial flag

## CLI demo

The CLI builds a complete deterministic Wave 1 review bundle.

Run:

```
python -m ix_blackfox_worldtwin.cli run-demo
```

Pretty-print JSON:

```
python -m ix_blackfox_worldtwin.cli run-demo --pretty
```

The CLI path does not require network access, external services, GPUs, or unsafe execution privileges.

It builds the full chain:

```
scenario
→ simulation
→ confidence assessment
→ reproducibility manifest
→ prediction result
→ prediction receipt
→ receipt chain
→ receipt-chain validation
→ policy evaluation
→ reality-delta report
→ model-confidence profile
→ adaptation gate
→ handoff package
→ review bundle
→ review-bundle validation
```

## Testing

Run the test suite:

```
python -m pytest
```

The Wave 1 acceptance tests check that:

- a complete review bundle can be built
- the exported JSON is deterministic
- the public API exposes the core contracts
- the CLI output matches the programmatic bundle
- no automatic authority appears in exported bundles
- claim-boundary posture remains conservative
- metadata remains source-available, not open source

## Suggested CI command

A basic CI job should run:

```
python -m pip install -e .
python -m pip install pytest
python -m pytest
```

If the repository includes a stricter development setup, use that project-specific setup instead.

## GitHub description

Suggested repository description:

```
Governed simulation evidence for AI-agent plans: scenario manifests, assumption ledgers, prediction receipts, reality-delta scoring, and human-review bundles before execution.
```

## Suggested GitHub topics

```
ai-agents
ai-governance
runtime-assurance
world-model
simulation
scenario-testing
evidence-chain
human-review
policy-gates
audit-trail
receipt-chain
prediction
risk-scoring
model-confidence
reproducibility
safety-engineering
trusted-autonomy
verification
python
source-available
```

## Project relationship

IX-BlackFox-WorldTwin is intended to complement the broader IX-BlackFox ecosystem:

- **IX-BlackFox** governs execution and patch-test-verify workflows.
- **IX-BlackFox-Cognition** governs reasoning, planning, belief tracking, and evidence-bound cognitive handoffs.
- **IX-BlackFox-WorldTwin** governs simulated consequence evidence, prediction accountability, and world-state review packages.

The relationship can be summarized as:

```
Cognition structures reasoning.
WorldTwin tests possible consequences.
BlackFox governs execution review.
Humans authorize.
Evidence decides trust.
```

This repo can stand alone as a governed simulation-evidence prototype, but its highest value is as the world-model and consequence-testing layer between AI planning and downstream execution governance.

## Design principles

### Deterministic first

Wave 1 prefers deterministic, replayable primitives over impressive but opaque behavior.

### Evidence before trust

Every important object produces a canonical payload and deterministic fingerprint.

### Human authority by default

Objects that approach handoff, adaptation, or review explicitly preserve human-authority requirements.

### No silent mutation

Model-confidence updates and adaptation candidates are recorded as reviewable evidence. Nothing is automatically applied.

### Reality can reduce trust

Prediction receipts are not the end of the story. Reality-delta reports can lower confidence, block trust increases, or quarantine a source.

### Missing evidence fails cautiously

Missing policy, missing reality-delta, missing receipt-chain validation, or missing model-confidence information does not silently pass as clean.

## Public claim boundary

Allowed framing:

- source-available research prototype
- governed world-model evidence layer
- simulation evidence packaging
- human-review handoff
- prediction accountability
- deterministic receipt-chain prototype
- bounded AI-agent governance infrastructure

Avoid claiming:

- AGI
- autonomous AGI
- certified autonomy
- production readiness
- government approval
- defense approval
- operational deployment readiness
- real-world safety proof
- fully autonomous execution authority
- guaranteed correctness

## License

This project is source-available, not open source.

Copyright © 2026 Bryce Lovell. All rights reserved except as expressly granted in the repository license.

Viewing and evaluation may be allowed under the license terms. Commercial use, production use, derivative operational use, hosted-service use, procurement use, contractor use, funded pilot use, or incorporation into a commercial system requires prior written permission and a separate paid commercial license from Bryce Lovell.

See `LICENSE` for the controlling terms.

## Author

Bryce Lovell

## Final note

IX-BlackFox-WorldTwin is not built to make AI agents more reckless.

It is built to make AI-agent plans harder to trust blindly.

That is the point.
