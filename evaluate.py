"""Measure classification accuracy against a small hand-labelled set.

    python evaluate.py --mock     # offline keyword rules
    python evaluate.py            # live model (needs OPENAI_API_KEY)
"""
import argparse
import json
import logging
import os
import sys

import triage


def evaluate(items, classify):
    cat_ok = pri_ok = 0
    misses = []
    for it in items:
        try:
            out = classify(it)
        except Exception as e:
            misses.append((it["id"], "error", str(e)))
            continue
        c = out["category"] == it["expected_category"]
        p = out["priority"] == it["expected_priority"]
        cat_ok += c
        pri_ok += p
        if not (c and p):
            misses.append((it["id"], f"got {out['category']}/{out['priority']}",
                           f"expected {it['expected_category']}/{it['expected_priority']}"))
    n = len(items)
    return {"n": n, "category_accuracy": cat_ok / n, "priority_accuracy": pri_ok / n, "misses": misses}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="data/labelled_tickets.json")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--model", default=os.environ.get("TRIAGE_MODEL", "gpt-4o-mini"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    with open(args.input, encoding="utf-8") as f:
        items = json.load(f)
    if args.mock:
        classify = triage.classify_mock
    else:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            print("OPENAI_API_KEY not set. Set it, or use --mock.")
            return 2
        classify = lambda t: triage.classify_llm(t, key, args.model)
    r = evaluate(items, classify)
    print(f"n={r['n']}  category accuracy={r['category_accuracy']:.0%}  priority accuracy={r['priority_accuracy']:.0%}")
    for m in r["misses"]:
        print("  miss:", *m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
