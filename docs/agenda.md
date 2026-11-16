# Agenda

The day mixes **AWS workshop content** (feature learning, generic examples) with **Dezerv labs** (this site). All times are IST.

![Day flow](diagrams/day-flow.drawio)

| Time | Block | Content |
|---|---|---|
| 09:30–10:00 | **Mental model** | AgentCore components mapped to Dezerv's platform needs, managed harness vs bring-your-own (Strands), and where AgentCore sits next to Dezerv's agentic SDLC tooling. *Start [bootstrap](getting-started/bootstrap.md) during the talk.* |
| 10:00–11:30 | **Track 1, part A** (AWS) | Your First Agent in Minutes (Harness) · Host Your Agent · Gateway · Authenticate & Authorize · Policy |
| 11:30–11:45 | Break | |
| 11:45–13:00 | [**Lab A, Parts 1–4**](lab-a/index.md) | Gateway and tools · Cedar policy · Interceptors · Audit hooks |
| 13:00–13:45 | Lunch | |
| 13:45–14:30 | **Track 1, part B** (AWS) | Manage Context (Memory) · Observe · Evaluate |
| 14:30–15:00 | [**Lab A, Parts 5–6**](lab-a/part-5-memory.md) | Incident memory and runbooks · Deploy, evaluate, CI gate |
| 15:00–15:15 | **Track 2** (AWS, condensed) | Build with Skills: End-to-End Example (walkthrough) · Customize Your Environment |
| 15:15–15:45 | [**Lab B**](lab-b/index.md) | Agent factory, Go service calls the agent, Go Lambda tool |
| 15:45–17:15 | [**Capstone**](capstone/index.md) | Each squad builds and demos an on-call agent for its own service |
| 17:15–17:45 | **Production Q&A** | IaC, account and tenant boundaries, cost, PrivateLink to MongoDB Atlas and Snowflake, region coverage, and the path to the Lead Product Engineer Agent Platform |

!!! note "AWS workshop pages we skip"
    From Track 1: *Connect Your Agent to Anything* (Code Interpreter is optional), *Optimize*, *Registry* (mentioned in Q&A) and *Agents That Transact*.

!!! tip "If the day runs long"
    Lab B shrinks to a 15-minute instructor demo, and only the Go Lambda tool is done hands-on. Every part also has a
    [catch-up target](reference/catch-up.md) that brings a squad that fell behind to the end of that part.

!!! warning "Start long-running steps early"
    - `make bootstrap` takes about 6 minutes, so run it during the mental-model talk.
    - `make deploy-agent` takes a few minutes, so run it first in Lab A Part 6 and read the concepts while it deploys.
    - A full `make eval` takes about 12 minutes, because cases run one at a time under the 30-calls-a-minute rate limit.
