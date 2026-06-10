import pytest


@pytest.mark.asyncio
async def test_list_searches_empty(client):
    response = await client.get("/api/searches")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_search(client):
    payload = {
        "query_text": "vintage fiets",
        "max_budget": 300.0,
        "radius_km": 20,
        "postcode": "3027CM",
        "ranking_mode": "precise_fit",
    }
    response = await client.post("/api/searches", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["query_text"] == "vintage fiets"
    assert data["max_budget"] == 300.0
    assert data["radius_km"] == 20
    assert data["active"] is True
    assert data["result_count"] == 0
    assert "id" in data


@pytest.mark.asyncio
async def test_create_search_minimal(client):
    response = await client.post("/api/searches", json={"query_text": "laptop"})
    assert response.status_code == 201
    data = response.json()
    assert data["query_text"] == "laptop"
    assert data["radius_km"] == 25  # default
    assert data["postcode"] == "3027CM"  # default


@pytest.mark.asyncio
async def test_get_search(client):
    create_resp = await client.post("/api/searches", json={"query_text": "bureau"})
    search_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/searches/{search_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == search_id


@pytest.mark.asyncio
async def test_get_search_not_found(client):
    response = await client.get("/api/searches/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_search(client):
    create_resp = await client.post("/api/searches", json={"query_text": "stoel"})
    search_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/searches/{search_id}")
    assert del_resp.status_code == 204

    # Should not appear in list (inactive)
    list_resp = await client.get("/api/searches")
    ids = [s["id"] for s in list_resp.json()]
    assert search_id not in ids


@pytest.mark.asyncio
async def test_get_results_empty(client):
    create_resp = await client.post("/api/searches", json={"query_text": "bank"})
    search_id = create_resp.json()["id"]

    results_resp = await client.get(f"/api/searches/{search_id}/results")
    assert results_resp.status_code == 200
    assert results_resp.json() == []


@pytest.mark.asyncio
async def test_invalid_ranking_mode(client):
    payload = {"query_text": "fiets", "ranking_mode": "invalid_mode"}
    response = await client.post("/api/searches", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_feedback(client):
    create_resp = await client.post("/api/searches", json={"query_text": "sofa"})
    search_id = create_resp.json()["id"]

    fb_resp = await client.post(
        f"/api/searches/{search_id}/feedback",
        json={"text": "budget max 400 euro"},
    )
    assert fb_resp.status_code == 201
    data = fb_resp.json()
    assert data["search_id"] == search_id
    assert "max_budget" in data["parsed_changes"]
    assert data["parsed_changes"]["max_budget"] == 400.0


@pytest.mark.asyncio
async def test_submit_feedback_not_found(client):
    response = await client.post(
        "/api/searches/9999/feedback",
        json={"text": "within 10 km"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_feedback_updates_radius(client):
    create_resp = await client.post("/api/searches", json={"query_text": "piano"})
    search_id = create_resp.json()["id"]

    await client.post(
        f"/api/searches/{search_id}/feedback",
        json={"text": "within 15 km please"},
    )
    get_resp = await client.get(f"/api/searches/{search_id}")
    assert get_resp.json()["radius_km"] == 15


@pytest.mark.asyncio
async def test_feedback_exclude_business(client):
    create_resp = await client.post("/api/searches", json={"query_text": "wasmachine"})
    search_id = create_resp.json()["id"]

    await client.post(
        f"/api/searches/{search_id}/feedback",
        json={"text": "too many business listings"},
    )
    get_resp = await client.get(f"/api/searches/{search_id}")
    assert get_resp.json()["exclude_business"] is True


@pytest.mark.asyncio
async def test_path_traversal_rejected(client):
    response = await client.get("/api/searches/../../etc/passwd")
    assert response.status_code in (400, 403, 404, 422)


@pytest.mark.asyncio
async def test_delete_correct_row(client):
    """Deleting search A by ID must set A inactive and leave B active."""
    resp_a = await client.post("/api/searches", json={"query_text": "racefiets"})
    assert resp_a.status_code == 201
    id_a = resp_a.json()["id"]

    resp_b = await client.post("/api/searches", json={"query_text": "mountainbike"})
    assert resp_b.status_code == 201
    id_b = resp_b.json()["id"]

    del_resp = await client.delete(f"/api/searches/{id_a}")
    assert del_resp.status_code == 204

    # A should return 404 (not found because it's inactive and the endpoint
    # checks active status via the list endpoint; direct GET still finds it)
    get_a = await client.get(f"/api/searches/{id_a}")
    assert get_a.status_code == 200
    assert get_a.json()["active"] is False

    get_b = await client.get(f"/api/searches/{id_b}")
    assert get_b.status_code == 200
    assert get_b.json()["active"] is True


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client):
    response = await client.delete("/api/searches/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_excludes_inactive(client):
    """After delete, GET /api/searches must not include the deleted search."""
    resp = await client.post("/api/searches", json={"query_text": "vintage camera"})
    assert resp.status_code == 201
    search_id = resp.json()["id"]

    del_resp = await client.delete(f"/api/searches/{search_id}")
    assert del_resp.status_code == 204

    list_resp = await client.get("/api/searches")
    assert list_resp.status_code == 200
    ids = [s["id"] for s in list_resp.json()]
    assert search_id not in ids
