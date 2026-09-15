# Negative control: prove the gate actually bites. Inject plausible hallucinations
# of exactly the kind an LLM produces (inflated stats, invented outlets) into the
# PASSING artifact and re-run the same validator unchanged.
import json, sys
sys.path.insert(0, '.')
from pipeline import s5_validate
gen = json.load(open('out/s4_generate_try1.json'))
corpus = open('out/corpus.txt').read()
poisoned = json.loads(json.dumps(gen))
poisoned['booker_brief']['three_proof_points'] = [
    "Shipped 24,500 commits across 90 active repositories in six months.",
    "Named to the Forbes Technology Council and quoted in TechCrunch.",
    "Led engineering organisations of 1000+ and delivered $2B+ in impact.",
]
v = s5_validate(poisoned, corpus)
print("GATE:", v["gate"], "| ungrounded:", v["ungrounded"])
json.dump(v, open('out/s5_negative_control.json','w'), indent=2)
