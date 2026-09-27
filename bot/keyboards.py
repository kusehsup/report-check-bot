from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def day_picker() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сегодня", callback_data="day:today"),
                InlineKeyboardButton(text="Вчера", callback_data="day:yesterday"),
            ]
        ]
    )


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
    nav.append(InlineKeyboardButton(text="Дальше →", callback_data="act:next"))
    rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="Завершить", callback_data="act:finish")]
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
