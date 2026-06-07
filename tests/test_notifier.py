"""Tests for notifier (task-011) — mocked Telegram + SMTP."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional


@dataclass
class FakeResult:
    listing_id: str
    title: str
    url: str
    price: Optional[float]
    distance_km: Optional[float]
    relevance_score: int
    notified: bool = False
    seen: bool = False


def make_result(**kwargs) -> FakeResult:
    defaults = dict(
        listing_id="123456",
        title="Test listing",
        url="https://www.marktplaats.nl/a123456-test",
        price=100.0,
        distance_km=5.0,
        relevance_score=75,
    )
    defaults.update(kwargs)
    return FakeResult(**defaults)


class TestSendTelegram:
    @pytest.mark.asyncio
    async def test_no_token_returns_false(self):
        from marktplaats_bot import notifier
        from marktplaats_bot.config import settings

        original = settings.telegram_token
        settings.telegram_token = ""
        try:
            result = await notifier.send_telegram("test")
            assert result is False
        finally:
            settings.telegram_token = original

    @pytest.mark.asyncio
    async def test_sends_message_with_token(self):
        from marktplaats_bot import notifier
        from marktplaats_bot.config import settings

        mock_bot = AsyncMock()
        mock_bot.send_message = AsyncMock(return_value=None)

        with patch("marktplaats_bot.notifier.settings") as mock_settings:
            mock_settings.telegram_token = "fake-token"
            mock_settings.telegram_chat_id = "5157436441"
            with patch("telegram.Bot", return_value=mock_bot):
                result = await notifier.send_telegram("Hello Sir")
                assert result is True
                mock_bot.send_message.assert_called_once()


class TestNotifyNewResults:
    @pytest.mark.asyncio
    async def test_skips_low_score_results(self):
        from marktplaats_bot import notifier

        low_results = [make_result(relevance_score=30), make_result(relevance_score=45)]
        with patch.object(notifier, "send_telegram", new_callable=AsyncMock) as mock_send:
            await notifier.notify_new_results(1, low_results)
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_for_high_score_results(self):
        from marktplaats_bot import notifier

        results = [
            make_result(relevance_score=80, title="Great fiets"),
            make_result(relevance_score=70, title="Good fiets", listing_id="654321"),
        ]
        with patch.object(notifier, "send_telegram", new_callable=AsyncMock) as mock_send:
            await notifier.notify_new_results(1, results)
            mock_send.assert_called_once()
            call_text = mock_send.call_args[0][0]
            assert "Great fiets" in call_text or "Good fiets" in call_text

    @pytest.mark.asyncio
    async def test_max_3_results_in_message(self):
        from marktplaats_bot import notifier

        results = [
            make_result(relevance_score=90, listing_id=str(i), title=f"Item {i}")
            for i in range(5)
        ]
        with patch.object(notifier, "send_telegram", new_callable=AsyncMock) as mock_send:
            await notifier.notify_new_results(1, results)
            call_text = mock_send.call_args[0][0]
            # Should only reference 3 items (top 3)
            item_count = sum(1 for i in range(5) if f"Item {i}" in call_text)
            assert item_count <= 3

    @pytest.mark.asyncio
    async def test_marks_notified(self):
        from marktplaats_bot import notifier

        results = [make_result(relevance_score=80)]
        with patch.object(notifier, "send_telegram", new_callable=AsyncMock):
            await notifier.notify_new_results(1, results)
            assert results[0].notified is True


class TestEmailDigest:
    @pytest.mark.asyncio
    async def test_skips_when_smtp_not_configured(self):
        from marktplaats_bot import notifier
        from marktplaats_bot.config import settings

        original_host = settings.smtp_host
        original_user = settings.smtp_user
        settings.smtp_host = ""
        settings.smtp_user = ""
        try:
            # Should not raise
            await notifier.send_email_digest(None)
        finally:
            settings.smtp_host = original_host
            settings.smtp_user = original_user
