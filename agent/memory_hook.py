"""Retrieves past incidents and runbooks from AgentCore Memory before EACH model call (spec 7.7).

The query is the original task plus the most recent evidence (tool results / assistant text), so retrieval gets
sharper as the investigation learns what the failure looks like. Results accumulate; the best-scoring ones are
injected into the system prompt.
"""
import os
import sys

import boto3
from strands.hooks import BeforeModelCallEvent, HookProvider, HookRegistry

PRODUCT = os.environ.get("PRODUCT", "payments-gw")
NAMESPACES = [f"/products/{PRODUCT}/incidents", f"/products/{PRODUCT}/runbooks"]


def _text(msg):
    out = []
    for c in msg.get("content", []):
        if "text" in c:
            out.append(c["text"])
        elif "toolResult" in c:
            out += [x.get("text", "") for x in c["toolResult"].get("content", []) if isinstance(x, dict)]
    return " ".join(out)


class MemoryHook(HookProvider):
    def __init__(self, memory_id, region="us-west-2", base_prompt="", top_k=8, keep=(8, 3)):
        self.memory_id, self.base_prompt, self.top_k, self.keep = memory_id, base_prompt, top_k, keep
        self.client = boto3.client("bedrock-agentcore", region_name=region)
        self.seen = {}        # namespace -> {record text -> best score}
        self.calls = 0

    def register_hooks(self, registry: HookRegistry, **kw):
        registry.add_callback(BeforeModelCallEvent, self.retrieve)

    def retrieve(self, e):
        msgs = e.agent.messages
        first_user = next((_text(m) for m in msgs if m.get("role") == "user"), "")
        if not first_user:
            return
        recent = " ".join(_text(m)[:450] for m in msgs[-6:])      # head of each recent message: source/query/key fields
        # at intake only the task is known; afterwards the evidence is a far better query than the raw alert JSON
        query = (recent if len(msgs) > 2 else first_user)[:2000]
        self.calls += 1
        for ns in NAMESPACES:
            try:
                r = self.client.retrieve_memory_records(memoryId=self.memory_id, namespace=ns,
                                                        searchCriteria={"searchQuery": query, "topK": self.top_k})
            except Exception as ex:
                print(f"memory retrieve {ns}: {ex}", file=sys.stderr)
                continue
            bucket = self.seen.setdefault(ns, {})
            for x in r.get("memoryRecordSummaries", []):
                t = x["content"].get("text", "")
                bucket[t] = max(bucket.get(t, 0), x.get("score", 0))
        parts = []
        for ns, n in zip(NAMESPACES, self.keep):
            best = sorted(self.seen.get(ns, {}).items(), key=lambda kv: -kv[1])[:n]
            parts += [f"- {t[:900]}" for t, _ in best]
        if parts:
            e.agent.system_prompt = (self.base_prompt + "\n\nRelevant past incidents and runbooks from memory "
                                     "(cite the INC-/RB- ids you rely on; they may or may not match the current incident):\n"
                                     + "\n\n".join(parts))
