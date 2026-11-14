"""Tiny MCP-over-HTTP client for the AgentCore Gateway + Cognito client-credentials tokens. No dependencies."""
import base64, json, os, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env():
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    st = ROOT / ".labA.json"
    if st.exists():
        env.update({k.upper(): v for k, v in json.loads(st.read_text()).items() if isinstance(v, str)})
    return env


_cache = {}


def token(persona="oncall", env=None):
    env = env or load_env()
    hit = _cache.get(persona)
    if hit and hit[1] > time.time() + 60:
        return hit[0]
    cid, sec = env[f"{persona.upper()}_CLIENT_ID"], env[f"{persona.upper()}_CLIENT_SECRET"]
    req = urllib.request.Request(env["TOKEN_URL"], data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()})
    for attempt in range(4):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=20))
            break
        except urllib.error.HTTPError:                # wrong client id/secret: retrying will not help
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    _cache[persona] = (r["access_token"], time.time() + r.get("expires_in", 3600))
    return r["access_token"]


def rpc(method, params=None, persona="oncall", env=None, tok=None):
    env = env or load_env()
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    req = urllib.request.Request(env["GATEWAY_URL"], data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                                          "Authorization": f"Bearer {tok or token(persona, env)}"})
    raw = None
    for attempt in range(4):
        try:
            raw = urllib.request.urlopen(req, timeout=120).read().decode()
            break
        except urllib.error.HTTPError as e:          # a real answer from the Gateway (401, 403, 5xx): never retried
            return {"http_error": e.code, "body": e.read().decode()[:2000]}
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == 3:                          # DNS blips and connection resets happen on busy networks: back off and retry
                raise
            time.sleep(1.5 * (attempt + 1))
    if raw.startswith("event:") or raw.startswith("data:"):
        raw = "".join(l[5:].strip() for l in raw.splitlines() if l.startswith("data:"))
    return json.loads(raw)


def list_tools(persona="oncall", env=None):
    out, cursor = [], None
    while True:
        r = rpc("tools/list", {"cursor": cursor} if cursor else {}, persona, env)
        res = r.get("result") or {}
        out += res.get("tools", [])
        cursor = res.get("nextCursor")
        if not cursor:
            return out


def call_tool(name, args, persona="oncall", env=None):
    """Returns (is_error, parsed_or_text, raw_response)."""
    r = rpc("tools/call", {"name": name, "arguments": args}, persona, env)
    if "result" in r:
        txt = "".join(c.get("text", "") for c in r["result"].get("content", []))
        try:
            parsed = json.loads(txt)
        except ValueError:
            parsed = txt
        return bool(r["result"].get("isError")), parsed, r
    return True, r.get("error") or r, r


def anchor(env=None):
    """Incident start (10:40 IST) chosen by bootstrap and stored as LAB_ANCHOR. Everything date-dependent derives from it."""
    from datetime import datetime
    env = env or load_env()
    if "LAB_ANCHOR" not in env:
        raise SystemExit("LAB_ANCHOR missing: run `make bootstrap` first")
    return datetime.fromisoformat(env["LAB_ANCHOR"])


def at(minutes=0, env=None):
    """ISO-8601 IST timestamp `minutes` after the incident start."""
    from datetime import timedelta
    return (anchor(env) + timedelta(minutes=minutes)).isoformat(timespec="seconds")
