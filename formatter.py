"""Pure text-cleaning logic (no Telegram imports, so it is easy to test)."""
import re

SOCIAL_DOMAINS = (
    "t.me/", "telegram.me/", "telegram.dog/", "facebook.com", "fb.com", "instagram.com",
    "twitter.com", "x.com", "linkedin.com", "youtube.com", "youtu.be", "tiktok.com",
    "wa.me/", "whatsapp.com",
)

MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
BARE_URL = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)
SCHEMELESS_SOCIAL = re.compile(
    r"(?<![\w/])(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog|facebook\.com|instagram\.com|"
    r"linkedin\.com|youtube\.com|youtu\.be|tiktok\.com|wa\.me)/[^\s)\]]*", re.IGNORECASE)
# @username, but NOT the part of an e-mail address (hr@company.com)
USERNAME = re.compile(r"(?<![\w.@])@[A-Za-z][A-Za-z0-9_]{3,}")
TRAILING_PUNCT = ".,;:!?"


def _is_social(url: str) -> bool:
    u = url.lower()
    return any(d in u for d in SOCIAL_DOMAINS)


def clean_text(text: str):
    """Return (cleaned_text, apply_links).

    - removes social/telegram links and @usernames of the source channel
    - keeps every other link and returns them as `apply_links`
    - keeps e-mail addresses
    """
    if not text:
        return "", []

    apply_links = []

    def md_repl(m):
        label, url = m.group(1), m.group(2)
        if _is_social(url):
            return label
        apply_links.append(url.rstrip(TRAILING_PUNCT))
        return label if label.strip() else ""

    text = MD_LINK.sub(md_repl, text)

    def url_repl(m):
        url = m.group(0)
        stripped = url.rstrip(TRAILING_PUNCT)
        if _is_social(stripped):
            return ""
        apply_links.append(stripped)
        return ""  # moved into the apply section at the bottom

    text = BARE_URL.sub(url_repl, text)
    text = SCHEMELESS_SOCIAL.sub("", text)
    text = USERNAME.sub("", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, list(dict.fromkeys(apply_links))


def build_message(text: str, cta: str, header: str = "", apply_title: str = "", link_label: str = "") -> str:
    cleaned, links = clean_text(text)
    parts = []
    if header:
        parts.append(header.strip())
    if cleaned:
        parts.append(cleaned)
    if links:
        title = apply_title or "**Application link(s):**"
        label = link_label or "Apply"
        lines = [f"[{label}]({link})" for link in links]
        parts.append(title + "\n" + "\n".join(lines))
    if cta:
        parts.append(cta.strip())
    return "\n\n".join(parts)


def split_text(text: str, limit: int = 4000):
    """Split long text on paragraph/line boundaries."""
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        candidate = f"{cur}\n\n{para}" if cur else para
        if len(candidate) <= limit:
            cur = candidate
            continue
        if cur:
            chunks.append(cur)
        while len(para) > limit:
            cut = para.rfind("\n", 0, limit)
            cut = cut if cut > 0 else limit
            chunks.append(para[:cut])
            para = para[cut:].lstrip("\n")
        cur = para
    if cur:
        chunks.append(cur)
    return chunks


def fingerprint(text: str) -> str:
    """Stable hash of the vacancy content for duplicate detection."""
    import hashlib
    cleaned, links = clean_text(text)
    norm = re.sub(r"\W+", "", cleaned.lower())[:600] + "|" + "|".join(sorted(links))
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()
