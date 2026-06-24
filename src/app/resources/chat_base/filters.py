# src/app/resources/chat_base/filters.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class GroupCandidate:
    external_id: str
    title: str
    link: str | None
    members: int | None
    description: str | None
    last_post_at: datetime | None
    week_message_count: int
    query: str
    platform: str = "telegram"

    def to_dict(self) -> dict[str, Any]:
        return {
            "external_id": self.external_id,
            "title": self.title,
            "link": self.link,
            "members": self.members,
            "description": self.description,
            "last_post_at": (
                self.last_post_at.isoformat() if self.last_post_at else None
            ),
            "week_message_count": self.week_message_count,
            "query": self.query,
            "platform": self.platform,
        }


def passes_filters(
    candidate: GroupCandidate,
    *,
    min_members: int,
    last_post_max_hours: int,
) -> tuple[bool, str | None]:
    if candidate.members is not None and candidate.members < min_members:
        return False, "too_few_members"
    if not candidate.last_post_at:
        return False, "no_recent_activity"
    max_age = timedelta(hours=max(1, last_post_max_hours))
    if datetime.now(timezone.utc) - candidate.last_post_at > max_age:
        return False, "stale_last_post"
    return True, None
