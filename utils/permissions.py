from __future__ import annotations

from typing import Iterable

import discord
from discord import app_commands

import config


def member_has_any_role(member: discord.Member, role_ids: Iterable[int]) -> bool:
    """True if the member has at least one of the given role IDs.
    Zero/falsy IDs in role_ids are ignored (unconfigured roles)."""
    wanted = {r for r in role_ids if r}
    if not wanted:
        return False
    return any(role.id in wanted for role in member.roles)


def has_roles(member: discord.Member, *role_ids: int) -> bool:
    """Same as member_has_any_role but with the IDs passed positionally."""
    return member_has_any_role(member, role_ids)


def slash_is_ceo_only():
    """App-command check: only the configured CEO role may use the command."""

    async def predicate(interaction: discord.Interaction) -> bool:
        return isinstance(interaction.user, discord.Member) and member_has_any_role(
            interaction.user, [config.CEO_ROLE_ID]
        )

    return app_commands.check(predicate)


def slash_is_ownership_only():
    """App-command check: the Ownership role (or CEO/Co-CEO as a fallback)
    may use the command."""

    async def predicate(interaction: discord.Interaction) -> bool:
        return isinstance(interaction.user, discord.Member) and member_has_any_role(
            interaction.user, [config.OWNERSHIP_ROLE_ID, config.CEO_ROLE_ID, config.ROLE_CO_CEO]
        )

    return app_commands.check(predicate)


def slash_is_staff_team():
    """App-command check: any general staff role (developer/CEO/Co-CEO) may
    use the command."""

    async def predicate(interaction: discord.Interaction) -> bool:
        return isinstance(interaction.user, discord.Member) and member_has_any_role(
            interaction.user, config.staff_role_ids()
        )

    return app_commands.check(predicate)
