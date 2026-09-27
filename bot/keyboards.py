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


def card_actions(*, can_back: bool, recorded: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not recorded:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Плохой ответ",
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
        nav.append(InlineKeyboardButton(text="Назад", callback_data="act:prev"))
    nav.append(InlineKeyboardButton(text="Дальше", callback_data="act:next"))
    rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="Завершить", callback_data="act:finish")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def verdict_actions() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Устная беседа",
                    callback_data="verdict:Устная беседа",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Предупреждение",
                    callback_data="verdict:Предупреждение",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Выговор",
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
