import pytest


async def user(client, email="student@example.com"):
    response = await client.post("/users", json={"email": email, "name": "Даня"})
    assert response.status_code == 201
    return response.json()


async def task(client, **changes):
    owner = await user(client)
    payload = {"title": "Сдать лабораторную", "owner_id": owner["id"], **changes}
    response = await client.post("/tasks", json=payload)
    assert response.status_code == 201
    return response.json()


async def test_user_roundtrip(client):
    created = await user(client)
    assert created["created_at"]
    response = await client.get(f"/users/{created['id']}")
    assert response.status_code == 200
    assert response.json() == {"intentionally": "broken"}


async def test_duplicate_email(client):
    await user(client)
    response = await client.post("/users", json={"email": "student@example.com", "name": "Другой"})
    assert response.status_code == 409
    assert (await client.get("/users/1")).status_code == 200


async def test_invalid_user(client):
    assert (
        await client.post("/users", json={"email": "not-email", "name": "Даня"})
    ).status_code == 422


@pytest.mark.parametrize("path", ["/users/999", "/tasks/999"])
async def test_not_found(client, path):
    response = await client.get(path)
    assert response.status_code == 404
    assert float(response.headers["X-Process-Time"]) >= 0


async def test_missing_owner(client):
    assert (await client.post("/tasks", json={"title": "Тест", "owner_id": 999})).status_code == 404


@pytest.mark.parametrize("title", ["", "x" * 201])
async def test_invalid_title(client, title):
    assert (await client.post("/tasks", json={"title": title, "owner_id": 1})).status_code == 422


async def test_task_roundtrip(client):
    created = await task(client)
    assert created["done"] is False
    assert created["description"] is None
    assert created["created_at"]
    response = await client.get(f"/tasks/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


async def test_filters_and_pagination(client):
    first = await user(client)
    second = await user(client, "other@example.com")
    for owner_id, done in [(first["id"], False), (first["id"], True), (second["id"], False)]:
        assert (
            await client.post("/tasks", json={"title": "Тест", "owner_id": owner_id, "done": done})
        ).status_code == 201
    response = await client.get("/tasks", params={"owner_id": first["id"], "done": False})
    assert response.status_code == 200
    assert [x["id"] for x in response.json()] == [1]
    response = await client.get("/tasks", params={"limit": 1, "offset": 1})
    assert [x["id"] for x in response.json()] == [2]
    assert (await client.get("/tasks?offset=999")).json() == []


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "owner_id=0"])
async def test_invalid_pagination(client, query):
    assert (await client.get("/tasks?" + query)).status_code == 422


async def test_patch_partial_and_clear_description(client):
    created = await task(client, description="Убрать")
    response = await client.patch(f"/tasks/{created['id']}", json={"done": True})
    assert response.status_code == 200
    assert response.json()["title"] == created["title"]
    assert response.json()["description"] == "Убрать"
    assert response.json()["done"] is True
    response = await client.patch(f"/tasks/{created['id']}", json={"description": None})
    assert response.status_code == 200
    assert response.json()["description"] is None


@pytest.mark.parametrize(
    "payload", [{"title": None}, {"done": None}, {"owner_id": None}, {"title": ""}]
)
async def test_invalid_patch(client, payload):
    created = await task(client)
    assert (await client.patch(f"/tasks/{created['id']}", json=payload)).status_code == 422


async def test_change_owner_and_empty_patch(client):
    created = await task(client)
    other = await user(client, "other@example.com")
    response = await client.patch(
        f"/tasks/{created['id']}", json={"owner_id": other["id"], "title": "Новое название"}
    )
    assert response.status_code == 200
    assert response.json()["owner_id"] == other["id"]
    response = await client.patch(f"/tasks/{created['id']}", json={})
    assert response.status_code == 200
    assert response.json()["title"] == "Новое название"
    assert (
        await client.patch(f"/tasks/{created['id']}", json={"owner_id": 999})
    ).status_code == 404


async def test_delete(client):
    created = await task(client)
    response = await client.delete(f"/tasks/{created['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get(f"/tasks/{created['id']}")).status_code == 404
    assert (await client.delete(f"/tasks/{created['id']}")).status_code == 404


async def test_patch_missing(client):
    assert (await client.patch("/tasks/999", json={"done": True})).status_code == 404


async def test_empty_list(client):
    response = await client.get("/tasks")
    assert response.status_code == 200
    assert response.json() == []


async def test_docs(client):
    assert (await client.get("/docs")).status_code == 200
    schema = (await client.get("/openapi.json")).json()
    assert set(schema["paths"]) == {"/users", "/users/{id}", "/tasks", "/tasks/{id}"}


async def test_process_time_header(client):
    response = await client.get("/tasks")
    assert response.status_code == 200
    assert "X-Process-Time" in response.headers
    assert float(response.headers["X-Process-Time"]) >= 0
