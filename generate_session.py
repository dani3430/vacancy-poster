"""Run ONCE on your computer to create the SESSION_STRING secret.
Nothing is hard-coded: you type your own API ID / hash (from https://my.telegram.org).
"""
import asyncio
import getpass

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    api_id = int(input("API_ID: ").strip())
    api_hash = getpass.getpass("API_HASH (hidden): ").strip()
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        s = client.session.save()
    print("\nSESSION_STRING (keep secret, never commit or share):\n")
    print(s)


if __name__ == "__main__":
    asyncio.run(main())
