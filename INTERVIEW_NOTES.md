# Talking through this project (private notes, don't submit)

## 30-second version
"It's a small Python tool I built to practise client-style automation work. It takes support tickets, calls an LLM over its REST API to classify and summarise them, checks the answer is valid, retries when the API fails, and sends a priority-sorted digest to a webhook. I also wrote a small labelled test set to measure how accurate it is."

## Be ready for
- **Why validate the model output?** Models can return wrong shapes or invented values. A bad value breaks whatever reads it next, so it is rejected and retried.
- **What happens when the API fails?** Transient errors (429, 5xx, timeouts) retry with exponential backoff. After three attempts the ticket is marked failed and flagged for a human. One bad ticket never stops the batch.
- **Why a mock mode?** So the pipeline can be demoed and tested with no key or network. It is crude keyword rules, not a replacement for the model.
- **How accurate is it?** Report the real number from `python evaluate.py` on the live model. The set is only 12 hand-labelled tickets, so say it is a small check, not proof. (Mock mode scores well on the first 8 only because those rules were written while looking at them.)
- **What would you do with a real client?** Connect their real ticketing or email system, build a bigger evaluation set from their data, keep a human reviewing suggested replies, and check privacy and where data is sent before using any external API.
- **What would you improve?** Real integration, an evaluation set from real data, cost tracking per run, and a review step before any reply is sent.

## Honest limits to state
Personal prototype, made-up data, no real client or users, single developer. Built with AI coding assistance. Only say you can do what the code shows, and be able to read any function aloud and explain it.
