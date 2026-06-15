import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import Result, Search
from ..schemas import ResultWithSearchResponse, ResultResponse, VerdictCreate

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.get("/unanalyzed", response_model=list[ResultWithSearchResponse])
async def get_unanalyzed(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Return results awaiting an AI verdict, with search context for the evaluating agent."""
    q = await db.execute(
        select(Result)
        .options(selectinload(Result.search))
        .where(Result.ai_score.is_(None))
        .limit(limit)
    )
    return [ResultWithSearchResponse.model_validate(r) for r in q.scalars().all()]


@router.post("/{result_id}/verdict", response_model=ResultResponse)
async def post_verdict(
    result_id: int,
    payload: VerdictCreate,
    db: AsyncSession = Depends(get_db),
):
    """Store an AI verdict (score, flags, reason) for a result."""
    q = await db.execute(select(Result).where(Result.id == result_id))
    result = q.scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    result.ai_score = payload.ai_score
    result.ai_flags = json.dumps(payload.ai_flags)
    result.ai_reason = payload.ai_reason

    # Update the search's last_analyzed_at timestamp
    sq = await db.execute(select(Search).where(Search.id == result.search_id))
    search = sq.scalar_one_or_none()
    if search:
        search.last_analyzed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(result)
    return ResultResponse.model_validate(result)
