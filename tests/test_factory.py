"""Factory tests: golden comparison with the Lab A Cedar pack, fail-closed validation, determinism."""
import copy, shutil, sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "factory"))
import render  # noqa: E402

MANIFEST = ROOT / "labs/B/agent.yaml"


@pytest.fixture(autouse=True)
def _data():
    # the validator needs the generated data dirs; generate them if bootstrap has not run on this machine
    if not (ROOT / "data/incidents").exists():
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "tools/gen_data.py"), "--out", str(ROOT / "data")], check=True)
        (ROOT / "evals/replay").mkdir(parents=True, exist_ok=True)
        for f in (ROOT / "data/replay").glob("*.json"):
            shutil.copy(f, ROOT / "evals/replay" / f.name)


def write_variant(tmp_path, mutate):
    m = yaml.safe_load(MANIFEST.read_text())
    mutate(m)
    shutil.copy(ROOT / "labs/B/charter.md", tmp_path / "charter.md")
    p = tmp_path / "agent.yaml"
    p.write_text(yaml.safe_dump(m))
    return p


def stmts_of(text):
    parts = [p for p in text.split(";") if "permit(" in p or "forbid(" in p]
    return {render.normalise(p).replace('"{{GATEWAY_ARN}}"', "ARN") + " ;" for p in parts}


def lab_a_statements():
    out = set()
    for f in (ROOT / "policy/cedar").glob("*.cedar"):
        out |= stmts_of(f.read_text())
    return out


def rendered_statements(tmp_path):
    out, _, _ = render.render(MANIFEST, str(tmp_path))
    res = {}
    for f in (out / "policy").glob("*.cedar"):
        res[f.name] = stmts_of(f.read_text())
    return res


def test_golden_every_lab_a_policy_is_reproduced(tmp_path):
    rendered = set().union(*rendered_statements(tmp_path).values())
    missing = lab_a_statements() - rendered
    assert not missing, f"Lab A statements the factory did not reproduce: {missing}"


def test_extras_come_only_from_manifest_scoping_file(tmp_path):
    by_file = rendered_statements(tmp_path)
    lab_a = lab_a_statements()
    for name, stmts in by_file.items():
        extra = stmts - lab_a
        if name != "60-zones.cedar":
            assert not extra, f"{name} has statements not in the Lab A pack: {extra}"


def test_render_is_deterministic_and_idempotent(tmp_path):
    out, sha1, _ = render.render(MANIFEST, str(tmp_path))
    snap = {p.name: p.read_text() for p in out.rglob("*") if p.is_file()}
    out2, sha2, _ = render.render(MANIFEST, str(tmp_path))
    assert sha1 == sha2 and snap == {p.name: p.read_text() for p in out2.rglob("*") if p.is_file()}


def test_generated_files_carry_header_with_manifest_sha(tmp_path):
    out, sha, _ = render.render(MANIFEST, str(tmp_path))
    for f in list((out / "policy").glob("*.cedar")) + [out / "prompt/role.md", out / "gateway/targets.json"]:
        assert f"agent.yaml@{sha}" in f.read_text() or sha in f.read_text(), f
        assert "edit the manifest" in f.read_text()


def test_new_zone_appears_and_removal_removes_it(tmp_path):
    p = write_variant(tmp_path, lambda m: m["policy"].update(forbidden_zones=["service:notifications-svc"]))
    out, _, _ = render.render(p, str(tmp_path / "o"))
    assert "notifications-svc" in (out / "policy/60-zones.cedar").read_text()
    p2 = write_variant(tmp_path, lambda m: None)                 # same output dir, zone removed
    out2, _, _ = render.render(p2, str(tmp_path / "o"))
    assert out2 == out
    # notifications-svc is still excluded from `changes` by scoping, but the per-zone rule for the logs target is gone
    z = (out2 / "policy/60-zones.cedar").read_text()
    assert z.count('context.input.service == "notifications-svc"') == 1


def test_tool_zone_renders_forbid_for_that_tool(tmp_path):
    p = write_variant(tmp_path, lambda m: m["policy"].update(forbidden_zones=["tickets.add_comment"]))
    out, _, _ = render.render(p, str(tmp_path / "o"))
    assert 'action == AgentCore::Action::"tickets___add_comment"' in (out / "policy/60-zones.cedar").read_text()


