"""AuditHooks (lab spec 7.6, TLA-07): one JSON line per lifecycle event to CloudWatch /dezerv/agent-audit."""
import base64, hashlib, json, os, re, sys, time, uuid
from datetime import datetime, timezone

import boto3
from strands.hooks import (AfterInvocationEvent, AfterToolCallEvent, BeforeInvocationEvent, BeforeToolCallEvent, HookProvider, HookRegistry)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "interceptor"))  # repo layout; in the Runtime zip pii.py sits beside this file
from pii import mask_obj  # same detectors as the Gateway interceptor

GROUP = "/dezerv/agent-audit"
DENY_MARK = re.compile(r"Tool Execution Denied|RATE_LIMITED|CHANGE_FREEZE|AccessDenied|not allowed", re.I)


def principal_of(token):
    try:
        p = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))).get("sub", "unknown")
    except Exception:
        return "unknown"


def trace_id():
    try:
        from opentelemetry import trace
        t = trace.get_current_span().get_span_context().trace_id
        if t:
            return format(t, "032x")
    except Exception:
        pass
    return uuid.uuid4().hex


class AuditHooks(HookProvider):
    def __init__(self, agent_id, session_id, task_id, principal, region="us-west-2", sink=None):
        self.ids = dict(agent_id=agent_id, session_id=session_id, task_id=task_id, principal=principal)
        self.logs = boto3.client("logs", region_name=region)
        self.stream = f"{session_id}-{uuid.uuid4().hex[:6]}"
        self.sink = sink
        self._t0, self._tools, self._tok0 = {}, 0, 0
        try:
            self.logs.create_log_stream(logGroupName=GROUP, logStreamName=self.stream)
        except Exception as e:
            print("audit stream:", e, file=sys.stderr)

    def register_hooks(self, registry: HookRegistry, **kw):
        registry.add_callback(BeforeInvocationEvent, self.before_inv)
        registry.add_callback(AfterInvocationEvent, self.after_inv)
        registry.add_callback(BeforeToolCallEvent, self.before_tool)
        registry.add_callback(AfterToolCallEvent, self.after_tool)

    # ---- sink
    def emit(self, event, **f):
        rec = {"ts": datetime.now(timezone.utc).isoformat(), **self.ids, "event": event, "trace_id": trace_id(), **f}
        line = json.dumps(rec, default=str)
        if self.sink is not None:
            self.sink.append(rec)
        try:
            self.logs.put_log_events(logGroupName=GROUP, logStreamName=self.stream,
                                     logEvents=[{"timestamp": int(time.time() * 1000), "message": line}])
        except Exception as e:  # auditing must not break the agent
            print("audit write failed:", e, file=sys.stderr)

    @staticmethod
    def _tokens(agent):
        try:
            return int(agent.event_loop_metrics.accumulated_usage.get("totalTokens", 0))
        except Exception:
            return 0

    # ---- invocation
    def before_inv(self, e):
        self._tok0 = self._tokens(e.agent)
        self.emit("before_invocation", tool=None, tokens=0)

    def after_inv(self, e):
        self.emit("after_invocation", tool=None, tokens=self._tokens(e.agent) - self._tok0)

    # ---- tools
    def before_tool(self, e):
        tid = e.tool_use["toolUseId"]
        self._t0[tid] = time.time()
        self.emit("before_tool_call", tool=e.tool_use["name"], input_masked=mask_obj(e.tool_use.get("input")))

    def after_tool(self, e):
        tid = e.tool_use["toolUseId"]
        lat = int((time.time() - self._t0.pop(tid, time.time())) * 1000)
        res = e.result or {}
        text = " ".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict))
        if e.exception is not None:
            text += f" {type(e.exception).__name__}: {e.exception}"
        failed = res.get("status") == "error" or e.exception is not None
        denied = failed and (bool(DENY_MARK.search(text)) or bool(e.cancel_message))
        reason = None
        if denied:
            m = re.search(r"(RATE_LIMITED|CHANGE_FREEZE)", text) or re.search(r"denied due to ([A-Za-z0-9_]+)", text)
            reason = m.group(1) if m else (e.cancel_message or text[:160])
        self.emit("after_tool_call", tool=e.tool_use["name"], input_masked=mask_obj(e.tool_use.get("input")),
                  output_sha256=hashlib.sha256(text.encode()).hexdigest(), latency_ms=lat,
                  decision={"result": "denied" if denied else "allowed", "reason": reason})
