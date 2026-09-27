from __future__ import annotations

import html
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.context import get_app
from bot.services.panel import PanelAuthError

logger = logging.getLogger(__name__)
router = Router(name="panel_auth")

_AWAITING_REFRESH: set[int] = set()
_JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


def _esc(value: object) -> str:
    return html.escape(str(value))


def _looks_like_jwt(text: str) -> bool:
    return bool(_JWT_RE.match(text.strip()))


@router.message(Command("panel_status"))
async def cmd_panel_status(message: Message) -> None:
    app = get_app()
    store = app.panel.session_store
    if store is None:
        await message.answer("Файловое хранение сессии не настроено.")
        return
    text = store.status_text()
    left = app.panel.refresh_seconds_left()
    if left is not None and left < 3 * 24 * 3600:
        text += "\n\n⚠ Скоро понадобится /panel_auth"
    await message.answer(text)


@router.message(Command("panel_auth"))
async def cmd_panel_auth(message: Message, command: CommandObject) -> None:
    app = get_app()
    token = (command.args or "").strip()
    if token:
        await _apply_refresh(message, token)
        return
    _AWAITING_REFRESH.add(message.chat.id)
    await message.answer(
        "Пришлите следующим сообщением cookie <code>refresh_token</code> "
        "с panel.exbot.su (DevTools → Application → Cookies).\n"
        "Access присылать не нужно — бот обновит его сам.",
    )


@router.message(F.text.func(lambda t: bool(t) and _looks_like_jwt(t)))
async def receive_refresh_jwt(message: Message) -> None:
    text = (message.text or "").strip()
    # Accept JWT either while awaiting /panel_auth, or always for admins
    # when it looks like a refresh token paste.
    if message.chat.id not in _AWAITING_REFRESH and not text.startswith("eyJ"):
        return
    # Prefer explicit awaiting; also accept bare JWT pastes from admins.
    await _apply_refresh(message, text)


async def _apply_refresh(message: Message, token: str) -> None:
    app = get_app()
    _AWAITING_REFRESH.discard(message.chat.id)
    token = token.strip().strip('"').strip("'")
    if not _looks_like_jwt(token):
        await message.answer("Это не похоже на JWT refresh_token. Попробуйте ещё раз: /panel_auth")
        return

    app.panel.update_tokens(refresh_token=token, access_token="")
    try:
        await app.panel.ensure_access_token(force=True)
    except PanelAuthError as exc:
        await message.answer(f"Не удалось активировать сессию:\n{_esc(exc)}")
        return

    left = app.panel.refresh_seconds_left()
    days = f"~{left/86400:.1f} дн." if left is not None else "срок неизвестен"
    await message.answer(
        "Сессия панели сохранена и проверена.\n"
        f"Refresh: {days}\n"
        "Access будет обновляться сам. Файл: <code>data/panel_session.json</code>"
    )
    # Best-effort: delete the secret message from chat history.
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        logger.info("Could not delete refresh token message")
