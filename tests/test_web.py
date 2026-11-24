# Web API tests — auth, skill editor, experiment builder, jobs.
# Runs against a throwaway copy of examples/demo-lab; offline (model mock).
import os
import shutil
import time

import pytest

pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient  # noqa: E402

import skilllab.models  # noqa: E402 - import before env switch
from skilllab.lab import Lab  # noqa: E402

DEMO = os.path.join(os.path.dirname(__file__), "..", "examples",
                    "demo-lab")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    labdir = tmp_path / "lab"
    shutil.copytree(DEMO, labdir)
    monkeypatch.setenv("SKILLLAB_DIR", str(labdir))
    monkeypatch.setenv("SKILLLAB_TOKEN", "t")
    from web.backend.app import app
    return TestClient(app)


H = {"Authorization": "Bearer t"}


def wait_job(c, jid, limit=30):
    for _ in range(limit * 4):
        j = c.get(f"/api/v1/jobs/{jid}", headers=H).json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.25)
    raise AssertionError(f"job {jid} stuck: {j['status']}")


class TestAuth:
    def test_health_public(self, client):
        assert client.get("/api/v1/health").status_code == 200

    def test_gets_require_token(self, client):
        for route in ("/api/v1/skills", "/api/v1/experiments",
                      "/api/v1/jobs", "/api/v1/status"):
            assert client.get(route).status_code == 401
            assert client.get(route, headers=H).status_code == 200


class TestSkillEditor:
    def test_tree_read_write_conflict(self, client):
        ref = "commit-helper@v3-bp"
        tree = client.get(f"/api/v1/skills/{ref}/files",
                          headers=H).json()["files"]
        assert any(f["path"] == "SKILL.md" for f in tree)
        assert all("revisions" not in f["path"].split("/")
                   for f in tree)

        r = client.get(f"/api/v1/skills/{ref}/file",
                       params={"path": "SKILL.md"}, headers=H).json()
        body = r["text"]

        ok = client.put(f"/api/v1/skills/{ref}/file", headers=H,
                        json={"path": "SKILL.md", "text": body + " x",
                              "base_sha": r["sha"]})
        assert ok.status_code == 200
        stale = client.put(f"/api/v1/skills/{ref}/file", headers=H,
                           json={"path": "SKILL.md", "text": "y",
                                 "base_sha": r["sha"]})
        assert stale.status_code == 409

    def test_traversal_and_revision_guard(self, client):
        ref = "commit-helper@v3-bp"
        for bad in ("../lab.yaml", "../../etc/passwd",
                    "revisions/r001.md"):
            assert client.get(f"/api/v1/skills/{ref}/file",
                              params={"path": bad},
                              headers=H).status_code in (400, 404)

    def test_revisions_restore_and_delete_guard(self, client):
        ref = "commit-helper@v3-bp"
        orig = client.get(f"/api/v1/skills/{ref}/file",
                          params={"path": "SKILL.md"}, headers=H).json()
        client.put(f"/api/v1/skills/{ref}/file", headers=H,
                   json={"path": "SKILL.md",
                         "text": orig["text"] + " edit",
                         "base_sha": orig["sha"]})
        revs = client.get(f"/api/v1/skills/{ref}/revisions",
                          params={"path": "SKILL.md"}, headers=H).json()["revisions"]
        assert len(revs) >= 1
        rev = client.get(f"/api/v1/skills/{ref}/revision",
                         params={"path": "SKILL.md",
                                 "rev": revs[-1]["rev"]},
                         headers=H).json()
        assert rev["text"] == orig["text"]
        # restore (is itself a snapshot'd edit)
        latest = client.get(f"/api/v1/skills/{ref}/file",
                            params={"path": "SKILL.md"},
                            headers=H).json()
        r = client.post(f"/api/v1/skills/{ref}/restore", headers=H,
                        json={"path": "SKILL.md", "rev": revs[-1]["rev"],
                              "base_sha": latest["sha"]})
        assert r.status_code == 200
        # SKILL.md may not be deleted; other files snapshot first
        assert client.delete(f"/api/v1/skills/{ref}/file",
                             params={"path": "SKILL.md"},
                             headers=H).status_code == 400

    def test_create_and_rename(self, client):
        ref = "commit-helper@v3-bp"
        r = client.put(f"/api/v1/skills/{ref}/file", headers=H,
                       json={"path": "notes.md", "text": "hi",
                             "base_sha": ""})
        assert r.status_code == 200
        r = client.post(f"/api/v1/skills/{ref}/rename", headers=H,
                        json={"path": "notes.md", "to": "docs/notes.md"})
        assert r.status_code == 200
        files = client.get(f"/api/v1/skills/{ref}/files",
                           headers=H).json()["files"]
        assert "docs/notes.md" in [f["path"] for f in files]
        # guards: collision, SKILL.md, traversal, revisions escape
        assert client.post(f"/api/v1/skills/{ref}/rename", headers=H,
                           json={"path": "docs/notes.md",
                                 "to": "SKILL.md"}).status_code == 400
        assert client.post(f"/api/v1/skills/{ref}/rename", headers=H,
                           json={"path": "docs/notes.md",
                                 "to": "../x"}).status_code == 400
        assert client.post(f"/api/v1/skills/{ref}/rename", headers=H,
                           json={"path": "docs/notes.md",
                                 "to": "revisions/x"}
                           ).status_code == 400


