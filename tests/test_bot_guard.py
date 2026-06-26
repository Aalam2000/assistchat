from unittest.mock import MagicMock, patch

import pytest

from src.app.modules.bot.guard import (
    BotInactive,
    is_bot_active,
    require_bot_active,
    require_resource_bot_active,
)


def test_is_bot_active_true():
    db = MagicMock()
    db.execute.return_value.first.return_value = (True,)
    assert is_bot_active(1, db) is True


def test_is_bot_active_false():
    db = MagicMock()
    db.execute.return_value.first.return_value = (False,)
    assert is_bot_active(1, db) is False


def test_require_bot_active_raises():
    with patch("src.app.modules.bot.guard.is_bot_active", return_value=False):
        with pytest.raises(BotInactive):
            require_bot_active(7)


def test_require_resource_bot_active():
    resource = MagicMock()
    resource.user_id = 3
    with patch("src.app.modules.bot.guard.require_bot_active") as req:
        require_resource_bot_active(resource)
    req.assert_called_once_with(3, None)
