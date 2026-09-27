from __future__ import annotations

from pathlib import Path

from bot.models import ReviewCard
from bot.services.reviewed import ReviewedStore


def _card(admin: str = "Cody_Angell", answer: str = "ok", cid: str = "1") -> ReviewCard:
    return ReviewCard(
        card_id=cid,
        answer_type="FAQ",
        answered_at="2026-09-27 08:13:47",
        player_name="VOVA_PIVOVOZ",
        player_id="1743799",
        question="почините машыну",
        admin_name=admin,
        answer=answer,
    )


def test_mark_and_filter_passed(tmp_path: Path) -> None:
    store = ReviewedStore(tmp_path / "r.db")
    a = _card(admin="Cody_Angell", answer="Не чиним", cid="a")
    b = _card(admin="Angel_Samitov", answer="нет", cid="b")
    store.mark("2026-09-26", a)
    kept = store.filter_new_cards([a, b])
    assert len(kept) == 1
    assert kept[0].admin_name == "Angel_Samitov"


def test_clear_day_allows_again(tmp_path: Path) -> None:
    store = ReviewedStore(tmp_path / "r.db")
    card = _card()
    store.mark("2026-09-26", card)
    assert store.clear_day("2026-09-26") == 1
    assert store.filter_new_cards([card]) == [card]
