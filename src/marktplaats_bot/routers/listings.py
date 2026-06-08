import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Result
from ..schemas import ResultResponse, VerdictCreate

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.get("/unanalyzed", response_model=list[ResultResponse])
async def get_unanalyzed(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Return results that have not yet received an AI verdict."""
    q = await db.execute(
        select(Result).where(Result.ai_score.is_(None)).limit(limit)
    )
    return [ResultResponse.model_validate(r) for r in q.scalars().all()]


@router.post("/{result_id}/verdict", response_model=ResultResponse)
async def post_verdict(
    result_id: int,
    payload: VerdictCreate,
    db: AsyncSession = Depends(get_db),
):
    """Store an AI verdict (score + flags) for a result."""
    q = await db.execute(select(Result).where(Result.id == result_id))
    result = q.scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    result.ai_score = payload.ai_score
    result.ai_flags = json.dumps(payload.ai_flags)
    await db.commit()
    await db.refresh(result)
    return ResultResponse.model_validate(result)
