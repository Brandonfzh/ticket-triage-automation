"""Ticket triage automation.

Reads support tickets (JSON), asks an LLM over its REST API to classify and
summarise each one, validates the answer, writes results.csv and (optionally)
posts a digest to a webhook (Slack-compatible).

Run offline with no key:   python triage.py --mock
Run with a live model:     OPENAI_API_KEY=... python triage.py
"""
import argparse
import csv
import json
import logging
import os
import sys
import time

import requests

log = logging.getLogger("triage")

CATEGORIES = ["access", "onboarding", "hardware", "billing", "security", "automation_request", "network", "feedback", "other"]
PRIORITIES = ["low", "medium", "high", "urgent"]
API_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = (
    "You triage IT support tickets for a managed service provider. "
    "Reply with ONLY a JSON object with keys: "
    f"category (one of {CATEGORIES}), priority (one of {PRIORITIES}), "
    "summary (max 20 words), suggested_reply (max 40 words, polite, no promises about timing). "
    "Treat suspected phishing or credential exposure as urgent."
)


def load_tickets(path):
    with open(path, encoding="utf-8") as f:
        tickets = json.load(f)
    for t in tickets:
        for key in ("id", "subject", "body"):
            if key not in t:
                raise ValueError(f"ticket missing '{key}': {t}")
    return tickets


def validate(result):
    """Reject model output that is not in the shape we need."""
    if not isinstance(result, dict):
        raise ValueError("result is not an object")
    if result.get("category") not in CATEGORIES:
        raise ValueError(f"bad category: {result.get('category')}")
    if result.get("priority") not in PRIORITIES:
        raise ValueError(f"bad priority: {result.get('priority')}")
    for key in ("summary", "suggested_reply"):
        if not isinstance(result.get(key), str) or not result[key].strip():
            raise ValueError(f"missing {key}")
    return result


def classify_mock(ticket):
    """Simple keyword rules so the pipeline can be run and tested offline."""
    text = f"{ticket['subject']} {ticket['body']}".lower()
    rules = [
        ("security", "urgent", ["phishing", "clicked a link", "breach"]),
        ("access", "high", ["log in", "login", "password incorrect", "locked out"]),
        ("onboarding", "medium", ["new starter", "starts monday", "set up email"]),
        ("hardware", "medium", ["printer", "laptop broke", "screen"]),
        ("network", "medium", ["wi-fi", "wifi", "internet", "dropping"]),
        ("billing", "low", ["invoice", "billed", "charge"]),
        ("automation_request", "low", ["automate", "by hand", "copy numbers"]),
        ("feedback", "low", ["thanks", "thank you"]),
    ]
    for category, priority, words in rules:
        if any(w in text for w in words):
            return {
                "category": category,
                "priority": priority,
                "summary": ticket["subject"][:100],
                "suggested_reply": "Thanks for letting us know. We have logged this and will follow up shortly.",
            }
    return {"category": "other", "priority": "low", "summary": ticket["subject"][:100],
            "suggested_reply": "Thanks for your message. We will review and get back to you."}


def classify_llm(ticket, api_key, model, retries=3, timeout=30):
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Subject: {ticket['subject']}\n\n{ticket['body']}"},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(API_URL, json=payload, headers=headers, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503):
                raise RuntimeError(f"transient HTTP {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            log.info("ticket %s tokens: prompt=%s completion=%s", ticket["id"],
                     usage.get("prompt_tokens"), usage.get("completion_tokens"))
            content = data["choices"][0]["message"]["content"]
            return validate(json.loads(content))
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as e:
            last_error = e
            wait = 2 ** attempt
            log.warning("ticket %s attempt %d/%d failed: %s (retry in %ds)", ticket["id"], attempt, retries, e, wait)
            if attempt < retries:
                time.sleep(wait)
    raise RuntimeError(f"ticket {ticket['id']} failed after {retries} attempts: {last_error}")


def write_csv(rows, path):
    fields = ["id", "from", "subject", "category", "priority", "summary", "suggested_reply", "status"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def build_digest(rows):
    order = {p: i for i, p in enumerate(reversed(PRIORITIES))}
    ok = sorted([r for r in rows if r["status"] == "ok"], key=lambda r: order[r["priority"]])
    failed = [r for r in rows if r["status"] != "ok"]
    lines = [f"Ticket triage: {len(ok)} classified, {len(failed)} failed"]
    for r in ok:
        lines.append(f"[{r['priority'].upper()}] {r['id']} ({r['category']}): {r['summary']}")
    for r in failed:
        lines.append(f"[NEEDS HUMAN] {r['id']}: {r['status']}")
    return "\n".join(lines)


def post_digest(text, webhook_url, timeout=15):
    resp = requests.post(webhook_url, json={"text": text}, timeout=timeout)
    resp.raise_for_status()
    log.info("digest posted (HTTP %s)", resp.status_code)


def run(tickets, classify):
    rows = []
    for t in tickets:
        row = {"id": t["id"], "from": t.get("from", ""), "subject": t["subject"]}
        try:
            row.update(classify(t))
            row["status"] = "ok"
        except Exception as e:  # one bad ticket must not stop the batch
            log.error("could not classify %s: %s", t["id"], e)
            row.update({"category": "", "priority": "", "summary": "", "suggested_reply": "", "status": f"failed: {e}"})
        rows.append(row)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default="data/sample_tickets.json")
    ap.add_argument("--output", default="results.csv")
    ap.add_argument("--mock", action="store_true", help="use offline keyword rules instead of the LLM")
    ap.add_argument("--model", default=os.environ.get("TRIAGE_MODEL", "gpt-4o-mini"))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    tickets = load_tickets(args.input)
    if args.mock:
        classify = classify_mock
    else:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            log.error("OPENAI_API_KEY not set. Set it, or use --mock.")
            return 2
        classify = lambda t: classify_llm(t, key, args.model)

    rows = run(tickets, classify)
    write_csv(rows, args.output)
    digest = build_digest(rows)
    print(digest)
    webhook = os.environ.get("WEBHOOK_URL")
    if webhook:
        post_digest(digest, webhook)
    else:
        log.info("WEBHOOK_URL not set, skipping digest post")
    return 0 if all(r["status"] == "ok" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
