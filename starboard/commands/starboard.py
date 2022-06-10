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

from typing import TYPE_CHECKING, Any, cast

import crescent
import hikari

from starboard.config import CONFIG
from starboard.core.config import StarboardConfig
from starboard.database import (
    Guild,
    Override,
    Starboard,
    goc_guild,
    validate_sb_changes,
)
from starboard.exceptions import StarboardError, StarboardNotFound
from starboard.undefined import UNDEF
from starboard.views import Confirm

from ._checks import has_guild_perms
from ._converters import any_emoji_list, any_emoji_str, disid
from ._sb_config import (
    BaseEditStarboardBehavior,
    BaseEditStarboardEmbedStyle,
    BaseEditStarboardRequirements,
    BaseEditStarboardStyle,
)
from ._utils import optiond, pretty_emoji_str, pretty_sb_config

if TYPE_CHECKING:
    from starboard.bot import Bot


plugin = crescent.Plugin("starboards")


starboards = crescent.Group(
    "starboards",
    "Manage Starboards",
    hooks=[has_guild_perms(hikari.Permissions.MANAGE_GUILD)],
)


@plugin.include
@starboards.child
@crescent.command(name="view", description="View a starboard")
class ViewStarboard:
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard to view", default=None
    )

    async def callback(self, ctx: crescent.Context) -> None:
        assert ctx.guild_id
        bot = cast("Bot", ctx.app)

        if self.starboard is None:
            all_starboards = (
                await Starboard.fetch_query()
                .where(guild_id=ctx.guild_id)
                .fetchmany()
            )
            if not all_starboards:
                await ctx.respond(
                    "There are no starboards in this server.", ephemeral=True
                )
                return

            embed = bot.embed(
                title="Starboards",
                description=(
                    "This shows all starboards and their most important "
                    "settings. To view all settings, run this command for a "
                    "specific starboard instead."
                ),
            )

            for sb in all_starboards:
                channel = bot.cache.get_guild_channel(sb.channel_id)
                if channel:
                    assert channel.name is not None
                    name = channel.name
                else:
                    name = f"Deleted Channel {sb.channel_id}"

                if sb.prem_locked:
                    name = f"{name} (Locked)"

                emoji_str = pretty_emoji_str(*sb.upvote_emojis, bot=bot)
                embed.add_field(
                    name=name,
                    value=(
                        f"required: {sb.required}\n"
                        f"self-vote: {sb.self_vote}\n"
                        f"upvote-emojis: {emoji_str}"
                    ),
                    inline=True,
                )
            await ctx.respond(embed=embed)

        else:
            starboard = await Starboard.exists(channel_id=self.starboard.id)
            if not starboard:
                raise StarboardNotFound(self.starboard.id)

            overrides = await Override.count(starboard_id=starboard.channel_id)

            config = pretty_sb_config(StarboardConfig(starboard, None), bot)
            embed = bot.embed(title=self.starboard.name)
            notes: list[str] = []
            if overrides:
                notes.append(
                    f"This starboard also has {overrides} channel-specific "
                    "overrides."
                )
            if starboard.prem_locked:
                notes.append(
                    "This starboard exceeds the non-premium limit and is "
                    "locked. If you believe this is a mistake, run `/premium "
                    "locks refresh`."
                )
            if notes:
                embed.description = "\n\n".join(notes)
            embed.add_field(
                name="General Style", value=config.general_style, inline=True
            )
            embed.add_field(
                name="Embed Style", value=config.embed_style, inline=True
            )
            embed.add_field(
                name="Requirements", value=config.requirements, inline=True
            )
            embed.add_field(
                name="Behavior", value=config.behavior, inline=True
            )

            await ctx.respond(embed=embed)


@plugin.include
@starboards.child
@crescent.command(name="create", description="Add a starboard")
class CreateStarboard:
    channel = crescent.option(
        hikari.TextableGuildChannel, "Channel to use as starboard"
    )

    async def callback(self, ctx: crescent.Context) -> None:
        bot = cast("Bot", ctx.app)
        assert ctx.guild_id
        exists = await Starboard.exists(channel_id=self.channel.id)
        if exists:
            await ctx.respond(
                f"<#{self.channel.id}> is already a starboard.", ephemeral=True
            )
            return

        guild = await goc_guild(ctx.guild_id)
        ip = guild.premium_end is not None

        limit = CONFIG.max_starboards if ip else CONFIG.np_max_starboards
        count = await Starboard.count(guild_id=ctx.guild_id)
        if count >= limit:
            raise StarboardError(
                f"You can only have up to {limit} starboards."
                + (
                    " You can increase this limit with premium."
                    if not ip
                    else ""
                )
            )

        await Starboard(
            channel_id=self.channel.id, guild_id=ctx.guild_id
        ).create()
        bot.cache.invalidate_vote_emojis(ctx.guild_id)

        await ctx.respond(f"Created starboard <#{self.channel.id}>.")


