# Vacancy Poster

A free, fully automated Telegram vacancy relay. Every 10 minutes GitHub Actions reads new
posts from source Telegram channels, cleans them, and publishes them to a target channel.
No server and no computer left on: it runs entirely on GitHub's free tier.

## What it does
- Reads new posts from the channels listed in `SOURCE_CHANNELS`.
- Removes the source channel's links (Telegram, Facebook, LinkedIn, YouTube, ...) and `@usernames`.
- Keeps real application links and shows them under "Application link(s)".
- **Skips posts with no application link** (ads and promotions).
- Skips duplicates and posts older than 48 hours.
- Adds the footer from `config.json` and 5 link buttons (needs a bot).
- Handles photo albums, long captions, and Telegram rate limits.
- Saves progress in `state.json` so nothing is posted twice.

## How it works
`.github/workflows/poll.yml` runs `bot.py` on a schedule. `bot.py` reads with a user session,
posts with a bot, and commits `state.json` back to the repo.

## Files
| File | Purpose |
|---|---|
| `bot.py` | Main program (runs once per schedule tick) |
| `formatter.py` | Text cleaning, link extraction, duplicate fingerprint |
| `config.json` | Footer text and button links (edit this to customize) |
| `generate_session.py` | One-time login helper to create `SESSION_STRING` |
| `test_formatter.py` | Tests for the cleaning logic |
| `.github/workflows/poll.yml` | Schedule and workflow |
| `state.json` | Auto-generated progress (last message per source) |

## Setup
1. **Telegram API keys:** create an app at https://my.telegram.org -> API development tools.
2. **Bot:** create one with @BotFather and add it as an **admin** of the target channel
   (permission: post messages).
3. **Session string:** on your computer run    Enter API ID, API hash, then your **phone number** (not the bot token) and the login code.
   Use a secondary Telegram account if possible.
4. **Repository:** it must be **public** (unlimited free Actions minutes).
   Settings -> Actions -> General -> Workflow permissions -> **Read and write permissions**.
5. **Secrets** (Settings -> Secrets and variables -> Actions):

   | Name | Value |
   |---|---|
   | `API_ID` | number from my.telegram.org |
   | `API_HASH` | hash from my.telegram.org |
   | `SESSION_STRING` | from `generate_session.py` |
   | `BOT_TOKEN` | from BotFather (optional; without it, posts have no buttons) |
   | `TARGET_CHANNEL` | `@yourchannel` |
   | `SOURCE_CHANNELS` | comma-separated, e.g. `@chan1,@chan2` |

6. **Start:** Actions -> "Relay vacancies" -> Run workflow. The first run only records the
   latest message of each source and posts nothing. After that it runs every ~10 minutes.

## Settings (optional environment variables in the workflow)
`MAX_POSTS_PER_RUN` (10), `MAX_AGE_HOURS` (48), `MIN_TEXT_LEN` (20), `MAX_MEDIA_MB` (20),
`REQUIRE_LINK` (true; set `false` to also post vacancies without a link), `INITIAL_BACKFILL` (0).

## Troubleshooting
- **Green run but nothing posted:** check the "Run relay" log. Common reasons: no new messages,
  posts had no application link, or `SOURCE_CHANNELS` is wrong.
- **`SESSION_STRING is invalid`:** regenerate it with your phone number.
- **Source `cannot resolve`:** wrong channel name, or a private channel the reader account has not joined.
- **Schedule stopped:** GitHub pauses schedules after 60 days of no repo activity; re-enable in the Actions tab.
- Use "Run workflow", not "Re-run all jobs" (that replays old code).

## Test locally 

## Notes
- Never commit secrets. They live only in GitHub Secrets.
- Automating a user account can violate Telegram's terms and may limit it. Respect the source
  channels' terms and credit sources where appropriate.
