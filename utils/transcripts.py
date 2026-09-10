import io
import discord


async def build_transcript(channel: discord.TextChannel) -> discord.File:
    """
    Builds a plain-text transcript of every message in the channel,
    oldest first, and returns it as a discord.File ready to attach
    to a message.
    """
    lines: list[str] = [
        f"Transcript for #{channel.name} ({channel.id})",
        f"Guild: {channel.guild.name}",
        "=" * 60,
        "",
    ]

    async for message in channel.history(limit=None, oldest_first=True):
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        author = f"{message.author} ({message.author.id})"
        content = message.content or ""

        if message.embeds:
            content += " [embed]"
        if message.attachments:
            attach_urls = ", ".join(a.url for a in message.attachments)
            content += f" [attachments: {attach_urls}]"
        if message.components:
            content += " [components]"

        lines.append(f"[{timestamp}] {author}: {content}")

    text = "\n".join(lines)
    buffer = io.BytesIO(text.encode("utf-8"))
    filename = f"transcript-{channel.name}.txt"
    return discord.File(buffer, filename=filename)
