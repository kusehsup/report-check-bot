from __future__ import annotations

import html
import logging
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.context import get_app
from bot.keyboards import card_actions, day_picker, verdict_actions
from bot.models import ReviewCard
from bot.services.normalize import format_card_text
from bot.services.panel import PanelAuthError, moscow_today, moscow_yesterday
from bot.services.session import ReviewSession
from bot.services.sheets import SheetsError

logger = logging.getLogger(__name__)
router = Router(name="check")


def _esc(value: object) -> str:
    return html.escape(str(value))


async def _show_card(message: Message, session: ReviewSession) -> None:
    app = get_app()
    total = len(session.cards)
    if total == 0:
        await message.answer("За выбранный день ответов для проверки нет.")
        app.sessions.clear(session.chat_id)
        return
    if session.index >= total:
        await message.answer(
            f"Готово.\nПросмотрено: {total}\nЗаписано в таблицу: {session.written}"
        )
        app.sessions.clear(session.chat_id)
        return

    card = session.cards[session.index]
    recorded = card.card_id in session.recorded_ids
    text = format_card_text(card, session.index + 1, total)
    await message.answer(
        f"<pre>{_esc(text)}</pre>",
        reply_markup=card_actions(
            can_back=session.index > 0,
            recorded=recorded,
        ),
    )
    app.sessions.save(session)


async def _start_day(message: Message, day: date) -> None:
    app = get_app()
    status = await message.answer(f"Загружаю логи за {day.isoformat()}…")
    try:
        cards = await app.panel.fetch_day_cards(day)
    except PanelAuthError as exc:
        await status.edit_text(f"Нет доступа к панели.\n{_esc(exc)}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch panel logs")
        await status.edit_text(f"Ошибка загрузки логов: {_esc(exc)}")
        return

    skipped = 0
    if app.sheets is not None:
        try:
            before = len(cards)
            cards = app.sheets.filter_new_cards(cards)
            skipped = before - len(cards)
        except SheetsError as exc:
            await status.edit_text(f"Ошибка таблицы: {_esc(exc)}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to read spreadsheet")
            await status.edit_text(f"Ошибка чтения таблицы: {_esc(exc)}")
            return
    else:
        await status.edit_text(
            "Предупреждение: Google Sheets не настроен "
            "(SERVICE_ACCOUNT_PATH / GOOGLE_SERVICE_ACCOUNT_JSON). "
            "Карточки покажу, запись в таблицу будет недоступна."
        )

    session = ReviewSession(
        chat_id=message.chat.id,
        day=day.isoformat(),
        index=0,
        written=0,
        awaiting_custom=False,
        cards=cards,
        recorded_ids=set(),
    )
    app.sessions.save(session)

    summary = (
        f"День {day.isoformat()}: карточек {len(cards)}"
        + (f" (пропущено уже записанных: {skipped})" if skipped else "")
    )
    try:
        await status.edit_text(summary)
    except Exception:  # noqa: BLE001
        await message.answer(summary)
    await _show_card(message, session)


def _load_session(chat_id: int) -> ReviewSession | None:
    return get_app().sessions.get(chat_id)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Бот проверки ответов администраторов.\n"
        "Команда /check — начать проверку дня.",
        reply_markup=day_picker(),
    )


@router.message(Command("check"))
async def cmd_check(message: Message) -> None:
    await message.answer("Какой день проверить?", reply_markup=day_picker())


@router.callback_query(F.data == "day:today")
async def pick_today(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await _start_day(callback.message, moscow_today())


@router.callback_query(F.data == "day:yesterday")
async def pick_yesterday(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await _start_day(callback.message, moscow_yesterday())


@router.callback_query(F.data == "act:noop")
async def act_noop(callback: CallbackQuery) -> None:
    await callback.answer("Эта карточка уже записана в таблицу")


@router.callback_query(F.data == "act:bad")
async def act_bad(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    session = _load_session(callback.message.chat.id)
    if session is None:
        await callback.answer("Сессия не найдена. /check", show_alert=True)
        return
    card = session.cards[session.index]
    if card.card_id in session.recorded_ids:
        await callback.answer("Уже записано", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer("Выберите вердикт:", reply_markup=verdict_actions())


@router.callback_query(F.data == "act:next")
async def act_next(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    session = _load_session(callback.message.chat.id)
    if session is None:
        await callback.answer("Сессия не найдена. /check", show_alert=True)
        return
    session.index += 1
    session.awaiting_custom = False
    get_app().sessions.save(session)
    await callback.answer()
    await _show_card(callback.message, session)


@router.callback_query(F.data == "act:prev")
async def act_prev(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    session = _load_session(callback.message.chat.id)
    if session is None:
        await callback.answer("Сессия не найдена. /check", show_alert=True)
        return
    session.index = max(0, session.index - 1)
    session.awaiting_custom = False
    get_app().sessions.save(session)
    await callback.answer()
    await _show_card(callback.message, session)


@router.callback_query(F.data == "act:finish")
async def act_finish(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    session = _load_session(callback.message.chat.id)
    app = get_app()
    if session is None:
        await callback.answer("Сессии нет")
        return
    total = len(session.cards)
    written = session.written
    app.sessions.clear(session.chat_id)
    await callback.answer()
    await callback.message.answer(
        f"Проверка остановлена.\nКарточек: {total}\nЗаписано: {written}"
    )


async def _write_verdict(message: Message, session: ReviewSession, verdict: str) -> None:
    app = get_app()
    if session.index >= len(session.cards):
        await message.answer("Карточек больше нет.")
        return
    card: ReviewCard = session.cards[session.index]
    if card.card_id in session.recorded_ids:
        await message.answer("Эта карточка уже записана. Жмите «Дальше».")
        return
    if app.sheets is None:
        await message.answer(
            "Google Sheets не настроен. Вердикт не записан. "
            "Добавьте SERVICE_ACCOUNT_PATH или GOOGLE_SERVICE_ACCOUNT_JSON."
        )
        return
    try:
        app.sheets.append_verdict(card, verdict)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to append sheet row")
        await message.answer(f"Не удалось записать в таблицу: {_esc(exc)}")
        return

    session.recorded_ids.add(card.card_id)
    session.written += 1
    session.awaiting_custom = False
    session.index += 1
    app.sessions.save(session)
    await message.answer(f"Записано: {_esc(verdict)}")
    await _show_card(message, session)


@router.callback_query(F.data.startswith("verdict:"))
async def pick_verdict(callback: CallbackQuery) -> None:
    if not callback.message or not callback.data:
        return
    session = _load_session(callback.message.chat.id)
    if session is None:
        await callback.answer("Сессия не найдена. /check", show_alert=True)
        return

    value = callback.data.split(":", 1)[1]
    if value == "cancel":
        session.awaiting_custom = False
        get_app().sessions.save(session)
        await callback.answer("Отменено")
        return
    if value == "custom":
        session.awaiting_custom = True
        get_app().sessions.save(session)
        await callback.answer()
        await callback.message.answer("Пришлите текст вердикта одним сообщением.")
        return

    await callback.answer()
    await _write_verdict(callback.message, session, value)


@router.message(F.text)
async def custom_verdict_text(message: Message) -> None:
    session = _load_session(message.chat.id)
    if session is None or not session.awaiting_custom:
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустой вердикт. Пришлите текст или нажмите «Отмена».")
        return
    await _write_verdict(message, session, text)
