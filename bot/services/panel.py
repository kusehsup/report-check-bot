from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from bot.models import ReviewCard
from bot.services.normalize import merge_and_sort, normalize_payload

logger = logging.getLogger(__name__)
MOSCOW = ZoneInfo("Europe/Moscow")


class PanelAuthError(RuntimeError):
    """Panel session is missing or expired."""


class PanelClient:
    def __init__(
        self,
        *,
        base_url: str,
        refresh_token: str = "",
        access_token: str = "",
        server_id: int = 6,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.refresh_token = refresh_token.strip()
        self.access_token = access_token.strip()
        self.server_id = server_id
        self.timeout = timeout

    def _cookies(self) -> dict[str, str]:
        cookies: dict[str, str] = {}
        if self.refresh_token:
            cookies["refresh_token"] = self.refresh_token
        if self.access_token:
            cookies["access_token"] = self.access_token
        return cookies

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": (
                "Mozilla/5.0 (compatible; report-check-bot/0.1; +local)"
            ),
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def ensure_access_token(self) -> str:
        if not self.refresh_token and self.access_token:
            return self.access_token
        if not self.refresh_token:
            raise PanelAuthError("PANEL_REFRESH_NOW is empty")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/auth",
                cookies={"refresh_token": self.refresh_token},
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/",
                },
            )
        if response.status_code in (401, 403):
            raise PanelAuthError(
                "Сессия панели истекла. Обновите PANEL_REFRESH_NOW после входа."
            )
        if response.status_code >= 400:
            raise PanelAuthError(
                f"Не удалось обновить access token: HTTP {response.status_code}"
            )
        data = response.json()
        token = data.get("accessToken") or data.get("access_token")
        if not token:
            raise PanelAuthError("Ответ /api/v1/auth без accessToken")
        self.access_token = str(token)
        # capture rotated refresh cookie if present
        for cookie in response.cookies.jar:
            if cookie.name == "refresh_token" and cookie.value:
                self.refresh_token = cookie.value
            if cookie.name == "access_token" and cookie.value:
                self.access_token = cookie.value
        return self.access_token

    async def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        await self.ensure_access_token()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{path}",
                params=params,
                cookies=self._cookies(),
                headers=self._headers(),
            )
        if response.status_code in (401, 403):
            # one retry after forced refresh
            if self.refresh_token:
                self.access_token = ""
                await self.ensure_access_token()
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(
                        f"{self.base_url}{path}",
                        params=params,
                        cookies=self._cookies(),
                        headers=self._headers(),
                    )
        if response.status_code in (401, 403):
            raise PanelAuthError(
                "Нет доступа к логам панели. Обновите PANEL_REFRESH_NOW."
            )
        if response.status_code >= 400:
            body = response.text[:300]
            raise RuntimeError(f"Panel {path} HTTP {response.status_code}: {body}")
        return response.json()

    @staticmethod
    def day_bounds(day: date) -> tuple[str, str]:
        start = datetime.combine(day, time(0, 0), tzinfo=MOSCOW)
        end = datetime.combine(day, time(23, 59), tzinfo=MOSCOW)
        return start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M")

    async def fetch_report_log(self, day: date) -> Any:
        start, end = self.day_bounds(day)
        return await self._get_json(
            "/api/v1/report-log",
            {
                "serverId": self.server_id,
                "startDate": start,
                "endDate": end,
            },
        )

    async def fetch_player_requests_z(self, day: date) -> Any:
        start, end = self.day_bounds(day)
        return await self._get_json(
            "/api/v1/player-requests-z",
            {
                "serverId": self.server_id,
                "query": "",
                "category": "answer_text",
                "startTime": start,
                "endTime": end,
            },
        )

    async def fetch_day_cards(self, day: date) -> list[ReviewCard]:
        report_raw = await self.fetch_report_log(day)
        faq_raw = await self.fetch_player_requests_z(day)
        report_cards = normalize_payload(report_raw, "Report")
        faq_cards = normalize_payload(faq_raw, "FAQ")
        logger.info(
            "Loaded day=%s report=%s faq=%s",
            day.isoformat(),
            len(report_cards),
            len(faq_cards),
        )
        return merge_and_sort(report_cards, faq_cards)


def moscow_today() -> date:
    return datetime.now(MOSCOW).date()


def moscow_yesterday() -> date:
    return date.fromordinal(moscow_today().toordinal() - 1)


def encode_day_param(value: str) -> str:
    """Helper for debugging URL encoding (spaces -> %20)."""
    return quote(value, safe="")
