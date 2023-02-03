# MIT License
#
# Copyright (c) 2022 TrigonDev
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import crescent
import hikari
from asyncpg import UniqueViolationError

from starboard.database import AutoStarChannel, Guild
from starboard.exceptions import StarboardError
from starboard.undefined import UNDEF
from starboard.views import Confirm

from ._autocomplete import asc_autocomplete
from ._checks import has_guild_perms
from ._converters import any_emoji_list, clean_name
from ._utils import optiond, pretty_emoji_str

if TYPE_CHECKING:
    from starboard.bot import Bot


plugin = crescent.Plugin()


autostar = crescent.Group(
    "autostar",
    "Manage autostar channels",
    hooks=[has_guild_perms(hikari.Permissions.MANAGE_GUILD)],
)


@plugin.include
@autostar.child
@crescent.command(name="create", description="Create an autostar channel")
class CreateAutoStar:
    channel = crescent.option(
        hikari.TextableGuildChannel, "The channel to make an autostar channel"
    )
    name = crescent.option(str, "The name of the autostar channel")

    async def callback(self, ctx: crescent.Context) -> None:
        bot = cast("Bot", ctx.app)
        assert ctx.guild_id

        await Guild.get_or_create(ctx.guild_id)
        name = clean_name(self.name)

        try:
            await AutoStarChannel(
                channel_id=self.channel.id, guild_id=ctx.guild_id, name=name
            ).create()
        except UniqueViolationError:
            raise StarboardError(
                f"An autostar channel with the name '{name}' already "
                "exists."
            ) from None

        bot.database.asc.add(self.channel.id)
        await ctx.respond(
            f"Created autostar channel '{name}' in <#{self.channel.id}>."
        )


@plugin.include
@autostar.child
@crescent.command(name="delete", description="Delete an autostar channel")
class DeleteAutoStar:
    autostar = crescent.option(
        str, "The autostar channel to delete", autocomplete=asc_autocomplete
    )

    async def callback(self, ctx: crescent.Context) -> None:
        assert ctx.guild_id

        asc = await AutoStarChannel.from_name(ctx.guild_id, self.autostar)

        confirm = Confirm(ctx.user.id, danger=True)
        msg = await ctx.respond(
            "Are you sure? All data for this autostar channel will be lost "
            "**permanently**.",
            components=confirm.build(),
            ensure_message=True,
        )
        await confirm.start(msg)
        await confirm.wait()

        if not confirm.result:
            await msg.edit("Cancelled.", components=[])
            return

        await asc.delete()
        await msg.edit(
            f"Deleted autostar channel '{asc.name}'.", components=[]
        )


@plugin.include
@autostar.child
@crescent.command(
    name="view", description="View the configuration for autostar channels"
)
class ViewAutoStar:
    autostar = crescent.option(
        str,
        "The autostar channel to view",
        autocomplete=asc_autocomplete,
        default=None,
    )

    async def callback(self, ctx: crescent.Context) -> None:
        assert ctx.guild_id
        bot = cast("Bot", ctx.app)

        if self.autostar:
            asc = await AutoStarChannel.from_name(ctx.guild_id, self.autostar)
            es = pretty_emoji_str(*asc.emojis, bot=bot)
            maxc = asc.max_chars if asc.max_chars is not None else "none"
            notes: list[str] = []
            if asc.prem_locked:
                notes.append(
                    "This AutoStar channel exceeds the non-premium limit and "
                    "is locked. If you believe this is a mistake, please run "
                    "`/premium locks refresh`."
                )
            ch = bot.cache.get_guild_channel(asc.channel_id)
            chname = f"#{ch.name}" if ch else "Deleted Channel"
            await ctx.respond(
                embed=bot.embed(
                    title=f"{asc.name} in {chname}",
                    description=(
                        f"emojis: {es}\n"
                        f"min-chars: {asc.min_chars}\n"
                        f"max-chars: {maxc}\n"
                        f"require-image: {asc.require_image}\n"
                        f"delete-invalid: {asc.delete_invalid}\n"
                        + ("\n" + "\n\n".join(notes) if notes else "")
                    ),
                )
            )

        else:
            ascs = (
                await AutoStarChannel.fetch_query()
                .where(guild_id=ctx.guild_id)
                .fetchmany()
            )

            if not ascs:
                raise StarboardError("This server has no autostar channels.")

            lines: list[str] = []
            for asc in ascs:
                if channel := bot.cache.get_guild_channel(asc.channel_id):
                    assert channel.name
                    chname = f"#{channel.name}"
                else:
                    chname = f"Deleted Channel {asc.channel_id}"
                name = f"{asc.name} in {chname}"
                if asc.prem_locked:
                    name = f"{name} (Locked)"

                es = pretty_emoji_str(*asc.emojis, bot=bot)
                lines.append(f"{name}: {es}")

            embed = bot.embed(
                title="Autostar Channels", description="\n".join(lines)
            )
            await ctx.respond(embed=embed)


@plugin.include
@autostar.child
@crescent.command(name="rename", description="Rename an autostar channel")
class RenameAutoStar:
    autostar = crescent.option(
        str, "The autostar channel to rename", autocomplete=asc_autocomplete
    )
    name = crescent.option(str, "The new name of the autostar channel")

    async def callback(self, ctx: crescent.Context) -> None:
        assert ctx.guild_id

        asc = await AutoStarChannel.from_name(ctx.guild_id, self.autostar)
        name = clean_name(self.name)
        asc.name = name
        await asc.save()

        await ctx.respond(
            f"Renamed autostar channel '{self.autostar}' to '{name}'."
        )


@plugin.include
@autostar.child
@crescent.command(name="edit", description="Edit an autostar channel")
class EditAutoStar:
    autostar = crescent.option(
        str, "The autostar channel to edit", autocomplete=asc_autocomplete
    )

    min_chars = optiond(
        int, "The minimum length of messages", name="min-chars", min_value=0
    )
    max_chars = optiond(
        int,
        "The maximum length of messages (use -1 to disable)",
        name="max-chars",
        min_value=-1,
    )
    require_image = optiond(
        bool, "Whether images must include images", name="require-image"
    )
    delete_invalid = optiond(
        bool,
        "Whether to delete messages that don't meet requirements",
        name="delete-invalid",
    )

    async def callback(self, ctx: crescent.Context) -> None:
        assert ctx.guild_id

        params = self.__dict__.copy()
        del params["autostar"]

        asc = await AutoStarChannel.from_name(ctx.guild_id, self.autostar)

        if params.get("max_chars") == -1:
            params["max_chars"] = None

        for k, v in params.items():
            if v is UNDEF.UNDEF:
                continue
            setattr(asc, k, v)

        await asc.save()
        await ctx.respond(f"Updated settings for '{asc.name}'.")


@plugin.include
@autostar.child
@crescent.command(name="set-emojis", description="Set the emojis")
class SetEmoji:
    autostar = crescent.option(
        str, "The autostar channel to edit", autocomplete=asc_autocomplete
    )
    emojis = crescent.option(str, "A list of emojis to use")

    async def callback(self, ctx: crescent.Context) -> None:
        assert ctx.guild_id

        asc = await AutoStarChannel.from_name(ctx.guild_id, self.autostar)
        emojis = any_emoji_list(self.emojis)

        asc.emojis = emojis
        await asc.save()
        await ctx.respond("Done.")
