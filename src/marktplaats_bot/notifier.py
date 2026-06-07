"""
Notifier — Telegram alerts and daily email digest.

Telegram: sends top 3 high-score new results immediately.
Email: daily digest at 21:00 via APScheduler (scheduled in main.py).
Both skip already-notified listing_ids.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .config import settings

if TYPE_CHECKING:
    from .models import Result

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------


async def send_telegram(text: str) -> bool:
    """Send *text* to Sir's Telegram chat. Returns True on success."""
    if not settings.telegram_token:
        logger.warning("TELEGRAM_TOKEN not set, skipping Telegram notification")
        return False
    try:
        import telegram

        bot = telegram.Bot(token=settings.telegram_token)
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return True
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


async def notify_new_results(search_id: int, new_results: list) -> None:
    """Send a Telegram alert for any new results with relevance_score ≥ threshold."""
    high_score = [r for r in new_results if r.relevance_score >= 60]
    if not high_score:
        return

    # Top 3 by relevance
    top3 = sorted(high_score, key=lambda r: -r.relevance_score)[:3]

    lines = [f"🔍 <b>Marktplaats: {len(high_score)} new match(es) found</b> (search #{search_id})\n"]
    for i, r in enumerate(top3, 1):
        price_str = f"€{r.price:.0f}" if r.price else "?"
        dist_str = f"{r.distance_km:.0f} km" if r.distance_km else "?"
        lines.append(
            f"{i}. <b>{r.title}</b>\n"
            f"   {price_str} · {dist_str} · relevance {r.relevance_score}/100\n"
            f"   <a href=\"{r.url}\">{r.url}</a>"
        )

    await send_telegram("\n".join(lines))

    # Mark as notified (best-effort — caller persists via db)
    for r in top3:
        r.notified = True


# ---------------------------------------------------------------------------
# Email digest
# ---------------------------------------------------------------------------


async def send_email_digest(db_factory) -> None:
    """Build and send a daily digest email to Sir."""
    if not settings.smtp_host or not settings.smtp_user:
        logger.warning("SMTP not configured, skipping email digest")
        return

    from sqlalchemy import select

    from .models import Result, Search

    async with db_factory() as db:
        result = await db.execute(select(Search).where(Search.active == True))
        searches = result.scalars().all()

        body_parts: list[str] = ["Marktplaats Bot — Daily Digest\n" + "=" * 50 + "\n"]

        for search in searches:
            r = await db.execute(
                select(Result)
                .where(Result.search_id == search.id)
                .order_by(Result.relevance_score.desc())
                .limit(10)
            )
            results = r.scalars().all()
            if not results:
                continue

            body_parts.append(f"\n### {search.query_text} ###")
            body_parts.append(f"Budget: €{search.max_budget or '?'} | Radius: {search.radius_km} km\n")

            for row in results:
                price_str = f"€{row.price:.0f}" if row.price else "?"
                dist_str = f"{row.distance_km:.0f} km" if row.distance_km else "?"
                seen_marker = " [seen]" if row.seen else ""
                body_parts.append(
                    f"  [{row.relevance_score:3d}] {row.title[:60]:<60} "
                    f"{price_str:>8} | {dist_str:>8}{seen_marker}\n"
                    f"        {row.url}"
                )

    body = "\n".join(body_parts)

    try:
        import aiosmtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "Marktplaats Bot — Daily Digest"
        msg["From"] = settings.smtp_from or settings.smtp_user
        msg["To"] = settings.notify_email

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("Daily digest sent to %s", settings.notify_email)
    except Exception as exc:
        logger.error("Email digest failed: %s", exc)
