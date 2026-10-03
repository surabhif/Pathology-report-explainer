"""Role / permission tests — expect 401/403 where appropriate."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/admin/progress")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_annotator_forbidden_on_admin(
    client: AsyncClient, annotator_headers: dict[str, str]
):
    resp = await client.get("/api/admin/progress", headers=annotator_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_clinician_forbidden_on_admin(
    client: AsyncClient, clinician_headers: dict[str, str]
):
    resp = await client.post(
        "/api/admin/invites",
        headers=clinician_headers,
        json={
            "email": "x@example.com",
            "name": "X",
            "role": "annotator",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_view_progress(client: AsyncClient, admin_headers: dict[str, str]):
    resp = await client.get("/api/admin/progress", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reports"] >= 6
    assert data["total_generations"] >= 1


@pytest.mark.asyncio
async def test_annotator_can_list_tasks_but_not_export_csv(
    client: AsyncClient, annotator_headers: dict[str, str]
):
    tasks = await client.get("/api/annotate/tasks", headers=annotator_headers)
    assert tasks.status_code == 200
    assert isinstance(tasks.json(), list)

    csv_resp = await client.get("/api/results/export.csv", headers=annotator_headers)
    assert csv_resp.status_code == 403


@pytest.mark.asyncio
async def test_clinician_can_list_review_tasks(
    client: AsyncClient, clinician_headers: dict[str, str]
):
    resp = await client.get("/api/review/tasks", headers=clinician_headers)
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) >= 1


@pytest.mark.asyncio
async def test_clinician_task_hides_model_details(
    client: AsyncClient, clinician_headers: dict[str, str]
):
    tasks = (await client.get("/api/review/tasks", headers=clinician_headers)).json()
    task_id = tasks[0]["id"]
    detail = await client.get(f"/api/review/tasks/{task_id}", headers=clinician_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body.get("report_text")
    assert body.get("explanation")
    # Model/prompt must not be exposed on clinician payload
    assert "provider" not in body or body.get("provider") is None
    assert "model" not in body
    assert "prompt_extract_version" not in body


@pytest.mark.asyncio
async def test_annotator_task_has_report_no_generation(
    client: AsyncClient, annotator_headers: dict[str, str]
):
    tasks = (await client.get("/api/annotate/tasks", headers=annotator_headers)).json()
    task_id = tasks[0]["id"]
    detail = await client.get(f"/api/annotate/tasks/{task_id}", headers=annotator_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["report"] is not None
    assert body["report"]["report_text"]
    assert "facts" not in body or body.get("facts") is None
    assert "explanation" not in body or body.get("explanation") is None


@pytest.mark.asyncio
async def test_public_explain_works(client: AsyncClient):
    reports = await client.get("/api/public/reports")
    assert reports.status_code == 200
    rid = reports.json()[0]["id"]
    expl = await client.get(f"/api/public/reports/{rid}/explain")
    assert expl.status_code == 200
    data = expl.json()
    assert data["facts"]
    assert data["explanation"]["sentences"]


@pytest.mark.asyncio
async def test_redeem_invalid_token(client: AsyncClient):
    resp = await client.post("/api/auth/redeem", json={"token": "NOPE"})
    assert resp.status_code == 401
