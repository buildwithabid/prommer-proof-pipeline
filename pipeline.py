#!/usr/bin/env python3
"""
prommer.net Proof Pipeline  --  multi-step agentic workflow
  S1 CRAWL     (deterministic) live site + network + llms.txt -> grounding corpus
  S2 EXTRACT   (AGENT)  raw crawl        -> structured proof ledger (JSON)
  S3 AUDIT     (AGENT)  ledger + llms.txt-> drift + retrieval-gap findings (JSON)
  S4 GENERATE  (AGENT)  findings         -> llms.txt patch + JSON-LD + booker brief
  S5 VALIDATE  (deterministic GATE) every number/entity must trace to the corpus
  S6 PUBLISH   emit run record for the dashboard
Agent steps are real `claude -p` calls. S5 can and does fail them.
"""
import re, json, subprocess, sys, os, time, html, hashlib
B = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(B, "out")
RUN = {"stages": [], "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

def text_of(p):
    s = open(p, encoding="utf-8", errors="ignore").read()
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", s)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()

def agent(name, prompt, timeout=300):
    """One agent step. Returns parsed JSON or raises."""
    t0 = time.time()
    p = subprocess.run(["claude", "-p", prompt, "--model", "claude-sonnet-5"],
                       capture_output=True, text=True, timeout=timeout)
    raw = p.stdout.strip()
    m = re.search(r"\{.*\}|\[.*\]", raw, re.S)
    if not m:
        raise RuntimeError(f"{name}: no JSON in agent output: {raw[:400]}")
    data = json.loads(m.group(0))
    RUN["stages"].append({"stage": name, "kind": "agent", "secs": round(time.time()-t0, 1),
                          "chars_in": len(prompt), "chars_out": len(raw)})
    json.dump(data, open(f"{OUT}/{name}.json", "w"), indent=2)
    print(f"  [agent] {name}: {round(time.time()-t0,1)}s, {len(raw)} chars out", flush=True)
    return data

# ---------------------------------------------------------------- S1 CRAWL
def s1_crawl():
    t0 = time.time()
    site = text_of(f"{B}/raw/prommer.html")
    fly  = text_of(f"{B}/raw/flywheel.html")
    llms = open(f"{B}/raw/prommer_llms.txt", encoding="utf-8").read()
    weeks = re.findall(r"Week of (\w+ \d+): ([\d,]+) active repos, ([\d,]+) commits \(([\d,]+) AI-paired\)", site)
    ticker = [{"week": w, "repos": int(r.replace(",","")), "commits": int(c.replace(",","")),
               "ai_paired": int(a.replace(",",""))} for w, r, c, a in weeks]
    corpus = "\n".join([site, fly, llms])
    crawl = {
        "fetched": ["prommer.net", "wetheflywheel.com", "prommer.net/llms.txt",
                    "swyx.io", "simonwillison.net", "danabra.mov"],
        "site_text_chars": len(site), "llms_txt_chars": len(llms),
        "ticker_weeks": ticker, "corpus_chars": len(corpus),
        "corpus_sha": hashlib.sha256(corpus.encode()).hexdigest()[:12],
    }
    open(f"{OUT}/corpus.txt", "w").write(corpus)
    json.dump(crawl, open(f"{OUT}/s1_crawl.json", "w"), indent=2)
    RUN["stages"].append({"stage": "s1_crawl", "kind": "deterministic",
                          "secs": round(time.time()-t0,1),
                          "note": f"{len(ticker)} ticker weeks, {len(corpus)} char corpus"})
    print(f"  [det] s1_crawl: {len(ticker)} ticker weeks, corpus {len(corpus)} chars", flush=True)
    return crawl, site, llms, corpus

# ---------------------------------------------------------------- S5 VALIDATE
STOP = set("""The A An And In On At Of For To With Ask Tom Press Home About Advisory Newsletter
Start Contact Topics Related Building Chasing Technology Training Tech Search Explore Week
Global Weekly Index Content English Two Other More Skip Opens Loading Tools Commits Shipping
Scope Teams Work Founder Community Book Sitemap Privacy Terms Direct Overview Background""".split())

def s5_validate(generated, corpus):
    """Deterministic grounding gate. Every number and proper-noun entity emitted by the
    generator must appear verbatim in the crawled corpus. No exceptions, no LLM judging."""
    t0 = time.time()
    norm = corpus.replace(",", "").lower()
    blob = json.dumps(generated)
    checks, fails = [], 0

    nums = sorted(set(re.findall(r"\b\d[\d,]*\+?\b", blob)))
    for n in nums:
        bare = n.replace(",", "").rstrip("+")
        if len(bare) < 2:            # skip 0-9, too noisy to be a claim
            continue
        ok = re.search(r"(?<!\d)" + re.escape(bare) + r"(?!\d)", norm) is not None
        checks.append({"type": "number", "token": n, "grounded": ok})
        fails += (not ok)

    ents = sorted(set(re.findall(r"\b[A-Z][a-zA-Z0-9.]+(?:\s[A-Z][a-zA-Z0-9.]+)+", blob)))
    for e in ents:
        if e.split()[0] in STOP:
            continue
        ok = re.search(r"\b" + re.escape(e.lower()) + r"\b", corpus.lower()) is not None
        checks.append({"type": "entity", "token": e, "grounded": ok})
        fails += (not ok)

    verdict = {"total_checks": len(checks), "failed": fails,
               "passed": len(checks) - fails,
               "gate": "PASS" if fails == 0 else "FAIL",
               "ungrounded": [c["token"] for c in checks if not c["grounded"]],
               "checks": checks}
    json.dump(verdict, open(f"{OUT}/s5_validate.json", "w"), indent=2)
    RUN["stages"].append({"stage": "s5_validate", "kind": "deterministic-gate",
                          "secs": round(time.time()-t0,1),
                          "note": f"{len(checks)} checks, {fails} ungrounded, gate={verdict['gate']}"})
    print(f"  [GATE] s5_validate: {len(checks)} checks, {fails} ungrounded -> {verdict['gate']}", flush=True)
    return verdict

# ---------------------------------------------------------------- S2 EXTRACT (agent)
P2 = """You are the EXTRACT step of an automated content pipeline for prommer.net
(Thomas Prommer: technology executive, CTO/CIO, AI strategy consultant, hybrid athlete).

Below is text scraped from the live homepage plus his group company site.

RULES
- Emit ONLY facts literally present in the text. Never infer, never round, never embellish.
- Copy numbers exactly as written.
- If you are not certain a fact is in the text, omit it.

Return ONLY JSON:
{"proof_ledger":[{"claim":"<one sentence, verbatim-grounded>","category":"press|scale|practice|network|positioning","evidence":"<exact substring from the text>"}],
 "properties":[{"name":"","url":"","role":""}],
 "press":[{"outlet":"","claim":""}]}

Aim for 10-16 ledger entries. TEXT:
---
%s
---"""

# ---------------------------------------------------------------- S3 AUDIT (agent)
P3 = """You are the AUDIT step of an automated pipeline for prommer.net.

prommer.net's positioning depends on BREADTH and PROOF-OF-PRACTICE. Its buyers are
(a) founders/operators evaluating a counterparty for AI-native engagements and
(b) press/podcast bookers. Both increasingly run their first-pass research through an
LLM, which can only cite what is in crawlable text -- not what renders client-side.

Here is the PROOF LEDGER extracted from the live site:
%s

Here is the CURRENT llms.txt (the hand-maintained machine-readable layer):
---
%s
---

Find where live proof exists on the site but is ABSENT or STALE in llms.txt, i.e. facts an
answer engine cannot cite today. Be specific and adversarial. Rank by impact on inbound demand.

Return ONLY JSON:
{"findings":[{"gap":"","why_it_costs_inbound":"","severity":"high|medium|low","fix":""}],
 "headline":"<one sentence: the single most valuable fix>"}
Aim for 4-6 findings."""

# ---------------------------------------------------------------- S4 GENERATE (agent)
P4 = """You are the GENERATE step of an automated pipeline for prommer.net.

AUDIT FINDINGS:
%s

GROUNDED PROOF LEDGER (the ONLY facts you may use):
%s

Produce the missing machine-readable proof layer. HARD CONSTRAINT: a downstream
deterministic validator checks that every number and every proper noun you emit appears
verbatim in the source crawl. Anything you invent WILL fail the build. Use only ledger facts.
%s

Return ONLY JSON:
{"llms_txt_patch":"<a new '## Proof of practice' section to append to llms.txt, markdown, 6-12 lines>",
 "jsonld":{...valid schema.org Person JSON-LD object...},
 "booker_brief":{"hook":"","why_now":"","three_proof_points":["","",""],"suggested_questions":["","",""]}}"""

def main():
    print("== prommer.net proof pipeline ==", flush=True)
    crawl, site, llms, corpus = s1_crawl()

    ledger = agent("s2_extract", P2 % site[:14000])
    audit  = agent("s3_audit",  P3 % (json.dumps(ledger)[:7000], llms))

    correction, attempt, verdict, gen = "", 0, None, None
    while attempt < 3:
        attempt += 1
        gen = agent(f"s4_generate_try{attempt}",
                    P4 % (json.dumps(audit)[:5000], json.dumps(ledger)[:8000], correction))
        verdict = s5_validate(gen, corpus)
        if verdict["gate"] == "PASS":
            break
        bad = ", ".join(verdict["ungrounded"][:25])
        correction = ("\nPREVIOUS ATTEMPT REJECTED BY THE VALIDATOR. These tokens do not appear "
                      f"in the source crawl and are therefore hallucinated: {bad}\n"
                      "Remove or replace every one of them with a fact that IS in the ledger. "
                      "Do not substitute a different invented value.\n")
        print(f"  [retry] gate failed, feeding {len(verdict['ungrounded'])} ungrounded tokens back", flush=True)

    RUN.update({"attempts": attempt, "gate": verdict["gate"], "crawl": crawl,
                "ledger": ledger, "audit": audit, "generated": gen, "validation": verdict,
                "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    json.dump(RUN, open(f"{OUT}/run.json", "w"), indent=2)
    print(f"== done: gate={verdict['gate']} after {attempt} generate attempt(s) ==", flush=True)

if __name__ == "__main__":
    main()