class TestExperimentAPI:
    def test_detail_config_put_and_duplicate(self, client):
        r = client.post("/api/v1/experiments",
                        headers=H, json={"id": "exp-web",
                                         "category": "capability"})
        assert r.status_code == 200
        exp = client.get("/api/v1/experiments/exp-web",
                         headers=H).json()["experiment"]
        exp["rollouts_per_arm"] = 1
        exp["tasks"] = ["write-commit-msg", "unrelated-refactor"]
        exp["arms"] = [{"name": "control", "skill": None},
                       {"name": "t", "skill": "commit-helper@v3-bp"}]
        r = client.put("/api/v1/experiments/exp-web/config",
                       headers=H, json=exp)
        assert r.status_code == 200 and r.json()["valid"], r.json()
        bad = {**exp, "rollouts_per_arm": -3}
        assert client.put("/api/v1/experiments/exp-web/config",
                          headers=H, json=bad).status_code == 200
        r = client.post("/api/v1/experiments/exp-web/duplicate",
                        headers=H, json={"id": "exp-web2"})
        assert r.status_code == 200
        dup = client.get("/api/v1/experiments/exp-web2",
                         headers=H).json()["experiment"]
        assert dup["status"] == "designed"
        assert client.get("/api/v1/experiments/exp-web2/runs",
                          headers=H).json() == []

    def test_run_returns_job_and_completes(self, client):
        client.post("/api/v1/experiments", headers=H,
                    json={"id": "exp-job", "category": "capability"})
        exp = client.get("/api/v1/experiments/exp-job",
                         headers=H).json()["experiment"]
        exp["rollouts_per_arm"] = 1
        exp["tasks"] = ["write-commit-msg"]
        exp["arms"] = [{"name": "control", "skill": None},
                       {"name": "t", "skill": "commit-helper@v3-bp"}]
        client.put("/api/v1/experiments/exp-job/config",
                   headers=H, json=exp)
        r = client.post("/api/v1/experiments/exp-job/run",
                        headers=H, json={})
        assert r.status_code == 200
        body = r.json()
        assert body["job"] and body["planned"] >= 1
        j = wait_job(client, body["job"])
        assert j["status"] == "completed" and j["progress"] == 1.0

    def test_concluded_is_immutable(self, client):
        r = client.post("/api/v1/experiments/exp-trigger-wording/run",
                        headers=H, json={})
        assert r.status_code == 409


class TestJobsAPI:
    def test_cancel_and_unknown(self, client):
        assert client.get("/api/v1/jobs/job-nope",
                          headers=H).status_code == 404
        r = client.post("/api/v1/jobs/job-nope/cancel",
                        headers=H)
        assert r.status_code == 404

    def test_quality_report(self, client):
        r = client.get("/api/v1/report/commit-helper/v3-bp",
                       headers=H)
        assert r.status_code == 200
        d = r.json()
        assert d["skill"] == "commit-helper" and d["variant"] == "v3-bp"
        assert d["content_hash"].startswith("sha256:")
        assert "verdict" in d and "label" in d["verdict"]
        assert isinstance(d["experiments"], list)
        assert isinstance(d["regressions"], list)
        assert d["simulated"] is True
        r = client.get("/api/v1/report/commit-helper/v3-bp?format=md",
                       headers=H)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/markdown")
        assert "attachment" in r.headers["content-disposition"]
        assert "Quality Report" in r.text
        assert client.get("/api/v1/report/commit-helper/nope",
                          headers=H).status_code == 404

    def test_regression_via_job(self, client):
        r = client.post("/api/v1/regressions", headers=H, json={
            "skill": "commit-helper", "baseline": "v1",
            "candidate": "v2-bad", "tasks": "write-commit-msg",
            "rollouts": 1})
        assert r.status_code == 200
        body = r.json()
        assert body["job"] and body["planned"] == 2
        j = wait_job(client, body["job"])
        assert j["status"] == "completed"


