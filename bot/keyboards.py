from __future__ import annotations

from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.day_progress import DayProgress
from bot.services.panel import moscow_recent_days, moscow_today

_WEEKDAYS_RU = (
    "пн",
    "вт",
    "ср",
    "чт",
    "пт",
    "сб",
    "вс",
)


def _day_base_label(day: date, *, today: date) -> str:
    delta = (today - day).days
    stamp = day.strftime("%d.%m")
    weekday = _WEEKDAYS_RU[day.weekday()]
    if delta == 0:
        return f"Сегодня · {stamp}"
    if delta == 1:
        return f"Вчера · {stamp}"
    return f"{weekday} · {stamp}"


def _day_status_suffix(
    day_key: str,
    *,
    progress: DayProgress | None,
    written: int,
) -> str:
    if progress is not None:
        if progress.last_remaining <= 0 and progress.last_total > 0:
            return " · ✓"
        if progress.last_remaining > 0:
            return f" · ост. {progress.last_remaining}"
    if written > 0:
        return f" · зап. {written}"
    return ""


def day_picker(
    *,
    days: int = 5,
    progress_by_day: dict[str, DayProgress] | None = None,
    written_by_day: dict[str, int] | None = None,
    mode: str = "check",
) -> InlineKeyboardMarkup:
    """
    mode=check → day:YYYY-MM-DD
    mode=reset → resetday:YYYY-MM-DD (force re-review, ignore sheet dedupe once)
    """
    today = moscow_today()
    recent = moscow_recent_days(days)
    progress_by_day = progress_by_day or {}
    written_by_day = written_by_day or {}
    prefix = "resetday" if mode == "reset" else "day"

    rows: list[list[InlineKeyboardButton]] = []
    for day in recent:
        key = day.isoformat()
        label = _day_base_label(day, today=today)
        if mode == "check":
            label += _day_status_suffix(
                key,
                progress=progress_by_day.get(key),
                written=written_by_day.get(key, 0),
            )
        else:
            label = f"↺ {label}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"{prefix}:{key}",
                )
            ]
        )

    if mode == "check":
        rows.append(
            [
                InlineKeyboardButton(
                    text="↺ Сбросить день и перепроверить",
                    callback_data="reset:menu",
                )
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="← Назад к дням", callback_data="reset:cancel")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_actions(
    *,
    can_back: bool,
    recorded: bool,
    admin_name: str = "",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not recorded:
        label = "Плохой ответ"
        if admin_name:
            short = admin_name if len(admin_name) <= 28 else admin_name[:27] + "…"
            label = f"Плохой ответ · {short}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data="act:bad",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Уже записано",
                    callback_data="act:noop",
                )
            ]
        )
    nav: list[InlineKeyboardButton] = []
    if can_back:
        nav.append(InlineKeyboardButton(text="← Назад", callback_data="act:prev"))
    # «Дальше» = вердикт «ответ нормальный», не просто навигация.
    nav.append(InlineKeyboardButton(text="Норм →", callback_data="act:next"))
    rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="Завершить", callback_data="act:finish")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_phrases_keyboard(phrases: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="+ Добавить фразу",
                callback_data="skip:add",
            )
        ]
    ]
    for phrase_id, phrase in phrases[:30]:
        short = phrase if len(phrase) <= 36 else phrase[:33] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Удалить · {short}"[:64],
                    callback_data=f"skip:del:{phrase_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="Закрыть", callback_data="skip:close")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def verdict_actions(*, admin_name: str = "") -> InlineKeyboardMarkup:
    who = f" · {admin_name}" if admin_name and len(admin_name) <= 20 else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Устная беседа{who}"[:64],
                    callback_data="verdict:Устная беседа",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Предупреждение{who}"[:64],
                    callback_data="verdict:Предупреждение",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Выговор{who}"[:64],
                    callback_data="verdict:Выговор",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Свой текст",
                    callback_data="verdict:custom",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="verdict:cancel",
                )
            ],
        ]
    )
