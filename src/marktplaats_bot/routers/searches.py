import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal, get_db
from ..feedback import parse_feedback as _parse_feedback_full
from ..models import Search, Result, Feedback
from ..schemas import SearchCreate, SearchQueryPatch, SearchResponse, ResultResponse, FeedbackCreate, FeedbackPatch, FeedbackResponse

router = APIRouter(prefix="/api/searches", tags=["searches"])

RANKING_MODES = {
    "precise_fit": lambda r: -r.relevance_score,
    "mispricing": lambda r: -r.deal_score,
    "time_in_market": lambda r: r.posted_at or float("inf"),
    "popularity": lambda r: -r.photo_count,
    "distance": lambda r: r.distance_km if r.distance_km is not None else float("inf"),
}


@router.get("", response_model=list[SearchResponse])
async def list_searches(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Search).where(Search.active == True))
    searches = result.scalars().all()
    out = []
    for s in searches:
        count_result = await db.execute(select(func.count(Result.id)).where(Result.search_id == s.id))
        count = count_result.scalar() or 0
        fb_result = await db.execute(
            select(func.count(Feedback.id), func.max(Feedback.created_at))
            .where(Feedback.search_id == s.id)
        )
        fb_count, last_fb_at = fb_result.one()
        out.append(_build_search_response(s, count, int(fb_count or 0), last_fb_at))
    return out


@router.post("", response_model=SearchResponse, status_code=201)
async def create_search(payload: SearchCreate, db: AsyncSession = Depends(get_db)):
    search = Search(
        query_text=payload.query_text,
        max_budget=payload.max_budget,
        radius_km=payload.radius_km,
        postcode=payload.postcode,
        max_age_years=payload.max_age_years,
        exclude_business=payload.exclude_business,
        relevance_threshold=payload.relevance_threshold,
        ranking_mode=payload.ranking_mode,
    )
    search.required_specs = payload.required_specs
    search.required_brands = payload.required_brands
    search.excluded_brands = payload.excluded_brands
    db.add(search)
    await db.commit()
    await db.refresh(search)

    # Trigger immediate scrape in background
    try:
        from ..scheduler import trigger_immediate_run
        await trigger_immediate_run(search.id, AsyncSessionLocal)
    except Exception:
        pass  # Non-fatal — scheduled runs will pick it up
    return _build_search_response(search, 0)


@router.get("/unenhanced", response_model=list[SearchResponse])
async def get_unenhanced(db: AsyncSession = Depends(get_db)):
    """Return active searches that have not yet had their query enhanced by AI."""
    result = await db.execute(
        select(Search).where(Search.active == True, Search.query_enhanced == False)
    )
    searches = result.scalars().all()
    out = []
    for s in searches:
        count_result = await db.execute(select(func.count(Result.id)).where(Result.search_id == s.id))
        count = count_result.scalar() or 0
        out.append(_build_search_response(s, count))
    return out


@router.get("/{search_id}", response_model=SearchResponse)
async def get_search(search_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Search).where(Search.id == search_id))
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    count_result = await db.execute(select(func.count(Result.id)).where(Result.search_id == search_id))
    count = count_result.scalar() or 0
    fb_result = await db.execute(
        select(func.count(Feedback.id), func.max(Feedback.created_at))
        .where(Feedback.search_id == search_id)
    )
    fb_count, last_fb_at = fb_result.one()
    return _build_search_response(search, count, int(fb_count or 0), last_fb_at)


@router.delete("/{search_id}", status_code=204)
async def delete_search(search_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Search).where(Search.id == search_id))
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    search.active = False
    await db.commit()


