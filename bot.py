import asyncio
import logging
import signal

import discord
from discord.ext import commands

import config
from keep_alive import keep_alive
from utils.storage import store

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Slash command sync failed: {e}")


async def main():
    keep_alive()
    await store.init()

    loop = asyncio.get_running_loop()

    async with bot:
        # Render (and most hosts) send SIGTERM to stop the old process
        # during a deploy. Without a handler, Python kills the process
        # immediately without closing the gateway connection — the old
        # instance can linger and keep receiving interactions alongside
        # the new one, causing "already acknowledged" errors on every
        # button click. This makes shutdown graceful instead.
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig, lambda: asyncio.create_task(bot.close())
                )
            except NotImplementedError:
                # add_signal_handler isn't available on some platforms
                # (e.g. Windows) — safe to skip there.
                pass

        await bot.load_extension("cogs.tickets")
        await bot.load_extension("cogs.orders")
        await bot.load_extension("cogs.support_tickets")
        await bot.load_extension("cogs.bot_status")
        await bot.load_extension("cogs.join_ping")
        await bot.load_extension("cogs.giveaways")
        await bot.load_extension("cogs.reviews")
        await bot.load_extension("cogs.suggestions")
        await bot.start(config.BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
