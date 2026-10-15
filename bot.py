"""Vacancy relay - runs ONCE per invocation (designed for GitHub Actions cron).

Reads new posts from source channels, cleans them, posts to the target channel,
and saves progress in state.json so nothing is posted twice.
"""
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from telethon import TelegramClient, Button
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from formatter import build_message, fingerprint, split_text, clean_text

# ---------- configuration (all from environment / GitHub secrets) ----------
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]          # reader account
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()          # optional poster bot (enables buttons)
TARGET_CHANNEL = os.environ["TARGET_CHANNEL"]
SOURCES = [s.strip() for s in os.environ["SOURCE_CHANNELS"].split(",") if s.strip()]

MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "10"))
INITIAL_BACKFILL = int(os.getenv("INITIAL_BACKFILL", "0"))   # posts to publish on first sight of a source
MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "48"))        # ignore older messages
MIN_TEXT_LEN = int(os.getenv("MIN_TEXT_LEN", "20"))
REQUIRE_LINK = os.getenv("REQUIRE_LINK", "true").lower() != "false"   # skip posts without an apply link
MAX_MEDIA_MB = int(os.getenv("MAX_MEDIA_MB", "20"))
DELAY_SECONDS = float(os.getenv("DELAY_SECONDS", "4"))

STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))
CONFIG = json.loads(Path("config.json").read_text(encoding="utf-8-sig"))
CTA = CONFIG.get("cta", "")
LINKS = CONFIG.get("social_links", [])  # [{"label": "...", "url": "..."}]


def log(msg):
    print(msg, flush=True)


# ---------- state ----------
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    return {"last_ids": {}, "hashes": []}


def save_state(state):
    state["hashes"] = state["hashes"][-1000:]
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")


def norm_source(s: str) -> str:
    return re.sub(r"^(https?://)?(t\.me/|telegram\.me/)?@?", "", s.strip()).strip("/").lower()


