from __future__ import annotations

import json
from pathlib import Path

from bot.services.normalize import (
    format_card_text,
    merge_and_sort,
    normalize_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_report_log_pairs_answers_with_questions() -> None:
    payload = json.loads((FIXTURES / "report_log.json").read_text(encoding="utf-8"))
    cards = normalize_payload(payload, "Report")

    # unanswered Solid_Interpolov skipped; Kirill 1 answer + Zub 2 answers
    assert len(cards) == 3

    multi = [c for c in cards if c.player_name == "Zub_Molochnyy"]
    assert len(multi) == 2
    first = next(c for c in multi if c.admin_name == "Kesh_Qa")
    assert first.answer_type == "Report"
    assert first.question == "как подать обевлени в трк ритм"
    assert first.player_id == "1716393"
    assert len(first.sibling_replies) == 1
    assert first.sibling_replies[0].admin_name == "Artem_Bariga"
    assert first.dialogue
    assert first.dialogue[0].role == "player"
    assert any(d.role == "agent" and d.name == "Kesh_Qa" for d in first.dialogue)

    kirill = next(c for c in cards if c.player_name == "Kirill_Shramokokk")
    assert kirill.answered_at == "2026-09-27 23:58:07"
    assert kirill.answer == "иду"
    assert kirill.question == "help"


def test_faq_payload_sender_name() -> None:
    payload = json.loads((FIXTURES / "player_requests_z.json").read_text(encoding="utf-8"))
    cards = normalize_payload(payload, "FAQ")
    # Bernaba: 1 agent answer; Vova: 4 agent answers (player follow-ups skipped)
    assert len(cards) == 5
    assert {c.answer_type for c in cards} == {"FAQ"}
    names = {c.player_name for c in cards}
    assert names == {"Bernaba_Casamento", "Vova_Beloysov"}
    one = next(c for c in cards if c.admin_name == "Daniel_Shevch" and "Рестарт" in c.answer)
    assert "Рестарт" in one.answer


def test_faq_multi_agent_dialogue_skips_player_replies() -> None:
    payload = json.loads((FIXTURES / "player_requests_z.json").read_text(encoding="utf-8"))
    cards = normalize_payload(payload, "FAQ")
    vova = [c for c in cards if c.player_name == "Vova_Beloysov"]
    assert len(vova) == 4
    assert {c.admin_name for c in vova} == {"Artem_Bariga", "Daniel_Shevch"}
    # Player never becomes the "admin" under review
    assert all(c.admin_name != "Vova_Beloysov" for c in vova)

    artem = next(c for c in vova if c.admin_name == "Artem_Bariga")
    daniel_case = next(c for c in vova if c.answer == "Только открытие кейс")
    assert artem.answer.startswith("нужна бронепластина")
    # Verdict on Artem's card must not use Daniel's answer text
    assert artem.sheet_row("Выговор")[2] == "Artem_Bariga"
    assert artem.sheet_row("Выговор")[4].startswith("нужна бронепластина")
    assert daniel_case.sheet_row("Выговор")[2] == "Daniel_Shevch"

    text = format_card_text(daniel_case, 1, len(cards))
    assert "Проверяется ответ агента: Daniel_Shevch" in text
    assert "Игрок Vova_Beloysov" in text
    assert "Агент Artem_Bariga" in text
    assert "Агент Daniel_Shevch" in text
    assert "← этот ответ" in text
    assert "Другие ответы агентов" in text
    # Player lines must not be listed as agent siblings
    assert "• Vova_Beloysov" not in text


def test_merge_sort_and_format() -> None:
    report = normalize_payload(
        json.loads((FIXTURES / "report_log.json").read_text(encoding="utf-8")),
        "Report",
    )
    faq = normalize_payload(
        json.loads((FIXTURES / "player_requests_z.json").read_text(encoding="utf-8")),
        "FAQ",
    )
    merged = merge_and_sort(report, faq)
    assert merged[0].answered_at >= merged[-1].answered_at
    text = format_card_text(merged[0], 1, len(merged))
    assert "· 1/" in text
    assert "Проверяется ответ агента:" in text or "Ответ:" in text
    assert "Диалог:" in text or "Вопрос:" in text
    # Telegram labels clarify source; sheet still stores Report|FAQ.
    assert "Report · репорт" in text or "FAQ · z-request" in text


def test_sheet_row() -> None:
    cards = normalize_payload(
        [
            {
                "time": "2026-09-27 11:00:00",
                "timeAsInt": 1,
                "player": {"name": "P", "accountId": 1},
                "type": "report",
                "message": "q",
            },
            {
                "time": "2026-09-27 12:00:00",
                "timeAsInt": 2,
                "admin": {"name": "A"},
                "player": {"name": "P", "accountId": 1},
                "type": "answer",
                "message": "ok",
            },
        ],
        "Report",
    )
    assert len(cards) == 1
    row = cards[0].sheet_row("Устная беседа")
    assert row == [
        "2026-09-27 12:00:00",
        "Report",
        "A",
        "q",
        "ok",
        "Устная беседа",
    ]
