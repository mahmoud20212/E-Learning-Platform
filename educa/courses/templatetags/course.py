from django import template
from urllib.parse import parse_qs, urlparse

register = template.Library()

@register.filter
def model_name(obj):
    try:
        return obj._meta.model_name
    except AttributeError:
        return None


@register.filter
def youtube_embed_url(url):
    """Return a safe YouTube embed URL from common YouTube link formats."""
    if not url:
        return ""

    parsed = urlparse(str(url))
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    video_id = ""

    if "youtu.be" in host:
        video_id = path.strip("/")
    elif "youtube.com" in host:
        if path.startswith("/watch"):
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif path.startswith("/shorts/"):
            video_id = path.split("/shorts/", 1)[1].split("/", 1)[0]
        elif path.startswith("/embed/"):
            video_id = path.split("/embed/", 1)[1].split("/", 1)[0]

    if not video_id:
        return ""

    return f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0&modestbranding=1"