from __future__ import annotations

import html
import logging
from datetime import date

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.context import get_app
from bot.keyboards import card_actions, day_picker, verdict_actions
from bot.models import ReviewCard
from bot.services.normalize import format_card_html
from bot.services.panel import PanelAuthError, moscow_recent_days
from bot.services.session import ReviewSession
from bot.services.sheets import SheetsError

logger = logging.getLogger(__name__)
router = Router(name="check")


def _esc(value: object) -> str:
    return html.escape(str(value))


def _card_html(card: ReviewCard, index: int, total: int) -> str:
    return format_card_html(card, index, total)


def _day_picker_markup(*, mode: str = "check") -> InlineKeyboardMarkup:
    app = get_app()
    days = [d.isoformat() for d in moscow_recent_days(5)]
    progress = app.day_progress.all_for_days(days)
    written: dict[str, int] = {}
    if app.sheets is not None:
        try:
            written = app.sheets.written_counts_by_date()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to read written counts from sheet")
    return day_picker(
        progress_by_day=progress,
        written_by_day=written,
        mode=mode,
    )


def _sync_remaining(session: ReviewSession) -> None:
    """Update day progress from the live session position."""
    left = sum(
        1
        for i, card in enumerate(session.cards)
        if i >= session.index and card.card_id not in session.recorded_ids
    )
    get_app().day_progress.set_remaining(session.day, left)


