#!/usr/bin/env python3
"""mcp_cli.py list [--persona P] | call <tool> '<json>' [--persona P]  -- talk to the Gateway directly."""
import argparse, json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import mcpc

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["list", "call", "token"])
ap.add_argument("tool", nargs="?")
ap.add_argument("args", nargs="?", default="{}")
ap.add_argument("--persona", default="oncall")
a = ap.parse_args()
if a.cmd == "token":
    print(mcpc.token(a.persona))
elif a.cmd == "list":
    ts = mcpc.list_tools(a.persona)
    print(len(ts), "tools"); [print(" ", t["name"]) for t in ts]
else:
    err, out, raw = mcpc.call_tool(a.tool, json.loads(a.args), a.persona)
    print("ERROR" if err else "OK"); print(json.dumps(out, indent=1)[:3000])
