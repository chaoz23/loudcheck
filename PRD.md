# PRD: LoudCheck — a standards-based loudness compliance verdict tool for agents

**Status:** Draft for handoff · **Type:** Open-source community project ·
**License intent:** MIT · **Build size:** ~2 days to v1

> **One line:** An agent-callable tool that measures a media file's loudness and
> true-peak against **formal published standards** (EBU R128, ATSC A/85) and returns
> a structured pass/fail verdict with the exact deltas — wrapping ffmpeg's
> `ebur128`/`loudnorm` analysis so an agent gets a compliance answer, not raw meter
> output it has to interpret. Deliberately excludes per-platform delivery templates,
> because that exclusion is what keeps maintenance near zero.

---

## Problem Statement

An AI agent in a post-production or media workflow can *run* ffmpeg to measure
loudness, but it cannot answer the question that actually matters — **"does this file
pass the spec?"** — because it doesn't know the target, the tolerance, or how to
interpret integrated loudness vs. loudness range vs. true-peak against a formal
standard. So loudness compliance, one of the most common causes of delivery
rejection, stays a manual, error-prone step. The agent either skips it (and a
non-compliant master ships) or dumps raw meter numbers on a human. The gap is not
measurement — ffmpeg measures fine — it is the **standards-aware verdict**.

## Background & prior art (why this is the right, and right-sized, gap)

- **ffmpeg is heavily wrapped but shallowly.** A dozen ffmpeg MCP servers exist; they
  expose trim/transcode/concat — operations an agent already brute-forces from a
  shell. Wrapping those adds nothing (fails the "beat brute force" test).
- **Loudness compliance is different:** it requires knowing the *standard's* target,
  tolerance, and gate, and interpreting multi-metric output against it. An agent
  cannot get that from a shell one-liner — it can get numbers, not a verdict. That's
  a genuine capability gap and a decisive brute-force margin.
- **The scoping trap that kills similar tools:** the commercially valuable version is
  a per-platform delivery checker (Netflix/DPP/Apple/Amazon templates). Those
  specs *change*, so that product is a yearly maintenance treadmill. This spec
  deliberately does **not** build that. It targets only **formal standards that
  essentially do not move** — EBU R128 and ATSC A/85 — which is what makes it a
  near-zero-maintenance community tool instead of a product with an upkeep tail.
- **Why it gets adopted:** rides the existing ffmpeg-in-every-media-agent reality and
  ships as an MCP tool; the verdict is the thing no existing ffmpeg wrapper provides.

## Goals

1. **Turn loudness measurement into a compliance verdict.** Return pass/fail against
   a named standard with per-metric deltas, not raw meter output. *Measure:* for a
   corpus of known-compliant and known-noncompliant files, verdict accuracy = 100%
   against a reference meter.
2. **Beat the brute-force baseline decisively.** One call returns the answer an agent
   would otherwise need multiple ffmpeg runs plus standards knowledge to assemble.
   *Measure:* median 1 tool call for a full verdict.
3. **Near-zero maintenance via scope discipline.** *Measure:* <1 week/year upkeep; no
   change required across a year of platform-spec churn, because platform specs are
   out of scope by design.
4. **Give the agent community a dependable primitive.** A stable, tested verdict tool
   other media-agent projects can call. *Measure:* referenced/imported by ≥1 other
   project; external contributions of additional *standards* (not platform templates).
5. **Actionable failure output.** Every fail states the exact correction needed
   (e.g. "-2.3 LU over target; apply -2.3 LU gain"). *Measure:* 100% of fails include
   a concrete delta and remediation.

## Non-Goals

1. **Per-platform delivery templates (Netflix, DPP, Apple TV+, Amazon, broadcaster
   specs).** This is the load-bearing non-goal. Those specs change and cover far more
   than loudness (codec, wrapper, colour, metadata). Including them converts a
   weekend tool into a yearly-maintenance product. Explicitly out. *(A downstream
   project could layer templates on top of this primitive — see P2.)*
