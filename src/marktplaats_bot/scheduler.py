"""
APScheduler job management.

Runs scrape+analyse 3× per day at 07:00/13:00/21:00 Amsterdam time.
Triggered immediately on new search creation via trigger_immediate_run().
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


async def run_all_searches(db_factory) -> None:
    """Scrape + analyse all active searches."""
    from sqlalchemy import select

    from .analyzer import analyse
    from .models import Result, Search
    from .scraper import scrape_bilingual

    async with db_factory() as db:
        result = await db.execute(select(Search).where(Search.active == True))
        searches = result.scalars().all()

    for search in searches:
        await run_single_search(search.id, db_factory)


async def run_single_search(search_id: int, db_factory) -> None:
    """Scrape + analyse one search by id and persist new results."""
    from sqlalchemy import select

    from .analyzer import analyse
    from .models import Result, Search
    from .scraper import scrape_bilingual

    async with db_factory() as db:
        r = await db.execute(select(Search).where(Search.id == search_id))
        search = r.scalar_one_or_none()
        if not search:
            logger.warning("run_single_search: search %d not found", search_id)
            return

        existing_ids_r = await db.execute(
            select(Result.listing_id).where(Result.search_id == search_id)
        )
        existing_ids = {row[0] for row in existing_ids_r.all()}

        # Collect price history for deal scoring
        prices_r = await db.execute(
            select(Result.price).where(Result.search_id == search_id, Result.price != None)
        )
        price_history = [row[0] for row in prices_r.all()]

        query_text = search.query_text
        max_budget = search.max_budget
        radius_km = search.radius_km
        postcode = search.postcode
        query_keywords = (
            ((search.nl_keywords or "") + " " + (search.en_keywords or "")).split()
        )
        required_specs = search.required_specs
        required_brands = search.required_brands
        excluded_brands = search.excluded_brands
        exclude_business = search.exclude_business

    logger.info("Running scrape for search %d: '%s'", search_id, query_text)

    try:
        listings, nl_query, en_query = await scrape_bilingual(
            query_text,
            postcode=postcode,
            radius_km=radius_km,
            max_price=max_budget,
        )
    except Exception as exc:
        logger.error("Scrape failed for search %d: %s", search_id, exc)
        return

    new_results: list[Result] = []
    for listing in listings:
        if listing.listing_id in existing_ids:
            continue

        result_obj = analyse(
            listing,
            query_keywords=query_keywords,
            required_specs=required_specs,
            required_brands=required_brands,
            excluded_brands=excluded_brands,
            max_budget=max_budget,
            exclude_business=exclude_business,
            price_history=price_history,
        )

        import json as _json
        row = Result(
            search_id=search_id,
            listing_id=listing.listing_id,
            title=listing.title,
            price=listing.price,
            distance_km=listing.distance_km,
            posted_at=listing.posted_at,
            url=listing.url,
            photo_count=listing.photo_count,
            description=listing.description,
            seller_type=result_obj.seller_type,
            relevance_score=result_obj.relevance_score,
            deal_score=result_obj.deal_score,
            quality_score=result_obj.quality_score,
            is_bidding=listing.is_bidding,
            image_urls=_json.dumps(listing.image_urls) if listing.image_urls else None,
        )
        new_results.append(row)

    if new_results:
        async with db_factory() as db:
            from sqlalchemy.exc import IntegrityError

            r = await db.execute(select(Search).where(Search.id == search_id))
            s = r.scalar_one_or_none()
            if s:
                s.nl_keywords = nl_query
                s.en_keywords = en_query
                s.last_run_at = datetime.utcnow()
                for row in new_results:
                    db.add(row)
                    try:
                        await db.flush()
                    except IntegrityError:
                        await db.rollback()
                        logger.debug(
                            "Search %d: duplicate listing_id %s, skipping",
                            search_id, row.listing_id,
                        )
                        # Re-attach search update after rollback
                        r2 = await db.execute(select(Search).where(Search.id == search_id))
                        s = r2.scalar_one_or_none()
                        if s:
                            s.nl_keywords = nl_query
                            s.en_keywords = en_query
                            s.last_run_at = datetime.utcnow()
                await db.commit()

        logger.info(
            "Search %d: added %d new results (total scraped: %d)",
            search_id,
            len(new_results),
            len(listings),
        )
        # Trigger notification for high-score results
        try:
            from .notifier import notify_new_results
            await notify_new_results(search_id, new_results)
        except Exception as exc:
            logger.warning("Notification failed for search %d: %s", search_id, exc)
    else:
        async with db_factory() as db:
            r = await db.execute(select(Search).where(Search.id == search_id))
            s = r.scalar_one_or_none()
            if s:
                s.last_run_at = datetime.utcnow()
                await db.commit()
        logger.info("Search %d: no new results (scraped %d, all known)", search_id, len(listings))


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="Europe/Amsterdam")
    return _scheduler


def start_scheduler(db_factory) -> None:
    """Start the APScheduler with 3×/day cron jobs."""
    scheduler = get_scheduler()
    if scheduler.running:
        return

    for hour in (7, 13, 21):
        scheduler.add_job(
            run_all_searches,
            trigger=CronTrigger(hour=hour, minute=0, timezone="Europe/Amsterdam"),
            args=[db_factory],
            id=f"scrape_{hour:02d}00",
            replace_existing=True,
            name=f"scrape-{hour:02d}:00",
        )

    scheduler.start()
    logger.info("Scheduler started: scrape jobs at 07:00, 13:00, 21:00 Amsterdam")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None


async def trigger_immediate_run(search_id: int, db_factory) -> None:
    """Kick off a background scrape immediately after a new search is created."""
    import asyncio

    asyncio.create_task(run_single_search(search_id, db_factory))
    logger.info("Immediate scrape triggered for search %d", search_id)