# ---------- sending ----------
def make_buttons():
    rows, row = [], []
    for item in LINKS:
        row.append(Button.url(item["label"], item["url"]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows or None


async def send_with_retry(coro_factory):
    """Run a send; on FloodWait <= 90s wait and retry once, else re-raise."""
    try:
        return await coro_factory()
    except FloodWaitError as e:
        if e.seconds > 90:
            raise
        log(f"  flood wait {e.seconds}s ...")
        await asyncio.sleep(e.seconds + 1)
        return await coro_factory()


async def safe_send_message(poster, text, buttons):
    try:
        return await send_with_retry(
            lambda: poster.send_message(TARGET_CHANNEL, text, parse_mode="md",
                                        buttons=buttons, link_preview=False))
    except FloodWaitError:
        raise
    except Exception as e:  # markdown problems etc. -> retry as plain text
        log(f"  markdown send failed ({e}); retrying as plain text")
        return await send_with_retry(
            lambda: poster.send_message(TARGET_CHANNEL, text, parse_mode=None,
                                        buttons=buttons, link_preview=False))


async def publish(poster, can_button, paths, text):
    buttons = make_buttons() if can_button else None
    if not paths:
        chunks = split_text(text)
        for i, chunk in enumerate(chunks):
            await safe_send_message(poster, chunk, buttons if i == len(chunks) - 1 else None)
        return

    if len(paths) == 1 and len(text) <= 1024:
        try:
            await send_with_retry(lambda: poster.send_file(
                TARGET_CHANNEL, paths[0], caption=text, parse_mode="md", buttons=buttons))
            return
        except FloodWaitError:
            raise
        except Exception as e:
            log(f"  caption send failed ({e}); falling back to separate text")

    cap = "📌 **Job vacancy details below** 👇"
    await send_with_retry(lambda: poster.send_file(
        TARGET_CHANNEL, paths if len(paths) > 1 else paths[0], caption=cap, parse_mode="md"))
    chunks = split_text(text)
    for i, chunk in enumerate(chunks):
        await safe_send_message(poster, chunk, buttons if i == len(chunks) - 1 else None)


# ---------- main loop ----------
def group_messages(messages):
    """Turn a list of messages (oldest first) into posts; albums become one post."""
    posts, albums = [], {}
    for m in messages:
        if m.grouped_id:
            if m.grouped_id not in albums:
                albums[m.grouped_id] = []
                posts.append(albums[m.grouped_id])
            albums[m.grouped_id].append(m)
        else:
            posts.append([m])
    return posts


async def download_media(reader, msgs, tmpdir):
    paths = []
    for m in msgs:
        if not m.media:
            continue
        size = getattr(getattr(m, "file", None), "size", None) or 0
        if size > MAX_MEDIA_MB * 1024 * 1024:
            log(f"  media {size/1e6:.1f}MB too big, skipping file")
            continue
        try:
            p = await reader.download_media(m, file=tmpdir + "/")
            if p:
                paths.append(p)
        except Exception as e:
            log(f"  media download failed: {e}")
    return paths


async def main():
    started = time.time()
    state = load_state()
    posted = 0

    reader = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await reader.connect()
    if not await reader.is_user_authorized():
        log("ERROR: SESSION_STRING is invalid or expired. Regenerate it with generate_session.py")
        sys.exit(1)

    if BOT_TOKEN:
        poster = TelegramClient(StringSession(), API_ID, API_HASH)
        await poster.start(bot_token=BOT_TOKEN)
        can_button = True
    else:
        poster, can_button = reader, False
        log("No BOT_TOKEN set: posting as your account, without buttons.")

    try:
        for source in SOURCES:
            key = norm_source(source)
            try:
                entity = await reader.get_entity(source)
            except Exception as e:
                log(f"[{key}] cannot resolve: {e}")
                continue

            if key not in state["last_ids"]:
                latest = await reader.get_messages(entity, limit=max(INITIAL_BACKFILL, 1))
                if not latest:
                    state["last_ids"][key] = 0
                    continue
                if INITIAL_BACKFILL <= 0:
                    state["last_ids"][key] = latest[0].id
                    log(f"[{key}] first run: starting from message {latest[0].id} (nothing posted)")
                    continue
                state["last_ids"][key] = min(m.id for m in latest) - 1

            last_id = state["last_ids"][key]
            msgs = [m async for m in reader.iter_messages(entity, min_id=last_id, limit=100, reverse=True)]
            msgs = [m for m in msgs if not getattr(m, "action", None)]
            if not msgs:
                continue
            log(f"[{key}] {len(msgs)} new message(s) after id {last_id}")

            for post in group_messages(msgs):
                if posted >= MAX_POSTS_PER_RUN:
                    log("Per-run limit reached; the rest continues next run.")
                    break
                newest_id = max(m.id for m in post)
                age_h = (time.time() - post[-1].date.timestamp()) / 3600
                text = next((m.text for m in post if m.text), "")

                skip = None
                if age_h > MAX_AGE_HOURS:
                    skip = "too old"
                elif len(clean_text(text)[0]) < MIN_TEXT_LEN:
                    skip = "no meaningful text"
                elif REQUIRE_LINK and not clean_text(text)[1]:
                    skip = "no application link (promo/ad)"
                else:
                    fp = fingerprint(text)
                    if fp in state["hashes"]:
                        skip = "duplicate"

                if skip:
                    log(f"  skip {newest_id}: {skip}")
                    state["last_ids"][key] = newest_id
                    continue

                final_text = build_message(text, CTA)
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        paths = await download_media(reader, post, tmp)
                        await publish(poster, can_button, paths, final_text)
                    state["hashes"].append(fp)
                    posted += 1
                    log(f"  posted {key}/{newest_id}")
                except FloodWaitError as e:
                    log(f"  long flood wait ({e.seconds}s): stopping, will resume next run")
                    save_state(state)
                    return
                except Exception as e:
                    log(f"  ERROR posting {newest_id}: {e} (skipping it)")
                state["last_ids"][key] = newest_id
                save_state(state)
                await asyncio.sleep(DELAY_SECONDS)
    finally:
        save_state(state)
        await reader.disconnect()
        if poster is not reader:
            await poster.disconnect()
    log(f"Done: {posted} posted in {time.time()-started:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
