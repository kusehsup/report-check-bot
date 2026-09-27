from __future__ import annotations

import json
from pathlib import Path

from bot.services.normalize import (
    format_card_text,
    merge_and_sort,
    normalize_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_report_log_one_card_per_answer_with_siblings() -> None:
    payload = json.loads((FIXTURES / "report_log.json").read_text(encoding="utf-8"))
    cards = normalize_payload(payload, "Report")

    # unanswered first item skipped; 1 + 1 + 5 answers
    assert len(cards) == 7

    multi = [c for c in cards if c.player_name == "Zub_Molochnyy"]
    assert len(multi) == 5
    first = next(c for c in multi if c.admin_name == "Kesh_Qa")
    assert first.answer_type == "Report"
    assert first.question == "как подать обевлени в трк ритм"
    assert first.player_id == "1716393"
    assert len(first.sibling_replies) == 4
    assert any(s.admin_name == "Artem_Bariga" for s in first.sibling_replies)

    jacob = next(c for c in cards if c.player_name == "Jacob_Ukraine")
    assert jacob.answered_at == "2026-09-27 23:58:03"
    assert jacob.answer == "на твинке только"


def test_faq_payload_nested_and_flat() -> None:
    payload = json.loads((FIXTURES / "player_requests_z.json").read_text(encoding="utf-8"))
    cards = normalize_payload(payload, "FAQ")
    assert len(cards) == 2
    assert {c.answer_type for c in cards} == {"FAQ"}
    names = {c.player_name for c in cards}
    assert names == {"Polinka_Korgi", "Kostya_Robchic"}


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
    assert "Вопрос:" in text
    assert "Ответ:" in text


def test_sheet_row() -> None:
    cards = normalize_payload(
        {
            "answers": [
                {
                    "adminName": "A",
                    "text": "ok",
                    "createdAt": "2026-09-27 12:00:00",
                }
            ],
            "question": "q",
            "playerName": "P",
            "playerId": 1,
            "createdAt": "2026-09-27 11:00:00",
        },
        "FAQ",
    )
    # _as_list on dict without list keys — single thread object
    assert len(cards) == 1
    row = cards[0].sheet_row("Устная беседа")
    assert row == [
        "2026-09-27 12:00:00",
        "FAQ",
        "A",
        "q",
        "ok",
        "Устная беседа",
    ]
