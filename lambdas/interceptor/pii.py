"""PII masking (TLA-04) and untrusted-content tagging (GOV-07). Pure functions, unit-tested."""
import re

_EMAIL = re.compile(r"(?<![\w.])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_VPA = re.compile(r"(?<![\w.@])[\w.\-]{2,}@[a-zA-Z]{2,}(?!\w|@|\.\w)")  # trailing sentence period is fine
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")
_PANNO = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_ACCT = re.compile(r"(?i)\b(acct|account)([\s:#=\-]*)(\d{9,18})\b")
_MOBILE = re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)")


def luhn_ok(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def _card(m):
    digits = re.sub(r"\D", "", m.group(0))
    if 13 <= len(digits) <= 19 and luhn_ok(digits):
        return "XXXX-XXXX-XXXX-" + digits[-4:]
    return m.group(0)


def mask_text(s):
    if not isinstance(s, str) or not s:
        return s
    s = _ACCT.sub(lambda m: f"{m.group(1)}{m.group(2)}{'X' * (len(m.group(3)) - 4)}{m.group(3)[-4:]}", s)
    s = _EMAIL.sub(lambda m: "***@" + m.group(0).split("@", 1)[1], s)
    s = _CARD.sub(_card, s)
    s = _AADHAAR.sub(lambda m: "XXXX-XXXX-" + re.sub(r"\D", "", m.group(0))[-4:], s)
    s = _PANNO.sub(lambda m: "XXXXXXXXX" + m.group(0)[-1], s)
    s = _MOBILE.sub(lambda m: "XXXXXXX" + re.sub(r"\D", "", m.group(0))[-3:], s)
    s = _VPA.sub(lambda m: "***@" + m.group(0).split("@", 1)[1], s)
    return s


def mask_obj(o):
    if isinstance(o, str):
        return mask_text(o)
    if isinstance(o, list):
        return [mask_obj(v) for v in o]
    if isinstance(o, dict):
        return {k: mask_obj(v) for k, v in o.items()}
    return o


def _wrap(source, text):
    if not isinstance(text, str) or text.startswith("<untrusted"):
        return text
    text = text.replace("</untrusted>", "")  # cannot be closed from inside
    return f'<untrusted source="{source}">{text}</untrusted>'


def tag_untrusted(tool, data):
    """Wrap free-text fields from tickets and logs. `data` is the parsed tool result."""
    if not isinstance(data, dict):
        return data
    body = data.get("data", data)
    if tool.startswith("logs___"):
        for line in body.get("lines", []) if isinstance(body, dict) else []:
            if "msg" in line:
                line["msg"] = _wrap("cloudwatch-log", line["msg"])
    elif tool.startswith("tickets___") and isinstance(body, dict):
        items = body.get("tickets") or ([body] if "key" in body else [])
        for t in items:
            src = f"ticket:{t.get('key', '?')}"
            for f in ("summary", "body"):
                if f in t:
                    t[f] = _wrap(src, t[f])
            for c in t.get("comments", []) or []:
                c["body"] = _wrap(src, c.get("body"))
    return data