@plugin.include
@starboards.child
@crescent.command(name="delete", description="Remove a starboard")
class DeleteStarboard:
    starboard = crescent.option(
        hikari.TextableGuildChannel, "Starboard to delete.", default=None
    )
    starboard_id = crescent.option(
        str, "Starboard to delete, by ID", default=None, name="starboard-id"
    )

    async def callback(self, ctx: crescent.Context) -> None:
        chid = (
            self.starboard.id if self.starboard else disid(self.starboard_id)
        )
        if not chid:
            raise StarboardError(
                "Please specify either a channel or channel ID."
            )

        bot = cast("Bot", ctx.app)
        assert ctx.guild_id
        confirm = Confirm(ctx.user.id, danger=True)
        msg = await ctx.respond(
            "Are you sure? All data will be lost **permanently**.",
            components=confirm.build(),
            ensure_message=True,
        )
        confirm.start(msg)
        await confirm.wait()

        if not confirm.result:
            await msg.edit("Cancelled.", components=[])
            return

        res = (
            await Starboard.delete_query()
            .where(channel_id=chid, guild_id=ctx.guild_id)
            .execute()
        )
        bot.cache.invalidate_vote_emojis(ctx.guild_id)
        if not res:
            await msg.edit(StarboardNotFound(chid).msg, components=[])
            return

        await msg.edit(f"Deleted starboard <#{chid}>.", components=[])


async def _update_starboard(
    starboard: hikari.InteractionChannel, params: dict[str, Any]
) -> None:
    validate_sb_changes(**params)

    s = await Starboard.exists(channel_id=starboard.id)
    if not s:
        raise StarboardNotFound(starboard.id)

    for k, v in params.items():
        setattr(s, k, v)

    await s.save()


edit = starboards.sub_group("edit", description="Edit a starboard")


@plugin.include
@edit.child
@crescent.command(name="behavior", description="Edit a starboard's behavior")
class EditStarboardBehavior(BaseEditStarboardBehavior):
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard to edit"
    )

    # these options cannot be implemented for overrides, so we put it on the
    # starboard edit command instead of the superclass
    private = optiond(
        bool,
        "Whether to prevent `random` and `moststarred` from using this "
        "starboard",
    )
    xp_multiplier = optiond(
        float, "The XP multiplier for this starboard", name="xp-multiplier"
    )

    def _options(self) -> dict[str, Any]:
        d = super()._options()
        if self.private is not UNDEF.UNDEF:
            d["private"] = self.private
        if self.xp_multiplier is not UNDEF.UNDEF:
            d["xp_multiplier"] = self.xp_multiplier
        return d

    async def callback(self, ctx: crescent.Context) -> None:
        await _update_starboard(self.starboard, self._options())
        await ctx.respond(f"Settings for <#{self.starboard.id}> updated.")


@plugin.include
@edit.child
@crescent.command(name="embed", description="Edit a starboard's embed style")
class EditStarboardEmbedStyle(BaseEditStarboardEmbedStyle):
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard to edit"
    )

    async def callback(self, ctx: crescent.Context) -> None:
        await _update_starboard(self.starboard, self._options())
        await ctx.respond(f"Settings for <#{self.starboard.id}> updated.")


@plugin.include
@edit.child
@crescent.command(
    name="requirements", description="Edit a starboard's requirements"
)
class EditStarboardRequirements(BaseEditStarboardRequirements):
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard to edit"
    )

    async def callback(self, ctx: crescent.Context) -> None:
        await _update_starboard(self.starboard, self._options())
        await ctx.respond(f"Settings for <#{self.starboard.id}> updated.")


@plugin.include
@edit.child
@crescent.command(name="style", description="Edit a starboard's style")
class EditStarboardStyle(BaseEditStarboardStyle):
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard to edit"
    )

    async def callback(self, ctx: crescent.Context) -> None:
        await _update_starboard(self.starboard, self._options())
        await ctx.respond(f"Settings for <#{self.starboard.id}> updated.")


upvote_emojis = starboards.sub_group(
    "emojis", "Modify upvote/downvote emojis for a starboard"
)


@plugin.include
@upvote_emojis.child
@crescent.command(name="set-upvote", description="Set the upvote emojis")
class SetUpvoteEmojis:
    starboard = crescent.option(
        hikari.TextableGuildChannel,
        "The starboard to set the upvote emojis for",
    )
    emojis = crescent.option(str, "A list of emojis to use")

    async def callback(self, ctx: crescent.Context) -> None:
        bot = cast("Bot", ctx.app)
        assert ctx.guild_id
        s = await Starboard.exists(channel_id=self.starboard.id)
        if not s:
            raise StarboardNotFound(self.starboard.id)

        guild = await Guild.fetch(guild_id=ctx.guild_id)
        ip = guild.premium_end is not None
        limit = CONFIG.max_vote_emojis if ip else CONFIG.np_max_vote_emojis

        upvote_emojis = any_emoji_list(self.emojis)
        downvote_emojis = set(s.downvote_emojis)
        downvote_emojis.difference_update(upvote_emojis)
        if len(upvote_emojis) + len(downvote_emojis) > limit:
            raise StarboardError(
                f"You an only have up to {limit} emojis per starboard."
                + (" Get premium to increase this." if not ip else "")
            )
        s.upvote_emojis = list(upvote_emojis)
        s.downvote_emojis = list(downvote_emojis)
        await s.save()
        bot.cache.invalidate_vote_emojis(ctx.guild_id)
        await ctx.respond("Done.")


