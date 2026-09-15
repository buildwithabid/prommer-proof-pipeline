# prommer.net Proof Pipeline

A six-stage agentic workflow that audits [prommer.net](https://prommer.net)'s machine-readable
layer against its own live page, and refuses to publish any claim it can't trace back to source.

**Live run report → https://buildwithabid.github.io/prommer-proof-pipeline/**

Built as a timed submission for the We The Flywheel Sr Agentic Engineer test.

## The finding

prommer.net already ships a good hand-written `llms.txt`. What it doesn't ship is its single
strongest AI-native credential: the homepage shipping ticker — **19,977 commits in six months,
69% paired with a coding agent, across 124 repos**. That's the number that substantiates
"AI-native, agentic-led", and it exists nowhere an answer engine can cite it.

## Stages

| # | Stage | Kind | Time | Output |
|---|-------|------|------|--------|
| 01 | CRAWL | deterministic | 0.0s | 26 ticker weeks, 23,798-char frozen corpus (`sha e6d0c0637420`) |
| 02 | EXTRACT | **agent** | 21.3s | 16-entry proof ledger, each claim carrying its source substring |
| 03 | AUDIT | **agent** | 35.7s | 6 gaps vs live `llms.txt`, 3 rated high |
| 04 | GENERATE | **agent** | 80.3s | `llms.txt` patch + schema.org Person + booker brief |
| 05 | VALIDATE | deterministic **gate** | 0.0s | 25 checks, 0 ungrounded → PASS |
| 06 | PUBLISH | deterministic | — | `out/run.json` |

Agent steps are real `claude -p` calls. Stage 05 is the one allowed to say no: every number and
proper noun in the generated output must appear verbatim in the frozen corpus, or the offending
tokens are fed back to stage 04 and it regenerates, up to 3 attempts.

## Proving the gate bites

A validator that passes everything is decoration. `negcontrol.py` takes the passing artifact,
injects the hallucinations an LLM most plausibly produces here, and re-runs the same validator:

```
$ python3 negcontrol.py
  [GATE] s5_validate: 28 checks, 2 ungrounded -> FAIL
GATE: FAIL | ungrounded: ['24,500', 'Forbes Technology Council']
```

The decoy — "1000+ engineers led, $2B+ impact" — correctly passes, because it's genuinely on the
page. The gate rejects fabrication, not confidence.

## Known weaknesses

- Entity checking only catches multi-word proper nouns. The negative control caught
  `Forbes Technology Council` but missed a bare `TechCrunch`. Not fixed.
- Grounding is verbatim string matching: it proves a number came from the page, not that the page
  is right. Fabrication gate, not a truth gate.
- Stage 01 reads server-rendered HTML. The ticker only parsed because its values ship in the
  markup; a fully client-rendered widget would need a headless browser.
- Stage 03's severity ranking is model judgement and is not gated.

## Run it

```bash
python3 pipeline.py      # full run, 3 agent calls
python3 negcontrol.py    # prove the gate fails when it should
```

Stdlib only. Requires the `claude` CLI on PATH. Raw crawl inputs and every intermediate
output are committed under `out/` so the run is reproducible and auditable.
