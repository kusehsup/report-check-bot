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
from bot.services.local_sheet import LocalSheetStore
from bot.services.panel import PanelAuthError, PanelClient
from bot.services.panel_session import PanelSessionStore
from bot.services.session import SessionStore
from bot.services.sheets import SheetsClient, SheetsError

logger = logging.getLogger(__name__)

# Keep access fresh and warn before refresh dies.
KEEPALIVE_SECONDS = 6 * 60 * 60
REFRESH_WARN_SECONDS = 3 * 24 * 60 * 60


def build_context(settings: Settings) -> AppContext:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir = settings.panel_fixture_dir.strip() or None
    session_store = PanelSessionStore(settings.panel_session_path)
    panel = PanelClient(
        base_url=settings.panel_base_url,
        refresh_token=settings.panel_refresh_token,
        access_token=settings.panel_access_token,
        server_id=settings.server_id,
        fixture_dir=fixture_dir,
        prefer_fixtures=settings.prefer_fixtures,
        session_store=session_store,
    )

    sheets = None
    sheet_backend = "none"
    if settings.has_google_credentials() and not settings.use_local_sheet:
        try:
            sheets = SheetsClient(
                spreadsheet_id=settings.spreadsheet_id,
                sheet_gid=settings.sheet_gid,
                service_account_path=settings.service_account_path,
                service_account_json=settings.google_service_account_json,
            )
            sheet_backend = "google"
        except SheetsError:
            logger.exception("Google Sheets credentials present but invalid")
            raise
    else:
        sheets = LocalSheetStore(settings.local_sheet_path)
        sheet_backend = "local_csv"
        logger.warning(
            "Using local CSV sheet at %s (set SERVICE_ACCOUNT_PATH for Google)",
            settings.local_sheet_path,
        )

    return AppContext(
        settings=settings,
        panel=panel,
        sheets=sheets,
        sessions=SessionStore(settings.session_db),
        sheet_backend=sheet_backend,
    )


async def _keepalive_loop(bot: Bot, ctx: AppContext) -> None:
    warned = False
    while True:
        try:
            await ctx.panel.ensure_access_token(force=True)
            left = ctx.panel.refresh_seconds_left()
            logger.info(
                "Panel keepalive ok; refresh_left=%s access_left=%s",
                left,
                ctx.panel.access_seconds_left(),
            )
            if left is not None and left < REFRESH_WARN_SECONDS and not warned:
                warned = True
                days = left / 86400
                text = (
                    f"⚠ Refresh панели истекает через ~{days:.1f} дн.\n"
                    "Зайдите на panel.exbot.su, скопируйте cookie "
                    "`refresh_token` и пришлите боту командой /panel_auth"
                )
                for admin_id in ctx.settings.admin_ids:
                    try:
                        await bot.send_message(admin_id, text)
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed to warn admin %s", admin_id)
            if left is not None and left >= REFRESH_WARN_SECONDS:
                warned = False
        except PanelAuthError as exc:
            logger.warning("Panel keepalive failed: %s", exc)
            for admin_id in ctx.settings.admin_ids:
                try:
                    await bot.send_message(
                        admin_id,
                        f"Сессия панели недоступна.\n{exc}\n"
                        "Команда: /panel_auth",
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to notify admin %s", admin_id)
        except Exception:  # noqa: BLE001
            logger.exception("Panel keepalive crashed")
        await asyncio.sleep(KEEPALIVE_SECONDS)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    get_settings.cache_clear()
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
    try:
        await ctx.panel.ensure_access_token(force=True)
        logger.info(
            "Panel session ready; refresh_left=%s",
            ctx.panel.refresh_seconds_left(),
        )
    except PanelAuthError as exc:
        logger.warning("Panel session not ready at startup: %s", exc)

    logger.info(
        "Starting @%s id=%s sheets=%s fixtures=%s",
        me.username,
        me.id,
        ctx.sheet_backend,
        bool(settings.panel_fixture_dir),
    )
    asyncio.create_task(_keepalive_loop(bot, ctx))
    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
