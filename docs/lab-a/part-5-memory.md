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

!!! note "Other memory strategies (out of scope today)"
    AgentCore Memory has more strategies than the two used here. The built-in ones are semantic, summary, user preference and
    episodic. You can also customize a built-in strategy with your own extraction prompt and model, or use a **self-managed**
    strategy, where you run your own extraction and consolidation and use Memory only for storage and retrieval. We use
    semantic records here and don't cover the others in this workshop.

**Seeding**

- Memory can extract records from conversations itself, but that is slow (60 s or more) and depends on an LLM.
- So the lab seeds deterministically: `scripts/seed_memory.py` writes 26 past incidents (`data/incidents/`) and 8 runbooks (`data/runbooks/`) as records with `BatchCreateMemoryRecords`.
- It takes about 30 s and is safe to re-run, because it skips a namespace that is already seeded.
- Only one incident, **INC-2026-031**, is a PSP timeout from a config change. The rest are look-alike distractors.

**Retrieval before every model call**

- `MemoryHook` (`agent/memory_hook.py`) runs before each model call.
- The first call searches with the alert. Later calls search with the recent tool results and notes, because the evidence describes the failure better than the raw alert.
- It searches both namespaces, keeps the best 8 incidents and 3 runbooks, and adds them to the system prompt, asking the model to cite the `INC-`/`RB-` ids it uses.
- The hook is only added when `MEMORY_ID` is set, which is why earlier runs printed `(no memory configured)`.

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

### 2. Seed the incidents and runbooks
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

### 3. Rerun the incident
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
    `make solution-part5` brings you to the end of this part (it adds `memory` and `seed-memory`).

## Troubleshooting
- **No INC-2026-031 in the answer:** retrieval and model variance. Rerun `make run-incident`, then `make verify-labA-part5`.
- **`timed out waiting for records`:** indexing is slow; run `make seed-memory` again (it skips what is already there).