2. **Loudness *correction* / normalization.** The tool measures and verdicts; it does
   not re-encode. An agent that wants to fix a file calls ffmpeg's `loudnorm`
   itself using the delta this tool provides. Keeps scope and liability tight.
3. **Full-file QC** (codec, resolution, colour space, cadence, PSE/flash). Different
   standards, different maintenance profile. Out.
4. **A GUI.** Consumer is an agent; output is JSON.
5. **Real-time / streaming loudness.** File-based analysis only.

## Target users

- **Primary: AI agents** in post-production, podcast, broadcast-prep, or
  content-delivery workflows, calling the tool via MCP.
- **Secondary: media-tooling maintainers** who want a vetted loudness-verdict
  primitive to embed rather than re-deriving standards logic.
- **Tertiary: editors/engineers** running agents who want a fast pre-flight loudness
  gate before delivery.

## User Stories

- As an **agent**, I want to call `check-loudness(file, standard="EBU_R128")` and get
  a pass/fail verdict with deltas so that I can gate a delivery without knowing the
  standard's internals.
- As an **agent**, on a fail I want the exact gain correction so that I can hand
  ffmpeg a precise `loudnorm` instruction in the next step.
- As an **agent**, I want the tool to name which metric failed (integrated loudness,
  LRA, or true-peak) so that I can report a specific cause, not "loudness bad."
- As a **media-tooling maintainer**, I want a stable, standards-only verdict tool so
  that I can build a platform-template layer on top without owning the measurement
  logic.
- As an **editor**, I want a one-call loudness pre-flight so that I catch the most
  common rejection cause before I deliver.

## Requirements

### Must-Have (P0) — the viable core

**P0.1 — Standards catalog (fixed, formal).** Ship EBU R128 (target −23 LUFS
integrated, and the R128 true-peak limit) and ATSC A/85 (−24 LKFS) as named,
built-in standards with their targets, tolerances, and gating defined as constants
citing the spec. *(These values are stable by nature — that's the whole thesis.)*
- *Acceptance:* Given `standard="EBU_R128"`, when a verdict runs, then it evaluates
  integrated loudness, loudness range, and true-peak against the R128 constants.

**P0.2 — Measurement via ffmpeg.** Wrap ffmpeg's `ebur128` / `loudnorm` analysis to
extract integrated loudness (LUFS/LKFS), loudness range (LRA), and true-peak (dBTP).
- *Acceptance:* Given a file, when measured, then integrated loudness, LRA, and
  true-peak are parsed correctly and match a reference meter within tolerance.

**P0.3 — Structured verdict output.** Return JSON: overall `pass|fail`, per-metric
measured value, target, tolerance, delta, and per-metric pass/fail.
- *Acceptance:* Given any file+standard, when checked, then the JSON contains every
  metric with measured/target/delta and a boolean, plus a top-level verdict.

**P0.4 — Actionable remediation on fail.** For integrated-loudness fails, include the
gain adjustment needed to reach target. For true-peak fails, state the overage.
- *Acceptance:* Given a file 2.3 LU over target, when it fails, then output states
  the −2.3 LU correction.

**P0.5 — Clean error handling.** Missing file, unreadable/no-audio stream, or ffmpeg
absent each return a specific `Error:`-prefixed message, never a raw trace.
- *Acceptance:* Given a video-only file, when checked, then it returns
  `"Error: no audio stream found"`.

**P0.6 — MCP tool + CLI, one engine.** Expose `check-loudness` as an MCP tool and a
CLI (`loudcheck file.wav --standard EBU_R128 --json`) over one core.
- *Acceptance:* Both surfaces return identical verdict JSON for the same input.

**P0.7 — Verification corpus.** Ship a small set of generated test tones/files at
known loudness (compliant and non-compliant) proving the verdict is correct.
- *Acceptance:* Given the corpus, when the suite runs, then every file's verdict
  matches its known-correct expectation.

### Nice-to-Have (P1) — fast follows

- **P1.1 — Additional formal standards** that are equally stable (e.g. an
  ITU-R BS.1770 base mode, or a documented streaming-baseline LUFS target that is a
  published standard rather than a moving platform template).
- **P1.2 — Per-stream / multi-track** loudness (check each audio track).
- **P1.3 — Momentary/short-term summary** (max momentary, max short-term) alongside
  integrated, for richer diagnostics.
- **P1.4 — Batch mode:** verdict a folder, return a table.

### Future Considerations (P2) — design for, don't build

- **P2.1 — Platform-template layer as a SEPARATE project** that consumes this tool's
  verdict primitive and adds Netflix/DPP/etc. targets. Kept out of this repo so the
  maintenance treadmill lives with whoever wants it. Design the standards catalog so
  a template is just a named set of targets pointing at the same engine.
- **P2.2 — Correction handoff:** emit a ready-to-run ffmpeg `loudnorm` command string
  (still not executing it) so an agent can one-shot the fix.

*Architectural insurance:* keep "standard definition" (targets/tolerances) fully
decoupled from "measurement engine," so P2.1 templates and P1.1 standards are data,
not code changes.

## Success Metrics

**Leading (days–weeks):**
- Verdict accuracy = 100% on the known-loudness corpus.
- Median tool calls per verdict = 1.
- 100% of fails include a concrete delta + remediation.
- Measurement matches a reference meter within a stated tolerance (define: e.g.
  ±0.5 LU integrated).

**Lagging (weeks–months):**
- Maintenance load <1 week/year (validates the scope-discipline thesis).
- External contributions of additional *standards* (not templates).
- Import/reference by ≥1 other media-agent project.
- Adoption: verdict calls in the wild via MCP.

## Open Questions

- **[engineering]** ffmpeg `loudnorm` (two-pass) vs. `ebur128` filter for the most
  accurate integrated + true-peak read in a single pass — which gives reference-meter
  agreement with the fewest ffmpeg invocations? *(Blocking for P0.2 accuracy target.)*
- **[engineering]** True-peak measurement: confirm ffmpeg's true-peak (oversampled
  dBTP) is spec-accurate for R128/A85, or whether a correction is needed. *(Blocking
  for P0.1 true-peak verdict.)*