@plugin.include
@upvote_emojis.child
@crescent.command(name="set-downvote", description="Set the downvote emojis")
class SetDownvoteEmojis:
    starboard = crescent.option(
        hikari.TextableGuildChannel,
        "The starboard to set the upvote emojis for",
    )
    emojis = crescent.option(str, "A list of emojis to use")

    async def callback(self, ctx: crescent.Context) -> None:
        bot = cast("Bot", ctx.app)
        assert ctx.guild_id
        s = await Starboard.exists(channel_id=self.starboard.id)
        if not s:
            raise StarboardNotFound(self.starboard.id)

        guild = await Guild.fetch(guild_id=ctx.guild_id)
        ip = guild.premium_end is not None
        limit = CONFIG.max_vote_emojis if ip else CONFIG.np_max_vote_emojis

        downvote_emojis = any_emoji_list(self.emojis)
        upvote_emojis = set(s.upvote_emojis)
        upvote_emojis.difference_update(downvote_emojis)
        if len(upvote_emojis) + len(downvote_emojis) > limit:
            raise StarboardError(
                f"You an only have up to {limit} emojis per starboard."
                + (" Get premium to increase this." if not ip else "")
            )
        s.upvote_emojis = list(upvote_emojis)
        s.downvote_emojis = list(downvote_emojis)
        await s.save()
        bot.cache.invalidate_vote_emojis(ctx.guild_id)
        await ctx.respond("Done.")


@plugin.include
@upvote_emojis.child
@crescent.command(name="add", description="Add an upvote emoji")
class AddStarEmoji:
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard to add the upvote emoji to"
    )
    emoji = crescent.option(str, "The upvote emoji to add")
    is_downvote = crescent.option(
        bool, "Whether this is a downvote emoji", default=False
    )

    async def callback(self, ctx: crescent.Context) -> None:
        assert ctx.guild_id
        bot = cast("Bot", ctx.app)
        s = await Starboard.exists(channel_id=self.starboard.id)
        if not s:
            raise StarboardNotFound(self.starboard.id)

        e = any_emoji_str(self.emoji)
        upvote_emojis = set(s.upvote_emojis)
        downvote_emojis = set(s.downvote_emojis)

        if self.is_downvote:
            upvote_emojis.discard(e)
            downvote_emojis.add(e)
        else:
            downvote_emojis.discard(e)
            upvote_emojis.add(e)

        guild = await Guild.fetch(guild_id=ctx.guild_id)
        ip = guild.premium_end is not None
        limit = CONFIG.max_vote_emojis if ip else CONFIG.np_max_vote_emojis

        if len(upvote_emojis) + len(downvote_emojis) >= limit:
            raise StarboardError(
                f"You an only have up to {limit} emojis per starboard."
                + (" Get premium to increase this." if not ip else "")
            )

        s.upvote_emojis = list(upvote_emojis)
        s.downvote_emojis = list(downvote_emojis)
        await s.save()
        bot.cache.invalidate_vote_emojis(ctx.guild_id)
        await ctx.respond("Done.")


@plugin.include
@upvote_emojis.child
@crescent.command(name="remove", description="Remove an upvote/downvote emoji")
class RemoveStarEmoji:
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard to remove the emoji from"
    )
    emoji = crescent.option(str, "The emoji to remove")

    async def callback(self, ctx: crescent.Context) -> None:
        bot = cast("Bot", ctx.app)
        assert ctx.guild_id

        s = await Starboard.exists(channel_id=self.starboard.id)
        if not s:
            raise StarboardNotFound(self.starboard.id)

        e = any_emoji_str(self.emoji)
        upvote_emojis = set(s.upvote_emojis)
        downvote_emojis = set(s.downvote_emojis)

        if e in upvote_emojis | downvote_emojis:
            upvote_emojis.discard(e)
            downvote_emojis.discard(e)
        else:
            await ctx.respond(
                f"{e} is not an upvote emoji on <#{s.channel_id}>",
                ephemeral=True,
            )
            return

        s.upvote_emojis = list(upvote_emojis)
        s.downvote_emojis = list(downvote_emojis)
        await s.save()
        bot.cache.invalidate_vote_emojis(ctx.guild_id)
        await ctx.respond("Done.")