async def _set_ui(
    message: Message,
    session: ReviewSession,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the single review UI message; send once if missing."""
    app = get_app()
    bot = message.bot
    chat_id = session.chat_id

    if session.ui_message_id is not None:
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=session.ui_message_id,
                reply_markup=reply_markup,
            )
            app.sessions.save(session)
            return
        except TelegramBadRequest as exc:
            err = str(exc).lower()
            if "message is not modified" in err:
                app.sessions.save(session)
                return
            logger.info("UI edit failed (%s); sending a new message", exc)
        except Exception:  # noqa: BLE001
            logger.exception("UI edit failed; sending a new message")

    sent = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
    )
    session.ui_message_id = sent.message_id
    app.sessions.save(session)


async def _show_card(message: Message, session: ReviewSession) -> None:
    app = get_app()
    total = len(session.cards)
    if total == 0:
        app.day_progress.save_load(session.day, total=0, remaining=0)
        await _set_ui(
            message,
            session,
            "За выбранный день ответов для проверки нет.",
            reply_markup=_day_picker_markup(),
        )
        app.sessions.clear(session.chat_id)
        return
    if session.index >= total:
        app.day_progress.save_load(session.day, total=total, remaining=0)
        await _set_ui(
            message,
            session,
            f"Готово.\nПросмотрено: {total}\nЗаписано в таблицу: {session.written}",
            reply_markup=_day_picker_markup(),
        )
        app.sessions.clear(session.chat_id)
        return

    _sync_remaining(session)
    card = session.cards[session.index]
    recorded = card.card_id in session.recorded_ids
    text = _card_html(card, session.index + 1, total)
    await _set_ui(
        message,
        session,
        text,
        reply_markup=card_actions(
            can_back=session.index > 0,
            recorded=recorded,
            admin_name=card.admin_name,
        ),
    )


async def _start_day(
    message: Message,
    day: date,
    *,
    force_reload: bool = False,
) -> None:
    app = get_app()
    day_key = day.isoformat()
    # Reuse the day-picker message as the single UI surface.
    session_stub = ReviewSession(
        chat_id=message.chat.id,
        day=day_key,
        index=0,
        written=0,
        awaiting_custom=False,
        cards=[],
        recorded_ids=set(),
        ui_message_id=message.message_id,
    )
    mode_note = " (перепроверка, включая уже записанные)" if force_reload else ""
    await _set_ui(
        message,
        session_stub,
        f"Загружаю логи за {day_key}…{mode_note}",
    )

    try:
        cards = await app.panel.fetch_day_cards(day)
    except PanelAuthError as exc:
        await _set_ui(message, session_stub, f"Нет доступа к панели.\n{_esc(exc)}")
        app.sessions.clear(message.chat.id)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch panel logs")
        await _set_ui(message, session_stub, f"Ошибка загрузки логов: {_esc(exc)}")
        app.sessions.clear(message.chat.id)
        return

    total_raw = len(cards)
    skipped = 0
    if app.sheets is not None and not force_reload:
        try:
            before = len(cards)
            cards = app.sheets.filter_new_cards(cards)
            skipped = before - len(cards)
        except SheetsError as exc:
            await _set_ui(message, session_stub, f"Ошибка таблицы: {_esc(exc)}")
            app.sessions.clear(message.chat.id)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to read spreadsheet")
            await _set_ui(message, session_stub, f"Ошибка чтения таблицы: {_esc(exc)}")
            app.sessions.clear(message.chat.id)
            return

    app.day_progress.save_load(day_key, total=total_raw, remaining=len(cards))

    report_n = sum(1 for c in cards if c.answer_type == "Report")
    faq_n = sum(1 for c in cards if c.answer_type == "FAQ")

    session = ReviewSession(
        chat_id=message.chat.id,
        day=day_key,
        index=0,
        written=0,
        awaiting_custom=False,
        cards=cards,
        recorded_ids=set(),
        ui_message_id=session_stub.ui_message_id,
    )
    app.sessions.save(session)

    fixture_note = ""
    if app.panel.used_fixtures:
        fixture_note = (
            "\n⚠ Логи панели с этого IP недоступны (403) — показаны тестовые фикстуры."
        )
    backend_note = ""
    if app.sheet_backend == "local_csv":
        backend_note = (
            f"\n⚠ Google Sheets не подключён — запись в {app.settings.local_sheet_path}"
        )
    force_note = (
        "\n↺ Режим перепроверки: уже записанные ответы снова в списке."
        if force_reload
        else ""
    )

    if not cards:
        summary = (
            f"День {day_key}: карточек 0"
            f" (Report: 0, FAQ/z-request: 0)"
            + (f"\nУже записано ранее: {skipped}" if skipped else "")
            + fixture_note
            + backend_note
            + force_note
            + "\n\nНовых ответов для проверки нет."
        )
        await _set_ui(message, session, summary, reply_markup=_day_picker_markup())
        app.sessions.clear(session.chat_id)
        return

    if skipped or fixture_note or backend_note or force_reload:
        flash = (
            f"День {day_key}: осталось {len(cards)} "
            f"(Report: {report_n}, FAQ/z-request: {faq_n})"
            + (f", уже записано: {skipped}" if skipped else "")
            + fixture_note
            + backend_note
            + force_note
        )
        await _set_ui(message, session, flash)

    await _show_card(message, session)


def _load_session(chat_id: int) -> ReviewSession | None:
    return get_app().sessions.get(chat_id)


def _picker_caption() -> str:
    return (
        "Какой день проверить? (последние 5 дней, МСК)\n"
        "<i>ост. N</i> — сколько ещё не проверено после последней загрузки\n"
        "<i>✓</i> — на последней загрузке новых не осталось\n"
        "<i>зап. N</i> — сколько вердиктов уже в таблице\n"
        "Уже записанные ответы при обычной загрузке скрываются."
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Бот проверки ответов администраторов.\n"
        "Источники: Report (репорт в админ-чат 2+) и FAQ/z-request (поддержка).\n"
        "В таблице колонка типа: Report или FAQ.\n\n"
        "/check — проверка дня (последние 5 дней, МСК)\n"
        "/panel_status — статус сессии панели\n"
        "/panel_auth — обновить refresh (редко, раз в ~30 дней)\n\n"
        + _picker_caption(),
        reply_markup=_day_picker_markup(),
    )


@router.message(Command("check"))
async def cmd_check(message: Message) -> None:
    await message.answer(
        _picker_caption(),
        reply_markup=_day_picker_markup(),
    )


@router.callback_query(F.data == "reset:menu")
async def reset_menu(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer()
    await callback.message.edit_text(
        "↺ <b>Перепроверка</b>\n"
        "Выберите день: ответы снова появятся, даже если вердикт уже есть в таблице.\n"
        "Новый вердикт будет дописан строкой в таблицу.",
        reply_markup=_day_picker_markup(mode="reset"),
    )


@router.callback_query(F.data == "reset:cancel")
async def reset_cancel(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer()
    await callback.message.edit_text(
        _picker_caption(),
        reply_markup=_day_picker_markup(),
    )


@router.callback_query(F.data.startswith("resetday:"))
async def reset_day(callback: CallbackQuery) -> None:
    if not callback.message or not callback.data:
        return
    raw = callback.data.split(":", 1)[1].strip()
    allowed = {d.isoformat() for d in moscow_recent_days(5)}
    if raw not in allowed:
        await callback.answer("Можно выбрать только из последних 5 дней", show_alert=True)
        return
    app = get_app()
    app.day_progress.mark_force_reload(raw)
    app.sessions.clear(callback.message.chat.id)
    await callback.answer("Сброс: день загрузится целиком")
    await _start_day(callback.message, date.fromisoformat(raw), force_reload=True)


@router.callback_query(F.data.startswith("day:"))
async def pick_day(callback: CallbackQuery) -> None:
    if not callback.message or not callback.data:
        return
    raw = callback.data.split(":", 1)[1].strip()
    allowed = {d.isoformat() for d in moscow_recent_days(5)}
    # Keep legacy aliases working if an old keyboard is still on screen.
    if raw == "today":
        raw = next(iter(sorted(allowed, reverse=True)))
    elif raw == "yesterday":
        ordered = sorted(allowed, reverse=True)
        raw = ordered[1] if len(ordered) > 1 else ordered[0]
    if raw not in allowed:
        await callback.answer("Можно выбрать только из последних 5 дней", show_alert=True)
        return
    day = date.fromisoformat(raw)
    await callback.answer()
    await _start_day(callback.message, day, force_reload=False)


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
    if session.index >= len(session.cards):
        await callback.answer("Карточек больше нет", show_alert=True)
        return
    card = session.cards[session.index]
    if card.card_id in session.recorded_ids:
        await callback.answer("Уже записано", show_alert=True)
        return
    session.ui_message_id = callback.message.message_id
    session.awaiting_custom = False
    get_app().sessions.save(session)
    await callback.answer()
    text = (
        _card_html(card, session.index + 1, len(session.cards))
        + f"\n\n<b>Вердикт для {_esc(card.admin_name)}</b> — выберите:"
    )
    await _set_ui(
        callback.message,
        session,
        text,
        reply_markup=verdict_actions(admin_name=card.admin_name),
    )


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
    session.ui_message_id = callback.message.message_id
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
    session.ui_message_id = callback.message.message_id
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
    _sync_remaining(session)
    session.ui_message_id = callback.message.message_id
    await callback.answer()
    await _set_ui(
        callback.message,
        session,
        f"Проверка остановлена.\nКарточек: {total}\nЗаписано: {written}",
        reply_markup=_day_picker_markup(),
    )
    app.sessions.clear(session.chat_id)


async def _write_verdict(message: Message, session: ReviewSession, verdict: str) -> None:
    app = get_app()
    if session.index >= len(session.cards):
        await _set_ui(message, session, "Карточек больше нет.")
        return
    card: ReviewCard = session.cards[session.index]
    if card.card_id in session.recorded_ids:
        await _show_card(message, session)
        return
    if app.sheets is None:
        await _set_ui(
            message,
            session,
            "Google Sheets не настроен. Вердикт не записан. "
            "Добавьте SERVICE_ACCOUNT_PATH или GOOGLE_SERVICE_ACCOUNT_JSON.",
        )
        return
    try:
        app.sheets.append_verdict(card, verdict)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to append sheet row")
        await _set_ui(
            message,
            session,
            f"Не удалось записать в таблицу: {_esc(exc)}",
        )
        return

    session.recorded_ids.add(card.card_id)
    session.written += 1
    session.awaiting_custom = False
    session.index += 1
    app.sessions.save(session)
    _sync_remaining(session)
    await _show_card(message, session)


@router.callback_query(F.data.startswith("verdict:"))
async def pick_verdict(callback: CallbackQuery) -> None:
    if not callback.message or not callback.data:
        return
    session = _load_session(callback.message.chat.id)
    if session is None:
        await callback.answer("Сессия не найдена. /check", show_alert=True)
        return

    session.ui_message_id = callback.message.message_id
    value = callback.data.split(":", 1)[1]
    if value == "cancel":
        session.awaiting_custom = False
        get_app().sessions.save(session)
        await callback.answer("Отменено")
        await _show_card(callback.message, session)
        return
    if value == "custom":
        session.awaiting_custom = True
        get_app().sessions.save(session)
        await callback.answer()
        card = session.cards[session.index]
        text = (
            _card_html(card, session.index + 1, len(session.cards))
            + f"\n\n<b>Свой вердикт для {_esc(card.admin_name)}</b>\n"
            "Пришлите текст одним сообщением."
        )
        await _set_ui(
            callback.message,
            session,
            text,
            reply_markup=verdict_actions(admin_name=card.admin_name),
        )
        return

    await callback.answer()
    await _write_verdict(callback.message, session, value)


@router.message(F.text)
async def custom_verdict_text(message: Message) -> None:
    # JWT pastes are handled by panel_auth router first.
    session = _load_session(message.chat.id)
    if session is None or not session.awaiting_custom:
        return
    text = (message.text or "").strip()
    if not text:
        admin = ""
        if session.index < len(session.cards):
            admin = session.cards[session.index].admin_name
        await _set_ui(
            message,
            session,
            "Пустой вердикт. Пришлите текст или нажмите «Отмена».",
            reply_markup=verdict_actions(admin_name=admin),
        )
        return
    # Prefer deleting the user's verdict text to keep the chat clean.
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    await _write_verdict(message, session, text)
