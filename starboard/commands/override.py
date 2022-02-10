from __future__ import annotations

from typing import TYPE_CHECKING, cast

import asyncpg
import crescent
import hikari

from starboard.core.config import StarboardConfig, validate_changes
from starboard.database import Override, Starboard
from starboard.exceptions import (
    CommandErr,
    OverrideNotFound,
    StarboardNotFound,
)

from ._checks import has_guild_perms
from ._converters import channel_list
from ._sb_config import EditStarboardConfig
from ._utils import pretty_sb_config

if TYPE_CHECKING:
    from starboard.bot import Bot


plugin = crescent.Plugin("overrides")
overrides = crescent.Group(
    "overrides",
    "Manage setting overrides",
    hooks=[has_guild_perms(hikari.Permissions.MANAGE_GUILD)],
)


@plugin.include
@overrides.child
@crescent.command(name="view", description="View setting overrides")
class ViewSettingOverrides:
    name = crescent.option(str, "The override to view", default=None)

    async def callback(self, ctx: crescent.Context) -> None:
        bot = cast("Bot", ctx.app)
        if self.name:
            ov = await Override.exists(guild_id=ctx.guild_id, name=self.name)
            if not ov:
                raise OverrideNotFound(self.name)

            sb = await Starboard.fetch(id=ov.starboard_id)

            config = StarboardConfig(sb, ov)
            options = pretty_sb_config(config, bot, ov.overrides.keys())

            cs = ", ".join(f"<#{c}>" for c in ov.channel_ids)
            embed = bot.embed(
                title=f"Override {self.name}",
                description=(
                    f"These are the settings for <#{sb.id}> in the channels "
                    f"{cs}."
                ),
            )

            embed.add_field(
                name="Appearance", value=options.appearance, inline=True
            )
            embed.add_field(
                name="Requirements", value=options.requirements, inline=True
            )
            embed.add_field(
                name="Behaviour", value=options.behaviour, inline=True
            )

            await ctx.respond(embed=embed)
        else:
            q = Override.fetch_query()
            q.where(guild_id=ctx.guild_id)
            ovs = await q.fetchmany()

            if not ovs:
                await ctx.respond(
                    "This server has no overrides.", ephemeral=True
                )
                return

            embed = bot.embed(
                title="Setting Overrides",
                description="\n".join(
                    f"{o.name}: **{len(o.overrides)}** overrwritten settings "
                    f"for <#{o.starboard_id}> in **{len(o.channel_ids)}** "
                    "channels."
                    for o in ovs
                ),
            )

            await ctx.respond(embed=embed)


@plugin.include
@overrides.child
@crescent.command(name="create", description="Create a setting override")
class CreateOverride:
    name = crescent.option(str, "The name of the override")
    channels = crescent.option(
        str, "A list of channels that this override applies to"
    )
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard this override applies to"
    )
    copy_from = crescent.option(
        str,
        "An existing override to copy options from",
        default=None,
        name="copy-from",
    )

    async def callback(self, ctx: crescent.Context) -> None:
        if self.copy_from is not None:
            ov = await Override.exists(
                guild_id=ctx.guild_id, name=self.copy_from
            )
            if not ov:
                raise OverrideNotFound(self.copy_from)

        else:
            ov = None

        o = Override(
            guild_id=ctx.guild_id,
            name=self.name,
            starboard_id=self.starboard.id,
            channel_ids=channel_list(self.channels),
            _overrides=ov._overrides if ov else "{}",
        )
        try:
            await o.create()
        except asyncpg.UniqueViolationError:
            raise CommandErr(
                f"There is already an override with the name '{self.name}'."
            )
        except asyncpg.ForeignKeyViolationError:
            raise StarboardNotFound(self.starboard.id)

        await ctx.respond(f"Created override with name '{self.name}'.")


@plugin.include
@overrides.child
@crescent.command(name="delete", description="Delete a setting override")
class DeleteOverride:
    name = crescent.option(str, "The name of the override")

    async def callback(self, ctx: crescent.Context) -> None:
        q = Override.delete_query()
        q.where(guild_id=ctx.guild_id)
        q.where(name=self.name)
        ret = await q.execute()

        if ret:
            await ctx.respond(f"Deleted setting override '{self.name}'.")
        else:
            raise OverrideNotFound(self.name)


@plugin.include
@overrides.child
@crescent.command(name="edit", description="Modify a setting override")
class EditOverride(EditStarboardConfig):
    name = crescent.option(str, "The name of the override")

    async def callback(self, ctx: crescent.Context) -> None:
        ov = await Override.exists(guild_id=ctx.guild_id, name=self.name)
        if not ov:
            raise OverrideNotFound(self.name)

        options = self._options()
        await validate_changes(**options)

        opt = ov.overrides
        for k, v in options.items():
            opt[k] = v
            ov.overrides = opt

        await ov.save()
        await ctx.respond(f"Updated settings for override '{self.name}'.")
