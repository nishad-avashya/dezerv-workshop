"""The anchor rule: latest 10:40 IST that has >= 40 min of past after it, so the lab works on any day, any hour."""
import sys, os
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")
import importlib.util
IST = timezone(timedelta(hours=5, minutes=30))
spec = importlib.util.spec_from_file_location("bootstrap", os.path.join(os.path.dirname(__file__), "..", "scripts", "bootstrap.py"))
bs = importlib.util.module_from_spec(spec); spec.loader.exec_module(bs)

def at(y, m, d, h, mi): return datetime(y, m, d, h, mi, tzinfo=IST).astimezone(timezone.utc)

def test_morning_uses_yesterday():
    assert bs.pick_anchor(at(2026, 11, 14, 9, 30)).isoformat() == "2026-11-13T10:40:00+05:30"

def test_just_before_cutoff_uses_yesterday():
    assert bs.pick_anchor(at(2026, 11, 14, 11, 19)).date().isoformat() == "2026-11-13"

def test_after_cutoff_uses_today():
    assert bs.pick_anchor(at(2026, 11, 14, 11, 20)).isoformat() == "2026-11-14T10:40:00+05:30"

def test_evening_and_month_boundary():
    assert bs.pick_anchor(at(2026, 12, 1, 8, 0)).isoformat() == "2026-11-30T10:40:00+05:30"
    assert bs.pick_anchor(at(2026, 11, 14, 23, 59)).isoformat() == "2026-11-14T10:40:00+05:30"

def test_anchor_always_in_past_and_within_cloudwatch_window():
    now = at(2026, 11, 14, 9, 30)
    a = bs.pick_anchor(now)
    assert a + timedelta(minutes=40) <= now and now - a < timedelta(days=2)
