import pytest
import pytest_asyncio
from httpx import AsyncClient

from marktplaats_bot.models import Result, Search


async def _make_search(db_session):
    s = Search(query_text="test", postcode="1234AB")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    return s


async def _make_result(db_session, search_id, *, ai_score=None):
    r = Result(
        search_id=search_id,
        listing_id="abc123",
        title="Test listing",
        url="https://marktplaats.nl/v/test/1",
        ai_score=ai_score,
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


@pytest.mark.asyncio
async def test_unanalyzed_empty(client: AsyncClient):
    resp = await client.get("/api/listings/unanalyzed")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_unanalyzed_returns_results_without_score(client: AsyncClient, db_session):
    s = await _make_search(db_session)
    await _make_result(db_session, s.id, ai_score=None)
    await _make_result(db_session, s.id, ai_score=7)

    resp = await client.get("/api/listings/unanalyzed")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ai_score"] is None


@pytest.mark.asyncio
async def test_post_verdict(client: AsyncClient, db_session):
    s = await _make_search(db_session)
    r = await _make_result(db_session, s.id)

    resp = await client.post(
        f"/api/listings/{r.id}/verdict",
        json={"ai_score": 8, "ai_flags": ["good condition", "fair price"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_score"] == 8
    assert data["ai_flags"] == ["good condition", "fair price"]


@pytest.mark.asyncio
async def test_post_verdict_not_found(client: AsyncClient):
    resp = await client.post("/api/listings/9999/verdict", json={"ai_score": 5, "ai_flags": []})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_verdict_invalid_score(client: AsyncClient, db_session):
    s = await _make_search(db_session)
    r = await _make_result(db_session, s.id)

    resp = await client.post(f"/api/listings/{r.id}/verdict", json={"ai_score": 11, "ai_flags": []})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unanalyzed_includes_search_metadata(client: AsyncClient, db_session):
    s = Search(
        query_text="Datsun 280z",
        postcode="3027CM",
        max_budget=5000.0,
        radius_km=50,
        exclude_business=True,
    )
    s.required_specs = ["hardtop"]
    s.required_brands = ["Datsun"]
    s.excluded_brands = ["replica"]
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    r = Result(
        search_id=s.id,
        listing_id="z123",
        title="Datsun 280z project",
        url="https://marktplaats.nl/v/test/z123",
    )
    db_session.add(r)
    await db_session.commit()

    resp = await client.get("/api/listings/unanalyzed")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    meta = data[0]["search"]
    assert meta["query_text"] == "Datsun 280z"
    assert meta["max_budget"] == 5000.0
    assert meta["radius_km"] == 50
    assert meta["exclude_business"] is True
    assert "hardtop" in meta["required_specs"]
    assert "Datsun" in meta["required_brands"]
    assert "replica" in meta["excluded_brands"]


@pytest.mark.asyncio
async def test_unanalyzed_limit(client: AsyncClient, db_session):
    s = await _make_search(db_session)
    for i in range(5):
        r = Result(
            search_id=s.id,
            listing_id=f"id{i}",
            title=f"Listing {i}",
            url=f"https://marktplaats.nl/v/test/{i}",
        )
        db_session.add(r)
    await db_session.commit()

    resp = await client.get("/api/listings/unanalyzed?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3
