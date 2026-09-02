from __future__ import annotations

from urllib.parse import urlparse


def discord_invite_code(link: str) -> str | None:
    parsed = urlparse(link)
    if parsed.scheme not in {"http", "https"}:
        return None

    hostname = (parsed.hostname or "").lower()
    parts = [segment for segment in parsed.path.split("/") if segment]

    if hostname in {"discord.gg", "discord.me", "discord.li"}:
        return parts[0] if parts else None

    if hostname in {"discord.com", "www.discord.com", "discordapp.com", "www.discordapp.com"}:
        if len(parts) >= 2 and parts[0].lower() == "invite":
            return parts[1]

    return None


def is_valid_link(link: str) -> bool:
    return discord_invite_code(link) is not None