@router.get("/{search_id}/results", response_model=list[ResultResponse])
async def get_results(
    search_id: int,
    ranking_mode: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    search_result = await db.execute(select(Search).where(Search.id == search_id))
    search = search_result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    results_q = await db.execute(select(Result).where(Result.search_id == search_id))
    results = list(results_q.scalars().all())

    mode = ranking_mode or search.ranking_mode
    if mode not in RANKING_MODES:
        mode = "precise_fit"
    results.sort(key=RANKING_MODES[mode])

    return [ResultResponse.model_validate(r) for r in results]


@router.post("/{search_id}/results/{result_id}/seen", status_code=200)
async def mark_seen(search_id: int, result_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Result).where(Result.id == result_id, Result.search_id == search_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Result not found")
    row.seen = True
    await db.commit()
    return {"ok": True}


@router.post("/run-now", status_code=202)
async def trigger_run_all():
    """Trigger an immediate scrape run for all active searches."""
    import asyncio
    from ..scheduler import run_all_searches
    asyncio.create_task(run_all_searches(AsyncSessionLocal))
    return {"status": "triggered"}


@router.post("/{search_id}/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    search_id: int, payload: FeedbackCreate, db: AsyncSession = Depends(get_db)
):
    search_result = await db.execute(select(Search).where(Search.id == search_id))
    search = search_result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    parsed = _parse_feedback_full(payload.text)
    _apply_parsed_to_search(search, parsed)

    fb = Feedback(search_id=search_id, text=payload.text)
    fb.parsed_changes = parsed
    db.add(fb)
    await db.commit()
    await db.refresh(fb)

    return FeedbackResponse(
        id=fb.id,
        search_id=fb.search_id,
        text=fb.text,
        parsed_changes=fb.parsed_changes,
        created_at=fb.created_at,
    )


@router.get("/{search_id}/feedback", response_model=list[FeedbackResponse])
async def list_feedback(search_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Feedback).where(Feedback.search_id == search_id).order_by(Feedback.created_at)
    )
    feedbacks = result.scalars().all()
    return [
        FeedbackResponse(
            id=f.id, search_id=f.search_id, text=f.text,
            parsed_changes=f.parsed_changes, created_at=f.created_at,
        )
        for f in feedbacks
    ]


@router.patch("/{search_id}/feedback/{fb_id}", response_model=FeedbackResponse)
async def update_feedback(
    search_id: int, fb_id: int, payload: FeedbackPatch, db: AsyncSession = Depends(get_db)
):
    if payload.text is None and payload.parsed_changes is None:
        raise HTTPException(status_code=400, detail="Provide text or parsed_changes")

    fb_result = await db.execute(
        select(Feedback).where(Feedback.id == fb_id, Feedback.search_id == search_id)
    )
    fb = fb_result.scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")

    search_result = await db.execute(select(Search).where(Search.id == search_id))
    search = search_result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    if payload.text is not None:
        fb.text = payload.text

    new_parsed = payload.parsed_changes if payload.parsed_changes is not None else _parse_feedback_full(fb.text)
    fb.parsed_changes = new_parsed
    _apply_parsed_to_search(search, new_parsed)

    await db.commit()
    await db.refresh(fb)
    return FeedbackResponse(
        id=fb.id, search_id=fb.search_id, text=fb.text,
        parsed_changes=fb.parsed_changes, created_at=fb.created_at,
    )


@router.delete("/{search_id}/feedback/{fb_id}", status_code=204)
async def delete_feedback(
    search_id: int, fb_id: int, db: AsyncSession = Depends(get_db)
):
    fb_result = await db.execute(
        select(Feedback).where(Feedback.id == fb_id, Feedback.search_id == search_id)
    )
    fb = fb_result.scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    await db.delete(fb)
    await db.commit()


@router.patch("/{search_id}/query", response_model=SearchResponse)
async def patch_search_query(
    search_id: int, payload: SearchQueryPatch, db: AsyncSession = Depends(get_db)
):
    """Apply AI-enhanced query parameters to a search and mark it as enhanced."""
    result = await db.execute(select(Search).where(Search.id == search_id))
    search = result.scalar_one_or_none()
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    if payload.nl_keywords is not None:
        search.nl_keywords = payload.nl_keywords
    if payload.en_keywords is not None:
        search.en_keywords = payload.en_keywords
    if payload.required_brands is not None:
        search.required_brands = payload.required_brands
    if payload.excluded_brands is not None:
        search.excluded_brands = payload.excluded_brands
    if payload.required_specs is not None:
        search.required_specs = payload.required_specs
    if payload.relevance_threshold is not None:
        search.relevance_threshold = payload.relevance_threshold
    search.query_enhanced = True

    await db.commit()
    await db.refresh(search)

    count_result = await db.execute(select(func.count(Result.id)).where(Result.search_id == search_id))
    count = count_result.scalar() or 0
    return _build_search_response(search, count)


def _build_search_response(
    s: Search, count: int, feedback_count: int = 0, last_feedback_at=None
) -> SearchResponse:
    return SearchResponse(
        id=s.id,
        query_text=s.query_text,
        nl_keywords=s.nl_keywords,
        en_keywords=s.en_keywords,
        max_budget=s.max_budget,
        radius_km=s.radius_km,
        postcode=s.postcode,
        max_age_years=s.max_age_years,
        required_specs=s.required_specs,
        required_brands=s.required_brands,
        excluded_brands=s.excluded_brands,
        exclude_business=s.exclude_business,
        relevance_threshold=s.relevance_threshold,
        ranking_mode=s.ranking_mode,
        active=s.active,
        query_enhanced=s.query_enhanced,
        created_at=s.created_at,
        last_run_at=s.last_run_at,
        last_analyzed_at=s.last_analyzed_at,
        result_count=count,
        feedback_count=feedback_count,
        last_feedback_at=last_feedback_at,
    )


def _remove_keyword(keywords: str, kw: str) -> str:
    """Remove all whole-word occurrences of kw from a keyword string."""
    pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
    result = pattern.sub("", keywords)
    return re.sub(r"\s{2,}", " ", result).strip()


def _apply_parsed_to_search(search: Search, parsed: dict) -> None:
    if "max_budget" in parsed:
        search.max_budget = parsed["max_budget"]
    if "radius_km" in parsed:
        search.radius_km = parsed["radius_km"]
    if "exclude_business" in parsed:
        search.exclude_business = parsed["exclude_business"]
    if "relevance_threshold" in parsed:
        search.relevance_threshold = parsed["relevance_threshold"]
    if "max_age_years" in parsed:
        search.max_age_years = parsed["max_age_years"]
    if "add_required_brands" in parsed:
        brands = search.required_brands
        for b in parsed["add_required_brands"]:
            if b not in brands:
                brands.append(b)
        search.required_brands = brands
    if "add_excluded_brands" in parsed:
        brands = search.excluded_brands
        for b in parsed["add_excluded_brands"]:
            if b not in brands:
                brands.append(b)
        search.excluded_brands = brands
    if "add_required_specs" in parsed:
        specs = search.required_specs
        for s in parsed["add_required_specs"]:
            if s not in specs:
                specs.append(s)
        search.required_specs = specs
    if "remove_keywords" in parsed:
        for kw in parsed["remove_keywords"]:
            if search.nl_keywords:
                search.nl_keywords = _remove_keyword(search.nl_keywords, kw)
            if search.en_keywords:
                search.en_keywords = _remove_keyword(search.en_keywords, kw)
    if "add_keywords" in parsed:
        for kw in parsed["add_keywords"]:
            if search.nl_keywords and kw not in search.nl_keywords:
                search.nl_keywords = f"{search.nl_keywords} {kw}".strip()
            if search.en_keywords and kw not in search.en_keywords:
                search.en_keywords = f"{search.en_keywords} {kw}".strip()

