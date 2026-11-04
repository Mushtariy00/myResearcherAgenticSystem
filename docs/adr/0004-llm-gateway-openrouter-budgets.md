# ADR 0004 — Own LLM gateway: paid OpenRouter models while the budget allows, free otherwise

- Status: accepted (2026-10-30), amended (2026-11-04; see the end)

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

## Amendment (2026-11-04)
What building and running it changed.

- **One key for now, not one per user.** The gateway holds a single OpenRouter key; the management
  key and the per-user keys above were never built, and they move to Phase 5 of the plan.
  - The journal already holds each person to their budget before a call goes out, and prepaid
    credit with auto top-up off caps the lab. A per-user key would be a second limit on the same
    money, which only matters if the journal has a bug.
  - It would cost a management key in the gateway (one that can raise any limit), encrypted storage
    of the keys, and extra steps whenever someone is invited, budgeted or offboarded.
  - It comes back if the lab's users stop being trusted colleagues, or if OpenRouter's own
    accounting per person is wanted.
  - A limit set on the one key in OpenRouter's settings still works, but for everyone: its 402
    moves the calls to free models.
- **A clock limit on every attempt.** Read timeouts never fire, because OpenRouter keeps a
  non-streaming request alive with whitespace while the model writes, so a stuck model was never
  replaced. An attempt now gets 120 s plus 20 tokens a second of the output it may write
  (`ARP_REQUEST_TIMEOUT_SECONDS`, `ARP_SLOWEST_TOKENS_PER_SECOND`): 320 s for a 4,000-token call and
  920 s for a coding call. A flat limit wouldn't do: free models took up to 454 s to write working
  code, and the slowest wrote 8 tokens a second.
  - A model past its limit rests for 30 minutes, and the next one takes over.
  - A paid attempt that timed out keeps its reservation until the sweeper settles it, because
    OpenRouter may still charge for it.
  - A call gives up after three limits (`ARP_ATTEMPTS_PER_CALL`), or when its models run out.
- **Each agent role can have its own chains**, set on the admin page and read on every call. An
  empty paid chain keeps a role on free models. They live in `settings`; the lab's chains stay in
  `ARP_PAID_MODELS` and `ARP_FREE_MODELS` for the roles without their own.
- **The gateway reports what it reads.** It alone holds the key, so it writes the model catalog
  (hourly) and the account (every 5 minutes: balance, free tier, daily limit) to `settings`, and
  the API reads them there. The admin pages keep working while the gateway is down and say when each
  was read. OpenRouter documents `/credits` for management keys, though it answered for this key;
  when it refuses, the gateway falls back on `/key`, and with neither the page says the balance is
  unknown.
- **The balance warning starts at $2** (`ARP_BALANCE_ALERT_FLOOR_USD`), not the $10 once planned: the
  lab's first purchase is $10, which would alert from the first paid call.
