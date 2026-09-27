from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, Message

from bot.context import get_app
from bot.keyboards import skip_phrases_keyboard
from bot.services.skip_rules import ALWAYS_SKIP_ADMIN_NAMES

router = Router(name="skips")


class AwaitingSkipAdd(Filter):
    """Only catch free-text while waiting for a new skip phrase."""

    async def __call__(self, message: Message) -> bool:
        if not message.text or message.text.startswith("/"):
            return False
        app = get_app()
        if not app.skip_rules.is_awaiting_add(message.chat.id):
            return False
        session = app.sessions.get(message.chat.id)
        if session is not None and session.awaiting_custom:
            return False
        return True


def _esc(value: object) -> str:
    return html.escape(str(value))


def _skips_text() -> str:
    app = get_app()
    phrases = app.skip_rules.list_phrases()
    auto = ", ".join(sorted(ALWAYS_SKIP_ADMIN_NAMES))
    lines = [
        "<b>Пропуск ответов</b>",
        "",
        f"Всегда пропускается автор: <code>{_esc(auto)}</code>",
        "",
        "Фразы/ключевые слова (подстрока в ответе, без учёта регистра):",
    ]
    if not phrases:
        lines.append("<i>Список пуст. Добавьте, например: Слежу за вами</i>")
    else:
        for item in phrases:
            lines.append(f"{item.id}. <code>{_esc(item.phrase)}</code>")
    lines.extend(
        [
            "",
            "Команды: /skips · /skip_add текст · /skip_del id",
        ]
    )
    return "\n".join(lines)


def _skips_markup():
    phrases = [(p.id, p.phrase) for p in get_app().skip_rules.list_phrases()]
    return skip_phrases_keyboard(phrases)


@router.message(Command("skips"))
async def cmd_skips(message: Message) -> None:
    get_app().skip_rules.set_awaiting_add(message.chat.id, False)
    await message.answer(_skips_text(), reply_markup=_skips_markup())


@router.message(Command("skip_add"))
async def cmd_skip_add(message: Message) -> None:
    app = get_app()
    text = (message.text or "").split(maxsplit=1)
    if len(text) < 2 or not text[1].strip():
        app.skip_rules.set_awaiting_add(message.chat.id, True)
        await message.answer(
            "Пришлите фразу для пропуска одним сообщением.\n"
            "Пример: <code>Слежу за вами</code>"
        )
        return
    ok, detail = app.skip_rules.add_phrase(text[1])
    app.skip_rules.set_awaiting_add(message.chat.id, False)
    if ok:
        await message.answer(
            f"Добавлено: <code>{_esc(detail)}</code>",
            reply_markup=_skips_markup(),
        )
    else:
        await message.answer(detail)


@router.message(Command("skip_del"))
async def cmd_skip_del(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /skip_del id\nСписок: /skips")
        return
    phrase_id = int(parts[1])
    if get_app().skip_rules.remove_phrase(phrase_id):
        await message.answer(f"Удалено #{phrase_id}", reply_markup=_skips_markup())
    else:
        await message.answer("Фраза не найдена.", reply_markup=_skips_markup())


@router.callback_query(F.data == "skip:add")
async def skip_add_cb(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    get_app().skip_rules.set_awaiting_add(callback.message.chat.id, True)
    await callback.answer()
    await callback.message.answer(
        "Пришлите фразу для пропуска одним сообщением.\n"
        "Пример: <code>Слежу за вами</code>"
    )


@router.callback_query(F.data == "skip:close")
async def skip_close_cb(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    get_app().skip_rules.set_awaiting_add(callback.message.chat.id, False)
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("skip:del:"))
async def skip_del_cb(callback: CallbackQuery) -> None:
    if not callback.message or not callback.data:
        return
    raw = callback.data.rsplit(":", 1)[-1]
    if not raw.isdigit():
        await callback.answer("Некорректный id", show_alert=True)
        return
    removed = get_app().skip_rules.remove_phrase(int(raw))
    await callback.answer("Удалено" if removed else "Не найдено")
    try:
        await callback.message.edit_text(_skips_text(), reply_markup=_skips_markup())
    except Exception:  # noqa: BLE001
        await callback.message.answer(_skips_text(), reply_markup=_skips_markup())


@router.message(F.text, AwaitingSkipAdd())
async def skip_add_text(message: Message) -> None:
    app = get_app()
    text = (message.text or "").strip()
    ok, detail = app.skip_rules.add_phrase(text)
    app.skip_rules.set_awaiting_add(message.chat.id, False)
    if ok:
        await message.answer(
            f"Добавлено: <code>{_esc(detail)}</code>",
            reply_markup=_skips_markup(),
        )
    else:
        await message.answer(detail)
