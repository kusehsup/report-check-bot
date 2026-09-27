from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from bot.models import ReviewCard

logger = logging.getLogger(__name__)
SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
)


class SheetsError(RuntimeError):
    pass


class SheetsClient:
    def __init__(
        self,
        *,
        spreadsheet_id: str,
        sheet_gid: int,
        service_account_path: str = "",
        service_account_json: str = "",
    ) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.sheet_gid = sheet_gid
        self._sheet_title: str | None = None
        creds = self._credentials(service_account_path, service_account_json)
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    @staticmethod
    def _credentials(path: str, raw_json: str) -> service_account.Credentials:
        if raw_json.strip():
            info = json.loads(raw_json)
            return service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES
            )
        if path.strip():
            file_path = Path(path).expanduser()
            if not file_path.is_file():
                raise SheetsError(f"Service account file not found: {file_path}")
            return service_account.Credentials.from_service_account_file(
                str(file_path), scopes=SCOPES
            )
        raise SheetsError(
            "Set SERVICE_ACCOUNT_PATH or GOOGLE_SERVICE_ACCOUNT_JSON"
        )

    def sheet_title(self) -> str:
        if self._sheet_title:
            return self._sheet_title
        meta = (
            self._service.spreadsheets()
            .get(spreadsheetId=self.spreadsheet_id, fields="sheets.properties")
            .execute()
        )
        for sheet in meta.get("sheets", []):
            props = sheet.get("properties") or {}
            if int(props.get("sheetId", -1)) == int(self.sheet_gid):
                title = props.get("title")
                if not title:
                    break
                self._sheet_title = str(title)
                return self._sheet_title
        raise SheetsError(f"Sheet gid={self.sheet_gid} not found in spreadsheet")

    def _range(self, a1: str) -> str:
        title = self.sheet_title().replace("'", "''")
        return f"'{title}'!{a1}"

    def read_all_rows(self) -> list[list[str]]:
        result = (
            self._service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=self._range("A:F"),
                majorDimension="ROWS",
            )
            .execute()
        )
        values = result.get("values") or []
        return [[str(cell) for cell in row] for row in values]

    @staticmethod
    def _row_dedupe_key(row: list[str]) -> tuple[str, str, str, str, str] | None:
        if len(row) < 5:
            return None
        date_s, type_s, admin, question, answer = row[:5]
        if not any(row[:5]):
            return None
        # skip summary notes without type
        if not type_s.strip() and not admin.strip():
            return None
        return (
            date_s.strip(),
            type_s.strip(),
            admin.strip().lower(),
            " ".join(question.split()).lower(),
            " ".join(answer.split()).lower(),
        )

    def existing_keys(self) -> set[tuple[str, str, str, str, str]]:
        keys: set[tuple[str, str, str, str, str]] = set()
        for row in self.read_all_rows()[1:]:
            key = self._row_dedupe_key(row)
            if key is not None:
                keys.add(key)
        return keys

    def filter_new_cards(self, cards: list[ReviewCard]) -> list[ReviewCard]:
        existing = self.existing_keys()
        return [card for card in cards if card.dedupe_key() not in existing]

    def append_verdict(self, card: ReviewCard, verdict: str) -> None:
        body: dict[str, Any] = {"values": [card.sheet_row(verdict)]}
        (
            self._service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.spreadsheet_id,
                range=self._range("A:F"),
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )
        logger.info(
            "Appended sheet row admin=%s type=%s verdict=%s",
            card.admin_name,
            card.answer_type,
            verdict,
        )
