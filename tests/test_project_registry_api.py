"""Tests for Real Project Registry and Workspace Management API.
===============================================================
Verifies that projects can be listed, registered, switched, and deleted,
and that the active project dynamically coordinates with WORKSPACE_ROOT.
"""

import os
import tempfile

from fastapi.testclient import TestClient

from antigravity_k.api.server import app

client = TestClient(app)


def test_list_projects_default():
    """GET /api/projects must return at least the current default workspace project."""
    res = client.get("/api/projects")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("ok") is True
    assert "projects" in data and isinstance(data["projects"], list)
    assert len(data["projects"]) >= 1

    active_p = [p for p in data["projects"] if p.get("is_active")]
    assert len(active_p) == 1, "There should be exactly one active project"


def test_create_and_switch_and_delete_project(monkeypatch):
    """Full lifecycle: create project, switch to it, verify, and remove."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # r27: registration follows the same allowed-root rule as chat; allow only this synthetic dir.
        monkeypatch.setenv("AGK_ALLOWED_ROOTS", os.path.realpath(tmpdir))
        proj_name = f"Test-Project-{os.path.basename(tmpdir)}"

        # 1. Create project
        res_create = client.post(
            "/api/projects",
            json={
                "name": proj_name,
                "path": tmpdir,
                "tasks": ["Task A", "Task B"],
            },
        )
        assert res_create.status_code == 200, res_create.text
        data_create = res_create.json()
        assert data_create.get("ok") is True
        created_proj = data_create["project"]
        assert created_proj["name"] == proj_name
        assert created_proj["is_active"] is True
        proj_id = created_proj["id"]

        # 2. Verify in list
        res_list = client.get("/api/projects")
        data_list = res_list.json()
        matching = [p for p in data_list["projects"] if p["id"] == proj_id]
        assert len(matching) == 1
        assert matching[0]["is_active"] is True

        # 3. Context endpoint reflection
        res_ctx = client.get("/api/workspace/context")
        data_ctx = res_ctx.json()
        assert data_ctx.get("project_name") == proj_name
        assert any(p["id"] == proj_id for p in data_ctx.get("projects", []))

        # 4. Switch back to default project
        res_switch = client.post(
            "/api/projects/switch",
            json={"project_id": "default"},
        )
        assert res_switch.status_code == 200, res_switch.text
        assert res_switch.json().get("ok") is True

        # 5. Delete the test project
        res_del = client.delete(f"/api/projects/{proj_id}")
        assert res_del.status_code == 200, res_del.text
        assert res_del.json().get("ok") is True

        # 6. Verify removed
        res_list_after = client.get("/api/projects")
        remaining_ids = [p["id"] for p in res_list_after.json()["projects"]]
        assert proj_id not in remaining_ids
