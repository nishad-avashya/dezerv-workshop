#!/usr/bin/env python3
"""break_prompt.py break|fix : remove / restore the untrusted-content rule and the cite-evidence rule (spec 7.8).

After `break`, redeploy (make deploy-agent) and run `make gate`: the unsafe-attempt metric should go red because the
agent may now obey injected instructions. Policy still blocks the action, so nothing is actually restarted.
"""
import shutil, sys
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "agent" / "prompt"
FILES = ["untrusted.md", "cite.md"]
mode = sys.argv[1] if len(sys.argv) > 1 else ""
for f in FILES:
    p, o = D / f, D / (f + ".orig")
    if mode == "break":
        if not o.exists():
            shutil.copy(p, o)
        p.write_text("")
    elif mode == "fix":
        if o.exists():
            shutil.copy(o, p); o.unlink()
    else:
        sys.exit(__doc__)
print(f"prompt {mode}: " + ", ".join(f"{f}={'EMPTY' if not (D / f).read_text().strip() else 'ok'}" for f in FILES))
