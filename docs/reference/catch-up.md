# Catch-up targets

Fell behind, or a step broke and you want to move on? Every part has a **solution target** that brings your account to the end of that part.
They are idempotent: running one again, or running one when you're already ahead, is safe.

## Lab A

| Target | Brings you to | Runs |
|---|---|---|
| `make solution-part1` | End of Part 1: Gateway + 6 targets | `bootstrap gateway` |
| `make solution-part2` | End of Part 2: Cedar pack enforced | `+ policy` |
| `make solution-part3` | End of Part 3: interceptors attached | `+ interceptors` |
| `make solution-part4` | End of Part 4 (audit hooks are always on in `agent/`) | same as Part 3 |
| `make solution-part5` | End of Part 5: memory created and seeded | `+ memory seed-memory` |
| `make solution-part6` | Part 6 setup: agent deployed to Runtime | `+ deploy-agent` (then `make eval`, `make gate` yourself) |
| `make cp6` / `make cp6-off` | Apply or remove the CP-6 exercise solution (ledger-svc forbidden zone) | |

## Lab B

Lab B needs Lab A deployed. If you are behind, run `make solution-part6` first.

| Target | Brings you to |
|---|---|
| `make solution-labB-part1` | Factory agent `payments-gw` rendered and deployed |
| `make solution-labB-part2` | Same as Part 1 (the Go forwarder needs no deployment) |
| `make solution-labB-part3` | Go mandates tool added to the manifest and deployed |
| `make solution-labB-part4` | `service:ledger-svc` forbidden zone added and deployed |

!!! warning "Lab B solution targets overwrite `labs/B/agent.yaml`"
    They copy the reference manifest over yours. Copy your edits somewhere else first if you want to keep them.

## Capstone

The capstone has no solution targets, because each squad's agent is its own. Use the [checkpoints](../capstone/index.md)
`make verify-capstone SQUAD=<s> CHECK=C1|C2|C3` to find what is missing, or pick a ready profile to restart quickly.

## Every target

```bash
make help
```
