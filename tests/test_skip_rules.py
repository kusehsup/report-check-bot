from __future__ import annotations

from pathlib import Path

from bot.models import ReviewCard
from bot.services.normalize import format_card_html
from bot.services.skip_rules import SkipRulesStore


def _card(*, admin: str, answer: str, cid: str = "1") -> ReviewCard:
    return ReviewCard(
        card_id=cid,
        answer_type="Report",
        answered_at="2026-09-27 12:00:00",
        player_name="P",
        player_id="1",
        question="q",
        admin_name=admin,
        answer=answer,
    )


def test_always_skip_automatic_answer(tmp_path: Path) -> None:
    store = SkipRulesStore(tmp_path / "s.db")
    cards = [
        _card(admin="Автоматический ответ", answer="ok", cid="a"),
        _card(admin="Garik_Trapov", answer="иду", cid="b"),
    ]
    result = store.filter_cards(cards)
    assert result.skipped_auto == 1
    assert result.skipped_phrases == 0
    assert len(result.cards) == 1
    assert result.cards[0].admin_name == "Garik_Trapov"


def test_phrase_skip_case_insensitive_substring(tmp_path: Path) -> None:
    store = SkipRulesStore(tmp_path / "s.db")
    ok, _ = store.add_phrase("Слежу за вами")
    assert ok
    cards = [
        _card(admin="A", answer="слежу за вами", cid="1"),
        _card(admin="B", answer="Слежу за вами!", cid="2"),
        _card(admin="C", answer="сейчас подойду", cid="3"),
    ]
    result = store.filter_cards(cards)
    assert result.skipped_phrases == 2
    assert [c.admin_name for c in result.cards] == ["C"]


def test_add_remove_phrases(tmp_path: Path) -> None:
    store = SkipRulesStore(tmp_path / "s.db")
    assert store.add_phrase("Слежу за вами")[0]
    assert store.add_phrase("слежу за вами")[0] is False  # duplicate normalized
    phrases = store.list_phrases()
    assert len(phrases) == 1
    assert store.remove_phrase(phrases[0].id)
    assert store.list_phrases() == []


def test_card_progress_shows_skipped() -> None:
    card = _card(admin="A", answer="x")
    html = format_card_html(card, 3, 150, raw_total=8000, skipped_total=7850)
    assert "3/150" in html
    assert "к проверке" in html
    assert "8000" in html
    assert "7850" in html
