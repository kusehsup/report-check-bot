from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    bot_token: str = Field(
        validation_alias=AliasChoices("BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
    )
    admin_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list,
        validation_alias=AliasChoices("ADMIN_IDS"),
    )

    panel_refresh_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "PANEL_REFRESH_NOW",
            "PANEL_REFRESH_TOKEN",
        ),
    )
    panel_access_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "PANEL_ACCESS_NOW",
            "PANEL_ACCESS_TOKEN",
        ),
    )
    panel_base_url: str = Field(
        default="https://panel.exbot.su",
        validation_alias=AliasChoices("PANEL_BASE_URL"),
    )
    server_id: int = Field(default=6, validation_alias=AliasChoices("SERVER_ID"))

    service_account_path: str = Field(
        default="",
        validation_alias=AliasChoices("SERVICE_ACCOUNT_PATH"),
    )
    google_service_account_json: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_SERVICE_ACCOUNT_JSON"),
    )
    spreadsheet_id: str = Field(
        default="1wfd3TNHFEY6T3MXyjiUPqzNUsnwWaNhElaq8RLAz-PI",
        validation_alias=AliasChoices("SPREADSHEET_ID"),
    )
    sheet_gid: int = Field(
        default=1296662959,
        validation_alias=AliasChoices("SHEET_GID"),
    )

    data_dir: Path = Field(default=Path("./data"), validation_alias=AliasChoices("DATA_DIR"))

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        if isinstance(value, int):
            return [value]
        text = str(value).strip()
        if not text:
            return []
        return [int(part.strip()) for part in text.split(",") if part.strip()]

    @model_validator(mode="after")
    def require_panel_auth(self) -> Settings:
        if not self.panel_refresh_token and not self.panel_access_token:
            raise ValueError(
                "Set PANEL_REFRESH_NOW (preferred) or PANEL_ACCESS_NOW"
            )
        return self

    @property
    def session_db(self) -> Path:
        return self.data_dir / "sessions.db"

    def has_google_credentials(self) -> bool:
        if self.google_service_account_json.strip():
            return True
        if self.service_account_path.strip():
            return Path(self.service_account_path).expanduser().is_file()
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
