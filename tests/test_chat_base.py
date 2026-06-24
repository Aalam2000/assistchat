from datetime import datetime, timedelta, timezone

from src.app.resources.chat_base.meta import (
    MAX_GROUPS_PER_PLATFORM,
    accept_candidate,
    can_accept_more,
    default_meta,
    is_blocked,
    normalize_meta,
    reject_candidate,
    suggest_queries,
)
from src.app.resources.chat_base.filters import GroupCandidate, passes_filters


def test_suggest_queries_from_topic():
    qs = suggest_queries("программист")
    assert "программист" in qs
    assert len(qs) >= 3


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


def test_normalize_meta_keeps_accepted():
    raw = default_meta()
    raw["accepted"]["telegram"] = [{"external_id": "@x", "title": "X"}]
    meta = normalize_meta(raw)
    assert meta["accepted"]["telegram"][0]["external_id"] == "@x"
