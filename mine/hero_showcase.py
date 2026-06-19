"""Landing hero showcase — YouTube embeds from the official Freeport channel."""
from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from mine.config import Config

_CONFIG_PATH = Config.BASE_DIR / "config" / "hero_showcase.json"
_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)

_DEFAULT_SLIDES = [
    {"caption": "Copper at the core — global mining operations", "youtube_id": "E8lmlyGbcms"},
    {"caption": "Lone Star mine — Southeastern Arizona", "youtube_id": "fyI1fRJY0hc"},
    {"caption": "Arizona copper mining — open-pit operations", "youtube_id": "m-SIKwpMF48"},
    {"caption": "Smelter commissioning — processing at scale", "youtube_id": "i_nXUS6pI6Y"},
    {"caption": "Indonesia operations — Grasberg mining complex", "youtube_id": "hKXYFuWpjLg"},
    {"caption": "Morenci — deep roots, broad horizons", "youtube_id": "24j4rJ4G4nM"},
]


def youtube_id_from_url(url: str) -> str | None:
    match = _YOUTUBE_ID_RE.search((url or "").strip())
    return match.group(1) if match else None


def youtube_watch_url(video_id: str, *, autoplay: bool = True) -> str:
    query = {"v": video_id}
    if autoplay:
        query["autoplay"] = "1"
    return "https://www.youtube.com/watch?" + urlencode(query)


def youtube_thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _load_showcase_config() -> list[dict]:
    if not _CONFIG_PATH.is_file():
        return list(_DEFAULT_SLIDES)
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        slides = data.get("slides") if isinstance(data, dict) else data
        if isinstance(slides, list) and slides:
            return slides
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return list(_DEFAULT_SLIDES)


def _hero_showcase_slides() -> list[dict]:
    """Landing hero reel — Freeport YouTube thumbnails (config/hero_showcase.json)."""
    slides = []
    for item in _load_showcase_config():
        video_id = (item.get("youtube_id") or "").strip()
        if not video_id:
            url = (item.get("youtube_url") or "").strip()
            video_id = youtube_id_from_url(url) or ""
        caption = (item.get("caption") or "").strip()
        if not video_id or not caption:
            continue
        slides.append(
            {
                "caption": caption,
                "youtube_id": video_id,
                "watch_url": youtube_watch_url(video_id),
                "thumbnail_url": youtube_thumbnail_url(video_id),
            }
        )
    return slides
