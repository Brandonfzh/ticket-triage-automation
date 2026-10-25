# Ticket Triage Automation

A small Python tool that takes support tickets, asks an LLM (over its REST API) to classify and summarise each one, validates the answer, saves a CSV and posts a priority-sorted digest to a webhook such as Slack.

I built it as a personal project to practise the kind of work a client-embedded engineer does: take messy real-world input, wire it to an API, handle failures properly and leave documentation so someone else can maintain it. All tickets in `data/` are made up.

## What it does

1. Loads tickets from JSON (`data/sample_tickets.json`, 8 invented examples).
2. For each ticket, calls the OpenAI chat completions REST endpoint and asks for JSON: category, priority, 20-word summary and a suggested reply.
3. Validates the model output against allowed categories and priorities. Anything malformed is rejected and retried.
4. Retries transient failures (HTTP 429/5xx, timeouts) with exponential backoff.
5. One bad ticket never stops the batch; it is marked `failed` and flagged as needing a human.
6. Writes `results.csv` and prints a digest sorted urgent first. If `WEBHOOK_URL` is set, posts the digest there.

## Run it

```
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python triage.py --mock                              # offline, keyword rules, no key needed
export OPENAI_API_KEY=...                            # your own key; never commit it
export WEBHOOK_URL=...                               # optional, Slack-compatible incoming webhook
python triage.py                                     # live model
pytest                                               # unit tests (network mocked)
python evaluate.py [--mock]                          # accuracy on 12 hand-labelled tickets
```

## Measuring accuracy

`evaluate.py` runs the classifier over `data/labelled_tickets.json` (12 tickets I labelled by hand) and prints category and priority accuracy plus the misses. The set is small, so treat the number as a sanity check, not proof. Offline mock mode scores about 83%, and misses the tickets its keyword rules were not written for, which is the point of having a held-out check. Live-model accuracy: not yet measured. The live API path is implemented and its retry and validation logic is unit tested with mocked responses, but I have not yet run it against the real service.

## Design decisions

- **Validate model output.** Models sometimes return wrong shapes or invented categories. `validate()` is the gate, and the tests cover it.
- **Fail soft.** In a real engagement one bad record shouldn't block the rest, but it should be visible. Failures appear in the CSV and the digest.
- **Mock mode.** Lets the pipeline be demonstrated and tested without a key or network. It uses crude keyword rules and is not a substitute for the model.
- **Phishing is urgent.** The prompt and mock rules treat suspected credential exposure as top priority.

## Limitations

- Prototype only: no real ticketing system integration, no auth beyond an API key, no persistence beyond CSV.
- Sample data is synthetic; accuracy on real client tickets has not been measured.
- Suggested replies are drafts for a human to review, not to send automatically.

## Next steps

Connect a real ticketing or email source, grow the evaluation set from real (consented) data, and track token cost per run. Token usage is already logged per ticket.

CI: GitHub Actions runs the tests and the offline mock on every push (`.github/workflows/ci.yml`).
