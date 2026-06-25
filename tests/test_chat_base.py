from datetime import datetime, timedelta, timezone

from src.app.resources.chat_base.assist import (
    build_assist_user_message,
    detect_languages,
    parse_queries_from_ai,
)
from src.app.resources.chat_base.meta import (
    MAX_GROUPS_PER_PLATFORM,
    accept_candidate,
    can_accept_more,
    default_meta,
    is_blocked,
    normalize_meta,
    reject_candidate,
)
from src.app.resources.chat_base.filters import GroupCandidate, passes_filters
from src.app.resources.chat_base.run_control import (
    clear_stop,
    is_running,
    mark_running,
    request_stop,
    unmark_running,
)


def test_request_stop_when_not_running():
    assert request_stop("nonexistent-rid") is False
    assert not is_running("nonexistent-rid")


def test_request_stop_when_running():
    rid = "test-rid-stop"
    mark_running(rid)
    try:
        assert is_running(rid)
        assert request_stop(rid) is True
    finally:
        unmark_running(rid)
        clear_stop(rid)


def test_build_assist_user_message_en_default():
    msg = build_assist_user_message("ФРИЛАНС ПАЙТОН", "Заказы программисту")
    assert "только на английском" in msg.lower()


def test_build_assist_user_message_ru_explicit():
    msg = build_assist_user_message("База", "Группы на русском про python")
    assert "только на английском" not in msg.lower()
    assert "RU" in msg
    assert "кириллица" in msg.lower()


def test_detect_languages_multi():
    langs = detect_languages(
        "ФРИЛАНСЕР ПАЙТОН",
        "Заказы программисту. EN, RU, AZ",
    )
    assert langs == ["EN", "RU", "AZ"]


def test_build_assist_user_message_multi_lang():
    msg = build_assist_user_message(
        "ФРИЛАНСЕР ПАЙТОН",
        "Заказы программисту. EN, RU, AZ",
    )
    assert "EN, RU, AZ" in msg
    assert "КАЖДОМ" in msg
    assert "не только EN" in msg
    assert "только на английском" not in msg.lower()


def test_parse_queries_from_ai():
    raw = """
1. python freelance
- developer jobs
• авиамоделизм
#tag
@username
python freelance
"""
    qs = parse_queries_from_ai(raw)
    assert qs == ["python freelance", "developer jobs", "авиамоделизм"]


def test_accept_respects_limit():
    meta = default_meta()
    for i in range(MAX_GROUPS_PER_PLATFORM):
        assert accept_candidate(
            meta, {"external_id": f"@g{i}", "title": f"G{i}"}
        )
    assert not can_accept_more(meta)
    assert not accept_candidate(
        meta, {"external_id": "@overflow", "title": "X"}
    )


def test_blacklist_blocks():
    meta = default_meta()
    reject_candidate(meta, {"external_id": "@bad"})
    assert is_blocked(meta, "@bad")


def test_passes_filters_members_and_freshness():
    now = datetime.now(timezone.utc)
    cand = GroupCandidate(
        external_id="@ok",
        title="Test",
        link="https://t.me/ok",
        members=5000,
        description="jobs",
        last_post_at=now - timedelta(hours=2),
        week_message_count=10,
        query="test",
    )
    ok, _ = passes_filters(cand, min_members=3000, last_post_max_hours=24)
    assert ok

    stale = GroupCandidate(
        external_id="@old",
        title="Old",
        link=None,
        members=5000,
        description=None,
        last_post_at=now - timedelta(days=3),
        week_message_count=0,
        query="test",
    )
    ok2, reason = passes_filters(
        stale, min_members=3000, last_post_max_hours=24
    )
    assert not ok2
    assert reason == "stale_last_post"


def test_normalize_meta_keeps_accepted_and_ai():
    raw = default_meta()
    raw["accepted"]["telegram"] = [{"external_id": "@x", "title": "X"}]
    raw["ai"]["model"] = "gpt-4o-mini"
    meta = normalize_meta(raw)
    assert meta["accepted"]["telegram"][0]["external_id"] == "@x"
    assert meta["ai"]["model"] == "gpt-4o-mini"
