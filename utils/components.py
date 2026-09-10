from __future__ import annotations

import discord

# Shared accent colour for every panel built through build_base_container.
PANEL_ACCENT_COLOUR = discord.Colour(0x3D91FF)


def build_base_container(
    *,
    title: str | None = None,
    description: str | None = None,
    thumbnail_url: str | None = None,
    banner_url: str | None = None,
    accent_colour: discord.Colour | None = None,
) -> discord.ui.Container:
    """Builds a standard panel container: optional banner on top, then a
    title (+ optional thumbnail as a side accessory) and description.
    Every panel built with this helper shares PANEL_ACCENT_COLOUR unless a
    different accent_colour is passed explicitly."""
    children: list[discord.ui.Item] = []

    if banner_url:
        children.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=banner_url)))

    header_text = discord.ui.TextDisplay(f"# {title}") if title else None
    body_text = discord.ui.TextDisplay(description) if description else None
    text_items = [item for item in (header_text, body_text) if item is not None]

    if thumbnail_url and text_items:
        children.append(
            discord.ui.Section(*text_items, accessory=discord.ui.Thumbnail(media=thumbnail_url))
        )
    else:
        children.extend(text_items)

    return discord.ui.Container(*children, accent_colour=accent_colour or PANEL_ACCENT_COLOUR)


def add_text(container: discord.ui.Container, text: str) -> discord.ui.TextDisplay:
    item = discord.ui.TextDisplay(text)
    container.add_item(item)
    return item


def add_separator(
    container: discord.ui.Container,
    *,
    spacing: discord.SeparatorSpacing = discord.SeparatorSpacing.small,
) -> discord.ui.Separator:
    item = discord.ui.Separator(spacing=spacing)
    container.add_item(item)
    return item


def add_action_row(container: discord.ui.Container, *items: discord.ui.Item) -> discord.ui.ActionRow:
    row = discord.ui.ActionRow(*items)
    container.add_item(row)
    return row
