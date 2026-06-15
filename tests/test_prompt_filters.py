from src.app.core.message_bus import MessageEvent
from src.app.resources.prompt.prompt_worker import _passes_filters


def _event(**kwargs) -> MessageEvent:
    defaults = {
        "source_type": "telegram_session",
        "source_rid": "test-rid",
        "peer_id": 1031436671,
        "peer_type": "group",
        "chat_id": -1003320156340,
        "sender_username": "thedarkest_lord",
        "chat_username": "baraxolka_baku",
        "msg_id": 1,
        "external_chat_id": "-1003320156340",
        "external_msg_id": "1",
        "text": "hello",
    }
    defaults.update(kwargs)
    return MessageEvent(**defaults)


def test_whitelist_group_username():
    assert _passes_filters(
        _event(),
        {"reply_groups": True, "whitelist": ["@baraxolka_baku"]},
    )


def test_whitelist_group_chat_id():
    assert _passes_filters(
        _event(),
        {"reply_groups": True, "whitelist": ["-1003320156340"]},
    )


def test_whitelist_sender_username():
    assert _passes_filters(
        _event(),
        {"reply_groups": True, "whitelist": ["@thedarkest_lord"]},
    )


def test_whitelist_sender_peer_id():
    assert _passes_filters(
        _event(),
        {"reply_groups": True, "whitelist": ["1031436671"]},
    )


def test_whitelist_rejects_unknown():
    assert not _passes_filters(
        _event(),
        {"reply_groups": True, "whitelist": ["@other_group"]},
    )


def test_blacklist_group_username():
    assert not _passes_filters(
        _event(),
        {"reply_groups": True, "blacklist": ["baraxolka_baku"]},
    )


def test_blacklist_sender_username():
    assert not _passes_filters(
        _event(),
        {"reply_groups": True, "blacklist": ["@thedarkest_lord"]},
    )


def test_empty_whitelist_allows_all():
    assert _passes_filters(_event(), {"reply_groups": True, "whitelist": []})
