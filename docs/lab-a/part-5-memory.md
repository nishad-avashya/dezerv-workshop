# Part 5: Memory

!!! time "12 minutes"

## What you'll learn
- How an **AgentCore Memory** resource stores long-term records in **namespaces** under a memory **strategy**.
- How to seed memory deterministically with `BatchCreateMemoryRecords` instead of waiting for extraction.
- How a Strands hook retrieves relevant records **before every model call**, so the agent finds a precedent as its evidence grows.

## Concepts

A good human on-call engineer remembers: "we saw this in March, it was a config change, the runbook says roll back".
The agent should too. **AgentCore Memory** is a managed store for that history. A memory resource has one or more
**strategies**; a strategy owns a **namespace** (a path such as `/products/payments-gw`), and records written under
it can be searched semantically with `RetrieveMemoryRecords`.

`make memory` creates the resource `dezerv_payments_oncall` with two strategies:

- a **semantic** strategy `payments_facts` on `/products/payments-gw`. Records live one level below it, in
  `/products/payments-gw/incidents` and `/products/payments-gw/runbooks`. A memory allows one semantic strategy with one
  namespace, so the strategy owns the parent and the records go underneath;
- an **episodic** strategy `oncall_episodes` on `/products/payments-gw/episodes/{sessionId}`. It is created, but the
  Lab A hook reads only the semantic records.

**Seeding.** Memory can extract records from conversation events by itself, but that is asynchronous (60 s or more)
and depends on an LLM. For a lab, deterministic beats clever: `scripts/seed_memory.py` writes each file in
`data/incidents/` (26 past incidents) and `data/runbooks/` (8 runbooks) as one record with `BatchCreateMemoryRecords`,
in batches of 10, then polls until they are listable (about 30 s in testing). It skips a namespace that is already
seeded, so it is safe to re-run. Only one past incident, **INC-2026-031**, is a PSP timeout caused by a config change;
the others are deliberately similar-looking distractors.

**Retrieval before every model call.** `MemoryHook` (`agent/memory_hook.py`) subscribes to Strands'
`BeforeModelCallEvent`. On the first call it searches with the task (the alert). On every later call it searches with
the head of the last six messages (tool results and the model's own notes, up to 2000 characters), because the evidence
describes the failure far better than the raw alert JSON. It queries both namespaces (top 8 each), keeps the best
8 incidents and 3 runbooks seen so far, and appends them to the system prompt with an instruction to cite the
`INC-`/`RB-` ids it relies on. The hook is only added when `MEMORY_ID` is configured, which is why earlier runs printed
`(no memory configured)`.

![Memory: seed once, retrieve before every model call](../diagrams/lab-a-memory.drawio)

## Steps

### 1. Create the memory resource
```bash
make memory
```
??? example "Expected output (representative)"
    ```text
    [labA] memory ACTIVE: dezerv_payments_oncall-<suffix> strategies={'payments_facts': '...', 'oncall_episodes': '...'}
    ```

### 2. Start the Part 6 deploy now, in the background
Deploying the agent to AgentCore Runtime takes a few minutes, so start it now and let it run while you finish this
part. Open a **second terminal** in the repo root and run:
```bash
make deploy-agent
```
Start it only **after** `make memory` has finished: the deploy passes the memory id to the Runtime as an environment
variable and stops with an error if there is none yet. The deploy makes no tool calls, so it does not compete with
your `oncall` runs for the rate limit. You will check it at the start of Part 6.

### 3. Seed the incidents and runbooks
```bash
make seed-memory
```
??? example "Expected output (representative)"
    ```text
    /products/payments-gw/incidents: wrote 26 records
    /products/payments-gw/runbooks: wrote 8 records
    polling until records are listable ...
      incidents=26 runbooks=8
    memory seeded
    ```

### 4. Rerun the incident
```bash
make run-incident
```
The diagnosis should be the same as in Part 1, and now the answer also cites the precedent and the runbook:
**INC-2026-031** (PSP timeout from a config change) and **RB-PSP-TIMEOUT**. The `(no memory configured)` line is gone.

## Verify
```bash
make verify-labA-part5
```
!!! success "You should see"
    ```text
    PASS  memory has >= 25 incident records (found 26)
    PASS  rerun cites INC-2026-031
    PASS  rerun cites RB-PSP-TIMEOUT

    RESULT: PASS
    ```
    The verify runs the agent once more. Retrieval is semantic and the model picks the closest precedent, so if a
    citation is missing, rerun once (INC-2026-031 was cited in 3 of 3 test runs).

## What just happened
- A Memory resource with one semantic strategy now holds 26 incidents and 8 runbooks in two namespaces.
- Seeding wrote records directly with `BatchCreateMemoryRecords`: instant and repeatable, with no extraction wait.
- `MemoryHook` searches memory before every model call, with a query built from the latest evidence, and injects the best matches into the system prompt.
- The model, not the retriever, picks the precedent that matches, and cites it.

!!! question "Discuss"
    Why build the query from recent evidence instead of the alert? (In testing, a query built from the raw alert JSON
    ranked generic incidents first.) What could go wrong if the agent wrote its own conclusions back into memory
    after every run?

!!! tip "Behind?"
    `make solution-part5` brings you to the end of this part (it adds `memory` and `seed-memory`). It does not start the
    deploy: run `make deploy-agent` yourself, or use `make solution-part6`.

## Troubleshooting
- **No INC-2026-031 in the answer:** retrieval and model variance. Rerun `make run-incident`, then `make verify-labA-part5`.
- **`make deploy-agent` fails with a missing `MEMORY_ID`:** it started before `make memory` finished. Run it again.
- **`timed out waiting for records`:** indexing is slow; run `make seed-memory` again (it skips what is already there).