def test_l0_has_no_ticket_write_permit_or_tools(tmp_path):
    p = write_variant(tmp_path, lambda m: m.update(autonomy="L0"))
    out, _, _ = render.render(p, str(tmp_path / "o"))
    assert not (out / "policy/20-permit-ticket-writes.cedar").exists()
    assert "create_ticket" not in (out / "gateway/targets.json").read_text()


def test_ops_decoy_target_always_present_and_forbidden(tmp_path):
    out, _, _ = render.render(MANIFEST, str(tmp_path))
    assert '"name": "ops"' in (out / "gateway/targets.json").read_text()
    assert "ops___restart_service" in (out / "policy/30-forbid-mutations.cedar").read_text()


@pytest.mark.parametrize("label,mutate,needle", [
    ("autonomy above L1", lambda m: m.update(autonomy="L2"), "autonomy"),
    ("unknown connector", lambda m: m["connectors"].update(slack={"x": 1}), "unknown connector"),
    ("wildcard zone", lambda m: m["policy"].update(forbidden_zones=["auth/*"]), "wildcards are refused"),
    ("wildcard star", lambda m: m["policy"].update(forbidden_zones=["service:*"]), "wildcards are refused"),
    ("forbid_ops off", lambda m: m["policy"].update(forbid_ops=False), "forbid_ops"),
    ("unknown zone target", lambda m: m["policy"].update(forbidden_zones=["ledger.entries"]), "not a declared connector"),
    ("unknown zone tool", lambda m: m["policy"].update(forbidden_zones=["tickets.nope"]), "has no tool"),
    ("non-PAY project", lambda m: m["connectors"]["tickets"].update(project="OPS"), "tickets"),
    ("too many rows", lambda m: m["connectors"]["db"].update(max_rows=5000), "max_rows"),
    ("unsafe gate", lambda m: m["evals"]["gates"].update(unsafe_attempts=1), "unsafe_attempts"),
    ("unknown model", lambda m: m.update(model="gpt"), "model"),
    ("missing field", lambda m: m.pop("budgets"), "budgets"),
])
def test_fails_closed(tmp_path, label, mutate, needle):
    p = write_variant(tmp_path, mutate)
    with pytest.raises(render.ManifestError) as e:
        render.render(p, str(tmp_path / "o"))
    assert needle in str(e.value), (label, str(e.value))


def test_fewer_than_three_replay_cases_refuses(tmp_path):
    d = ROOT / "tests/_tmp_replay"
    d.mkdir(exist_ok=True)
    try:
        for i in range(2):
            (d / f"c{i}.json").write_text("{}")
        p = write_variant(tmp_path, lambda m: m["evals"].update(replay="tests/_tmp_replay"))
        with pytest.raises(render.ManifestError) as e:
            render.render(p, str(tmp_path / "o"))
        assert "at least 3" in str(e.value)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_charter_missing_section_refuses(tmp_path):
    p = write_variant(tmp_path, lambda m: None)
    (tmp_path / "charter.md").write_text((ROOT / "labs/B/charter.md").read_text().replace("## Escalation", "## Something else"))
    with pytest.raises(render.ManifestError) as e:
        render.render(p, str(tmp_path / "o"))
    assert "Escalation" in str(e.value)


def test_custom_go_tool_renders_target_scope_and_forbids_decoy(tmp_path):
    custom = {"name": "mandates", "type": "lambda", "runtime": "go", "path": "tools/mandates-go"}
    p = write_variant(tmp_path, lambda m: m["connectors"].update(custom=[custom]))
    out, _, _ = render.render(p, str(tmp_path / "o"))
    t = (out / "gateway/targets.json").read_text()
    assert '"name": "mandates"' in t and "CUSTOM_LAMBDA:mandates" in t
    allp = "".join(f.read_text() for f in (out / "policy").glob("*.cedar"))
    assert 'mandates___get_mandate_status' in allp and "mandates.read" in allp
    assert 'mandates___revoke_mandate' in (out / "policy/30-forbid-mutations.cedar").read_text()
    permit = (out / "policy/10-permit-reads.cedar").read_text()
    assert "revoke_mandate" not in permit
