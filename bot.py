import asyncio
import logging

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

    async with bot:
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
