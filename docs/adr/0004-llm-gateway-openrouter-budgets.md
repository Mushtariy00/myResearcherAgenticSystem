# ADR 0004 — Own LLM gateway: paid OpenRouter models while the budget allows, free otherwise

- Status: accepted (2026-10-30)

## Context
The lab wants paid and free models to be interchangeable per user budget. The legacy system used
free models only, and all 13 recorded LLM errors were 503s.

OpenRouter (Oct 2026):
- per-key credit limits with a monthly reset (UTC), managed through a management key;
- the actual cost in each response's `usage`, and `/generation?id=` for exact cost later;
- HTTP 402 with `limit_source=openrouter_key_limit` when a key is over its limit;
- free models capped at 20 requests/min and 50/day *per account*, or 1,000/day after a lifetime
  $10 purchase.

LiteLLM shipped malicious releases in March and October 2026 and had critical CVEs.

## Decision
- **A separate `gateway` service** is the only holder of OpenRouter keys: the lab management key,
  plus one provisioned key per user whose limit equals the user's monthly budget. Auto top-up
  stays off. Workers hold no provider keys and call the gateway over the internal network. CrewAI
  reaches it through a custom `BaseLLM`.
- **Every call is a journal row** (`reserved → sent → settled | unknown | released`):
  - The reservation is input tokens plus the role's max output tokens × price.
  - Calls are sent with an idempotency key and `max_price`.
  - A sweeper settles rows left `unknown` through `/generation`.
- **Routing:** if the reservation fits within the minimum of the user's budget and the run's cap,
  and paid models are enabled, the gateway uses the role's paid chain. Otherwise it uses the
  role's free chain, after checking the free model's context length.
  - A 402 key-limit error switches the rest of the run to free models.
  - An exhausted lab balance pauses the run (`paused_budget`) and alerts admins.
- **The free quota is one account-wide bucket** with a per-user fair share.
- **Privacy:** confidential projects route with `data_collection: deny`, or disable free models.

## Consequences
- We own a small, well-tested piece of money-handling code.
- The lab should buy $10 of OpenRouter credit once, to unlock 1,000 free calls/day.

## Alternatives considered
- **LiteLLM proxy** (has budgets and virtual keys): rejected for its 2026 supply-chain and CVE
  history.
- **Direct OpenRouter calls from workers**: puts keys in every worker, with no central ledger.
