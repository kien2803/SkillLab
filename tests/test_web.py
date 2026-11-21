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