class TestJobsRace:
    """Deterministic coverage for Jobs.submit() unique-index races —
    the CI flake that returned {} -> KeyError('id'). _insert is the
    injectable checkpoint; cross-instance submits exercise the real
    SQLite unique-index path."""

    def test_cross_instance_same_key_returns_winner(self, tmp_path):
        import sqlite3 as _sq, threading
        from web.backend.jobs import Jobs
        db = tmp_path / "jobs.sqlite"
        a, b = Jobs(db), Jobs(db)
        gate = threading.Event()
        j1 = a.submit("k", "shared", lambda h: gate.wait(5))
        try:
            # b's insert hits the partial index on a SEPARATE connection
            # while a's job is still active -> must return a's job
            j2 = b.submit("k", "shared", lambda h: None)
            assert j2["id"] == j1["id"]
            assert j2["status"] in ("queued", "running")
        finally:
            gate.set()

    def test_conflict_winner_finished_retries_fresh(
            self, tmp_path, monkeypatch):
        import sqlite3
        from web.backend.jobs import Jobs
        db = tmp_path / "jobs.sqlite"
        a, b = Jobs(db), Jobs(db)
        j1 = a.submit("k", "done-key", lambda h: None)
        for _ in range(200):
            if b.get(j1["id"])["status"] == "completed":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("competitor never finished")
        calls = [0]
        orig = b._insert

        def flaky(*args):
            calls[0] += 1
            if calls[0] == 1:
                raise sqlite3.IntegrityError("simulated")
            return orig(*args)

        monkeypatch.setattr(b, "_insert", flaky)
        j2 = b.submit("k", "done-key", lambda h: None)
        assert calls[0] >= 1
        assert j2["id"] and j2["id"] != j1["id"]
        assert j2["status"] in ("queued", "running", "completed")

    def test_persistent_conflict_raises_not_empty(
            self, tmp_path, monkeypatch):
        import sqlite3
        import pytest as _pytest
        from web.backend.jobs import Jobs, JobSubmitError
        b = Jobs(tmp_path / "jobs.sqlite")
        b.SUBMIT_ATTEMPTS = 3
        b.SUBMIT_RETRY_S = 0.001

        def always(*args):
            raise sqlite3.IntegrityError("simulated")

        monkeypatch.setattr(b, "_insert", always)
        with _pytest.raises(JobSubmitError):
            b.submit("k", "stuck", lambda h: None)

    def test_completed_key_reusable(self, tmp_path):
        from web.backend.jobs import Jobs
        a = Jobs(tmp_path / "jobs.sqlite")
        j1 = a.submit("k", "reuse", lambda h: None)
        for _ in range(200):
            if a.get(j1["id"])["status"] == "completed":
                break
            time.sleep(0.01)
        j2 = a.submit("k", "reuse", lambda h: None)
        assert j2["id"] != j1["id"]

    def test_submit_failure_maps_to_503(self, client, monkeypatch):
        from web.backend.jobs import Jobs, JobSubmitError

        def boom(*a, **k):
            raise JobSubmitError("simulated persistent conflict")

        monkeypatch.setattr(Jobs, "submit", boom)
        r = client.post("/api/v1/experiments/exp-503/run",
                        headers=H, json={})
        # exp doesn't exist -> 404, never reaches submit — make it first
        assert r.status_code == 404
        client.post("/api/v1/experiments", headers=H,
                    json={"id": "exp-503", "category": "capability"})
        exp = client.get("/api/v1/experiments/exp-503",
                         headers=H).json()["experiment"]
        exp["rollouts_per_arm"] = 1
        exp["tasks"] = ["write-commit-msg"]
        exp["arms"] = [{"name": "control", "skill": None},
                       {"name": "t", "skill": "commit-helper@v3-bp"}]
        client.put("/api/v1/experiments/exp-503/config",
                   headers=H, json=exp)
        r = client.post("/api/v1/experiments/exp-503/run",
                        headers=H, json={})
        assert r.status_code == 503
        assert "conflict" in r.json()["detail"]


