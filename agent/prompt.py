"""System prompt assembly. `make break-prompt` empties untrusted.md and cite.md (originals saved as *.orig)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

D = Path(__file__).resolve().parent / "prompt"
IST = timezone(timedelta(hours=5, minutes=30))


def system_prompt(extra=""):
    parts = [(D / n).read_text().strip() for n in ("role.md", "untrusted.md", "cite.md")]
    parts.append(f"Current time: {datetime.now(IST).isoformat(timespec='seconds')} (IST).")
    if extra:
        parts.append(extra)
    return "\n\n".join(p for p in parts if p)
