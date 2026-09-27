from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import Settings, get_settings
from bot.context import AppContext, set_app
from bot.handlers import router
from bot.middlewares import AccessMiddleware
from bot.services.panel import PanelClient
from bot.services.session import SessionStore
from bot.services.sheets import SheetsClient, SheetsError

logger = logging.getLogger(__name__)


def build_context(settings: Settings) -> AppContext:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    panel = PanelClient(
        base_url=settings.panel_base_url,
        refresh_token=settings.panel_refresh_token,
        access_token=settings.panel_access_token,
        server_id=settings.server_id,
    )
    sheets: SheetsClient | None = None
    if settings.has_google_credentials():
        try:
            sheets = SheetsClient(
                spreadsheet_id=settings.spreadsheet_id,
                sheet_gid=settings.sheet_gid,
                service_account_path=settings.service_account_path,
                service_account_json=settings.google_service_account_json,
            )
        except SheetsError:
            logger.exception("Google Sheets credentials present but invalid")
            raise
    else:
        logger.warning(
            "Google credentials missing — review UI works, sheet append disabled"
        )

    return AppContext(
        settings=settings,
        panel=panel,
        sheets=sheets,
        sessions=SessionStore(settings.session_db),
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    settings = get_settings()
    ctx = build_context(settings)
    set_app(ctx)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AccessMiddleware(settings))
    dp.callback_query.middleware(AccessMiddleware(settings))
    dp.include_router(router)

    me = await bot.get_me()
    logger.info("Starting @%s; sheets=%s", me.username, ctx.sheets is not None)
    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
