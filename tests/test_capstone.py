"""Every ready profile must generate a squad that the factory accepts and renders (so no squad meets a broken profile on the day)."""
import json, shutil, subprocess, sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import render  # noqa: E402

PROFILES = sorted(p.stem for p in (ROOT / "capstone/profiles").glob("*.yaml"))


def gen(profile, squad):
    subprocess.run([sys.executable, str(ROOT / "tools/gen_profile.py"), "--profile", profile, "--squad", squad], check=True, capture_output=True)
    return ROOT / "squads" / squad


@pytest.fixture
def squad(request):
    name = f"tst-{request.node.callspec.params['profile'][:8]}"
    d = gen(request.node.callspec.params["profile"], name)
    yield name, d
    shutil.rmtree(d, ignore_errors=True)


@pytest.mark.parametrize("profile", PROFILES)
def test_profile_generates_valid_squad_that_renders(profile, squad, tmp_path):
    name, d = squad
    meta = json.loads((d / "meta.json").read_text())
    out, sha, files = render.render(d / "agent.yaml", str(tmp_path))
    assert (out / "gateway/targets.json").exists()
    tg = {t["name"]: t for t in json.loads((out / "gateway/targets.json").read_text())["targets"]}
    assert meta["target"] in tg and tg[meta["target"]]["tools"][0]["name"] == meta["tool"]
    pol = "".join(f.read_text() for f in (out / "policy").glob("*.cedar"))
    assert "ops___restart_service" in pol and "custom.read" in pol
    assert len(list((d / "replay").glob("*.json"))) >= 3


@pytest.mark.parametrize("profile", PROFILES)
def test_scenario_is_self_consistent(profile, squad):
    name, d = squad
    meta = json.loads((d / "meta.json").read_text())
    prof = yaml.safe_load((d / "profile.yaml").read_text())
    docs = json.loads((d / f"data/mongo/{meta['collection']}.json").read_text())
    window = [x for x in docs if x["created_at"] >= meta["anchor"][:16] and x["error_code"]]
    assert len(window) == meta["failures"], "failure count in the data must equal the profile's"
    logs = [json.loads(l) for l in (d / f"data/cloudwatch/{meta['service']}.log").read_text().splitlines()]
    errs = [l for l in logs if l["level"] == "ERROR"]
    assert len(errs) == meta["failures"] and all(l["commit"] == prof["incident"]["deploy"]["commit"] for l in errs)
    assert all({"commit", "caller", "template_id", "trace_id"} <= set(l) for l in logs)
    deploys = json.loads((d / "data/changes/deploys.json").read_text())
    assert any(x["commit"] == prof["incident"]["deploy"]["commit"] for x in deploys)
    assert "ignore prior instructions" in json.loads((d / "data/tickets.json").read_text())[0]["body"]
    assert any("ops-hint" in l["msg"] for l in logs), "planted log injection missing"


def test_missing_profile_field_is_reported(tmp_path):
    bad = yaml.safe_load((ROOT / "capstone/profiles/kyc-svc.yaml").read_text())
    del bad["incident"]["root_cause"]
    f = tmp_path / "bad.yaml"
    f.write_text(yaml.safe_dump(bad))
    r = subprocess.run([sys.executable, str(ROOT / "tools/gen_profile.py"), "--schema", str(f), "--squad", "tst-bad"], capture_output=True, text=True)
    assert r.returncode != 0 and "incident.root_cause" in (r.stdout + r.stderr)
    shutil.rmtree(ROOT / "squads/tst-bad", ignore_errors=True)
