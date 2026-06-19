from src.app.core.message_bus import MessageEvent
from src.app.resources.prompt.prompt_worker import (
    _extract_ai_match,
    _is_deliverable_notify_text,
    _listen_source_rids,
    _message_link,
)


def test_extract_ai_match_true_json():
    assert _extract_ai_match('{"match": true, "reason": "bot request"}') is True


def test_extract_ai_match_false_json():
    assert _extract_ai_match('{"match": false, "reason": "job seeker"}') is False


def test_extract_ai_match_markdown_fence():
    raw = '```json\n{"match": false, "confidence": "high"}\n```'
    assert _extract_ai_match(raw) is False


def test_extract_ai_match_embedded_json():
    raw = 'Analysis complete.\n{"match": true, "confidence": "medium"}\nDone.'
    assert _extract_ai_match(raw) is True


def test_extract_ai_match_prose_without_json():
    assert _extract_ai_match("This looks like a valid lead for a website.") is None


def test_extract_ai_match_string_false():
    assert _extract_ai_match('{"match": "false"}') is False


def test_listen_source_rids_session_only_not_prompt_bot():
    rids = _listen_source_rids({
        "telegram_session_rid": "sess-1",
        "telegram_bot_rid": "bot-notify-1",
    })
    assert rids == ["sess-1"]


def test_listen_source_rids_empty_without_session():
    assert _listen_source_rids({"telegram_bot_rid": "bot-notify-1"}) == []


def test_listen_source_rids_empty_sources():
    assert _listen_source_rids({}) == []
    assert _listen_source_rids(None) == []


def test_deliverable_notify_rejects_empty_and_skip():
    assert _is_deliverable_notify_text("") is False
    assert _is_deliverable_notify_text("   ") is False
    assert _is_deliverable_notify_text("SKIP") is False
    assert _is_deliverable_notify_text("skip.") is False


def test_deliverable_notify_rejects_classification_json():
    assert _is_deliverable_notify_text('{"match": false, "reason": "no"}') is False
    assert _is_deliverable_notify_text('{"match": true, "reason": "yes"}') is False


def test_deliverable_notify_accepts_prose():
    text = "🔔 Лид\n📋 Нужен Telegram-бот\n👤 @client"
    assert _is_deliverable_notify_text(text) is True


def _msg_event(**kwargs) -> MessageEvent:
    defaults = {
        "source_type": "telegram_session",
        "source_rid": "test-rid",
        "peer_id": 1031436671,
        "peer_type": "group",
        "chat_id": -1003320156340,
        "sender_username": "client_user",
        "chat_username": "my_group",
        "msg_id": 42,
        "external_chat_id": "-1003320156340",
        "external_msg_id": "42",
        "text": "hello",
    }
    defaults.update(kwargs)
    return MessageEvent(**defaults)


def test_message_link_public_chat_username():
    assert _message_link(_msg_event()) == "https://t.me/my_group/42"


def test_message_link_private_supergroup():
    assert _message_link(_msg_event(chat_username=None)) == "https://t.me/c/3320156340/42"


def test_message_link_private_dm_with_username():
    link = _message_link(_msg_event(
        peer_type="private",
        chat_id=1031436671,
        chat_username=None,
        sender_username="client_user",
    ))
    assert link == "https://t.me/client_user/42"


def test_message_link_private_dm_without_username():
    link = _message_link(_msg_event(
        peer_type="private",
        chat_id=1031436671,
        chat_username=None,
        sender_username="John Doe",
    ))
    assert link == "tg://openmessage?user_id=1031436671&message_id=42"


def test_message_link_missing_msg_id():
    assert _message_link(_msg_event(msg_id=None)) is None
