from __future__ import annotations

import json
import logging
from datetime import date, datetime, time
from pathlib import Path
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
        timeout: float = 120.0,
        fixture_dir: str | Path | None = None,
        prefer_fixtures: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.refresh_token = refresh_token.strip()
        self.access_token = access_token.strip()
        self.server_id = server_id
        self.timeout = timeout
        self.fixture_dir = Path(fixture_dir) if fixture_dir else None
        self.prefer_fixtures = prefer_fixtures
        self.used_fixtures = False

    def _cookie_header(self) -> str:
        parts: list[str] = []
        if self.refresh_token:
            parts.append(f"refresh_token={self.refresh_token}")
        if self.access_token:
            parts.append(f"access_token={self.access_token}")
        return "; ".join(parts)

    def _headers(self, *, include_cookie: bool = True, api_key: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
        }
        # Panel axios interceptor: X-API-KEY: Bearer <accessToken>
        if api_key and self.access_token:
            headers["X-API-KEY"] = f"Bearer {self.access_token}"
        if include_cookie and self._cookie_header():
            headers["Cookie"] = self._cookie_header()
        return headers

    async def ensure_access_token(self) -> str:
        if self.prefer_fixtures and self.fixture_dir:
            return self.access_token or "fixture"
        if not self.refresh_token and self.access_token:
            return self.access_token
        if not self.refresh_token:
            raise PanelAuthError("PANEL_REFRESH_NOW is empty")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/auth",
                headers={
                    **self._headers(include_cookie=False),
                    "Cookie": f"refresh_token={self.refresh_token}",
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
                headers=self._headers(api_key=True),
            )
        # Axios client refreshes when API says access JWT expired.
        expired = False
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001
                payload = None
            if isinstance(payload, dict) and payload.get("message") == (
                "JWT access token has expired"
            ):
                expired = True
        if response.status_code in (401, 403) or expired:
            if self.refresh_token:
                self.access_token = ""
                await self.ensure_access_token()
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(
                        f"{self.base_url}{path}",
                        params=params,
                        headers=self._headers(api_key=True),
                    )
        if response.status_code in (401, 403):
            raise PanelAuthError(
                "Нет доступа к логам панели (HTTP 403). "
                "Проверьте PANEL_REFRESH_NOW / X-API-KEY."
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

    def _load_fixture(self, name: str) -> Any:
        if not self.fixture_dir:
            raise RuntimeError("fixture_dir is not set")
        path = self.fixture_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    async def fetch_report_log(self, day: date) -> Any:
        if self.prefer_fixtures and self.fixture_dir:
            self.used_fixtures = True
            return self._load_fixture("report_log.json")
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
        if self.prefer_fixtures and self.fixture_dir:
            self.used_fixtures = True
            return self._load_fixture("player_requests_z.json")
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
        self.used_fixtures = False
        try:
            report_raw = await self.fetch_report_log(day)
            faq_raw = await self.fetch_player_requests_z(day)
        except PanelAuthError:
            if self.fixture_dir and not self.prefer_fixtures:
                logger.warning(
                    "Panel logs forbidden; falling back to fixtures in %s",
                    self.fixture_dir,
                )
                self.prefer_fixtures = True
                report_raw = await self.fetch_report_log(day)
                faq_raw = await self.fetch_player_requests_z(day)
            else:
                raise
        report_cards = normalize_payload(report_raw, "Report")
        faq_cards = normalize_payload(faq_raw, "FAQ")
        logger.info(
            "Loaded day=%s report=%s faq=%s fixtures=%s",
            day.isoformat(),
            len(report_cards),
            len(faq_cards),
            self.used_fixtures,
        )
        return merge_and_sort(report_cards, faq_cards)


def moscow_today() -> date:
    return datetime.now(MOSCOW).date()


def moscow_yesterday() -> date:
    return date.fromordinal(moscow_today().toordinal() - 1)


def encode_day_param(value: str) -> str:
    """Helper for debugging URL encoding (spaces -> %20)."""
    return quote(value, safe="")