- **[standards]** Exact R128 true-peak and gating constants and tolerance to encode —
  cite the current published spec text at build time to avoid transcription error.
- **[community]** Do we pin an ffmpeg minimum version (filter behavior can vary across
  ffmpeg releases)? Affects the "near-zero maintenance" claim — an ffmpeg change is
  the one realistic source of upkeep.
- **[scope]** Where exactly is the line between "formal standard" (in-scope) and
  "platform baseline that happens to be documented" (out-of-scope)? Write it down so
  P1.1 doesn't quietly reopen the maintenance treadmill.

## Timeline Considerations

- **No hard deadline** — community give-back.
- **Phasing:**
  - **v0.1 (the 2-day core):** P0.1–P0.7 with EBU R128 + ATSC A/85 only, MCP + CLI,
    verification corpus. This is the whole hackathon deliverable.
  - **v0.2:** P1 items (more formal standards, per-track, richer diagnostics, batch).
  - **separate project:** P2.1 platform templates, so this repo never inherits their
    churn.
- **Dependency:** ffmpeg present on the host (document the minimum version once P0.2
  is resolved).

## Scope guardrail (the spine of this product)

The single decision that makes LoudCheck a near-zero-maintenance community tool
rather than a yearly-maintenance product: **only formal, stable standards live in
this repo; per-platform delivery templates never do.** Enforce in review — if a PR
adds a target that a platform can change unilaterally, it belongs in the separate
template layer (P2.1), not here. The moment platform templates enter, the maintenance
thesis breaks. Guard it.

## Parking lot (good ideas, not in scope)

Loudness correction/normalization; codec/colour/cadence QC; PSE/flash checks;
platform delivery templates (→ separate project); real-time monitoring; a GUI.