class TestSuiteAPI:
    """Test Suite management — task/rubric/suite CRUD, fixtures,
    validation, datasets."""

    def test_task_crud_cycle(self, client):
        spec = {"id": "t-new", "kind": "performance",
                "prompt": "do the thing", "fixtures": [],
                "skill_relevance": {"expected": [], "unexpected": []},
                "deterministic_checks": [
                    {"type": "file-exists", "path": "OUTPUT.md"}]}
        r = client.post("/api/v1/tasks", headers=H, json=spec)
        assert r.status_code == 200, r.text
        assert client.get("/api/v1/tasks/t-new",
                          headers=H).json()["task"]["id"] == "t-new"
        spec["prompt"] = "do the thing differently"
        r = client.put("/api/v1/tasks/t-new", headers=H, json=spec)
        assert r.status_code == 200
        got = client.get("/api/v1/tasks/t-new", headers=H).json()
        assert "differently" in got["resolved_prompt"]
        # duplicate -> independent copy
        r = client.post("/api/v1/tasks/t-new/duplicate",
                        headers=H, json={"id": "t-new-copy"})
        assert r.status_code == 200
        # delete archives (unreferenced -> no force needed)
        r = client.delete("/api/v1/tasks/t-new-copy", headers=H)
        assert r.status_code == 200
        assert client.get("/api/v1/tasks/t-new-copy",
                          headers=H).status_code == 404
        assert client.get("/api/v1/tasks/t-new",
                          headers=H).status_code == 200

    def test_task_create_conflict_and_validation(self, client):
        client.post("/api/v1/tasks", headers=H,
                    json={"id": "dup"})
        r = client.post("/api/v1/tasks", headers=H,
                        json={"id": "dup"})
        assert r.status_code in (400, 409)
        r = client.post("/api/v1/tasks", headers=H,
                        json={"id": "../escape"})
        assert r.status_code in (400, 422)

    def test_task_delete_blocked_by_experiment_ref(self, client):
        # write-commit-msg is referenced by exp-trigger-wording
        r = client.delete("/api/v1/tasks/write-commit-msg",
                          headers=H)
        assert r.status_code in (400, 409)
        assert "referenced" in r.json()["detail"]
        r = client.delete("/api/v1/tasks/write-commit-msg?force=true",
                          headers=H)
        assert r.status_code == 200
        # archived, not unlinked — runs still inspectable
        assert client.get("/api/v1/tasks/write-commit-msg",
                          headers=H).status_code == 404

    def test_task_files_safety(self, client):
        tid = "files-task"
        client.post("/api/v1/tasks", headers=H, json={"id": tid})
        r = client.put(f"/api/v1/tasks/{tid}/file", headers=H,
                       json={"path": "src/app.py",
                             "content": "print(1)\n"})
        assert r.status_code == 200
        files = client.get(f"/api/v1/tasks/{tid}/files",
                           headers=H).json()
        assert any(f["path"] == "src/app.py" for f in files)
        got = client.get(f"/api/v1/tasks/{tid}/file?path=src/app.py",
                         headers=H).json()
        assert got["content"] == "print(1)\n"
        # traversal + task.yaml bypass both refused
        for bad in ("../x", "/etc/passwd", "task.yaml", "a/../../b"):
            r = client.put(f"/api/v1/tasks/{tid}/file", headers=H,
                           json={"path": bad, "content": "x"})
            assert r.status_code == 400, bad
        r = client.delete(
            f"/api/v1/tasks/{tid}/file?path=src/app.py", headers=H)
        assert r.status_code == 200

    def test_rubric_crud_and_ref_protection(self, client):
        rub = {"id": "r1", "criteria": [
            {"id": "ok", "weight": 1.0, "method": "deterministic",
             "check": "out.md", "scale": "1-5"},
            {"id": "judge", "weight": 2.0, "method": "llm-judge",
             "judge_prompt": "is it good", "scale": "1-5"}]}
        r = client.post("/api/v1/rubrics", headers=H, json=rub)
        assert r.status_code == 200, r.text
        got = client.get("/api/v1/rubrics/r1", headers=H).json()
        assert len(got["rubric"]["criteria"]) == 2
        assert any(i["severity"] == "warning"
                   for i in got["issues"])      # mock judge warns
        # task referencing it blocks delete
        client.post("/api/v1/tasks", headers=H,
                    json={"id": "uses-r1", "prompt": "x",
                          "rubric": "r1"})
        r = client.delete("/api/v1/rubrics/r1", headers=H)
        assert r.status_code in (400, 409)
        r = client.post("/api/v1/rubrics/r1/duplicate",
                        headers=H, json={"id": "r1-copy"})
        assert r.status_code == 200
        rub2 = {"id": "r1", "criteria": [
            {"id": "ok2", "weight": 0, "method": "deterministic"}]}
        r = client.put("/api/v1/rubrics/r1", headers=H, json=rub2)
        assert r.status_code == 200
        assert any("weight" in i["message"]
                   for i in r.json()["issues"])

    def test_suites_crud(self, client):
        r = client.post("/api/v1/suites", headers=H,
                        json={"id": "s1", "tasks": ["write-commit-msg"]})
        assert r.status_code == 200
        lst = client.get("/api/v1/suites", headers=H).json()
        assert lst[0]["id"] == "s1"
        r = client.put("/api/v1/suites/s1", headers=H,
                       json={"tasks": ["write-commit-msg",
                                       "unrelated-refactor"]})
        assert r.json()["tasks"] == ["write-commit-msg",
                                     "unrelated-refactor"]
        client.post("/api/v1/suites/s1/duplicate", headers=H,
                    json={"id": "s1-copy"})
        assert len(client.get("/api/v1/suites",
                              headers=H).json()) == 2
        client.delete("/api/v1/suites/s1-copy", headers=H)
        assert len(client.get("/api/v1/suites",
                              headers=H).json()) == 1

    def test_suite_validate(self, client):
        r = client.get("/api/v1/suite/validate", headers=H)
        assert r.status_code == 200
        j = r.json()
        assert "write-commit-msg" in j["tasks"]
        assert j["runnable"]["write-commit-msg"] is True

    def test_dataset_import_export_json(self, client):
        data = '[{"id":"imp-1","kind":"performance","prompt":"p"},' \
               ' {"id":"imp-2","kind":"bogus-kind"}]'
        prev = client.post("/api/v1/suite/import", headers=H,
                           json={"format": "json", "data": data})
        j = prev.json()
        assert len(j["ok"]) == 1 and len(j["bad"]) == 1
        # invalid dataset refuses to write anything
        r = client.post("/api/v1/suite/import", headers=H,
                        json={"format": "json", "data": data,
                              "confirm": True})
        assert r.status_code in (400, 422)
        assert client.get("/api/v1/tasks/imp-1",
                          headers=H).status_code == 404
        good = '[{"id":"imp-1","kind":"performance","prompt":"p"}]'
        r = client.post("/api/v1/suite/import", headers=H,
                        json={"format": "json", "data": good,
                              "confirm": True})
        assert r.json()["imported"] == ["imp-1"]
        # conflict: skip by default, overwrite when asked
        r = client.post("/api/v1/suite/import", headers=H,
                        json={"format": "json", "data": good,
                              "confirm": True})
        assert r.json()["skipped"] == ["imp-1"]
        r = client.post("/api/v1/suite/import", headers=H,
                        json={"format": "json", "data": good,
                              "confirm": True,
                              "on_conflict": "overwrite"})
        assert r.json()["imported"] == ["imp-1"]
        r = client.get("/api/v1/suite/export?format=json",
                       headers=H)
        assert "imp-1" in r.text

    def test_dataset_csv_roundtrip(self, client):
        r = client.get("/api/v1/suite/export?format=csv", headers=H)
        assert r.status_code == 200
        assert "id,kind,prompt" in r.text
        r = client.post("/api/v1/suite/import", headers=H,
                        json={"format": "csv", "data": r.text})
        j = r.json()
        assert j["bad"] == [] and j["parse_errors"] == []

    def test_historical_runs_survive_task_edit(self, client):
        # edit the task's prompt — recorded run evidence is untouched
        spec = client.get("/api/v1/tasks/unrelated-refactor",
                          headers=H).json()["task"]
        spec["prompt"] = "edited prompt"
        client.put("/api/v1/tasks/unrelated-refactor",
                   headers=H, json=spec)
        r = client.get("/api/v1/experiments/exp-trigger-wording/runs",
                       headers=H)
        assert r.status_code == 200 and r.json()
