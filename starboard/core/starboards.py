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

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable

import hikari
from apgorm import sql

from starboard.database import Message, SBMessage, Star, Starboard

from .sb_messages import get_sbmsg_content

if TYPE_CHECKING:
    from starboard.bot import Bot


async def refresh_message(
    bot: Bot, orig_message: Message, sbids: list[int] | None = None
) -> None:
    if orig_message.id in bot.refresh_message_lock:
        return
    bot.refresh_message_lock.add(orig_message.id)
    try:
        await _refresh_message(bot, orig_message, sbids)
    finally:
        bot.refresh_message_lock.remove(orig_message.id)


async def _refresh_message(
    bot: Bot, orig_message: Message, sbids: list[int] | None
) -> None:
    if sbids:
        starboards = (
            await Starboard.fetch_query()
            .where(Starboard.id.eq(sql(sbids).any))
            .fetchmany()
        )
    else:
        starboards = (
            await Starboard.fetch_query()
            .where(guild_id=orig_message.guild_id)
            .fetchmany()
        )

    for sb in starboards:
        await _refresh_message_for_starboard(bot, orig_message, sb)


async def _refresh_message_for_starboard(
    bot: Bot, orig_msg: Message, starboard: Starboard
) -> None:
    orig_msg_obj = await bot.cache.gof_message(
        orig_msg.channel_id,
        orig_msg.id,
    )

    starcount = await _get_star_count(orig_msg.id, starboard.id)
    action = _get_action(orig_msg, starboard, starcount, orig_msg_obj is None)

    sbmsg = await SBMessage.exists(
        message_id=orig_msg.id,
        starboard_id=starboard.id,
    )
    if (
        sbmsg is not None
        and sbmsg.last_known_star_count == starcount
        and not action.remove
    ):
        return
    if not sbmsg:
        sbmsg = await SBMessage(
            message_id=orig_msg.id, starboard_id=starboard.id
        ).create()
    if sbmsg.sb_message_id is not None:
        sbmsg_obj = await bot.cache.gof_message(
            sbmsg.starboard_id,
            sbmsg.sb_message_id,
        )
    else:
        sbmsg_obj = None

    if action.add and sbmsg_obj is None:
        if orig_msg_obj:
            content, embed = await get_sbmsg_content(
                bot,
                starboard,
                orig_msg_obj,
                orig_msg,
                starcount,
            )
            assert embed
            sbmsg_obj = await _send(bot, starboard, content, embed)
            if sbmsg_obj:
                sbmsg.sb_message_id = sbmsg_obj.id
                await sbmsg.save()
                if starboard.autoreact:
                    for emoji in starboard.star_emojis:
                        assert emoji
                        _emoji: hikari.UnicodeEmoji | hikari.CustomEmoji
                        try:
                            __emoji = bot.cache.get_emoji(int(emoji))
                            if __emoji is None:
                                continue
                            _emoji = __emoji
                        except ValueError:
                            _emoji = hikari.UnicodeEmoji.parse(emoji)
                        try:
                            await sbmsg_obj.add_reaction(_emoji)
                        except (
                            hikari.ForbiddenError,
                            hikari.BadRequestError,
                            hikari.NotFoundError,
                        ):
                            pass

    elif action.remove:
        if sbmsg_obj is not None:
            sbmsg.sb_message_id = None
            await _delete(bot, starboard, sbmsg_obj)

    elif sbmsg_obj is not None:
        # edit the message

        if orig_msg_obj:
            content, embed = await get_sbmsg_content(
                bot,
                starboard,
                orig_msg_obj,
                orig_msg,
                starcount,
            )
            assert embed
            if starboard.link_edits:
                await _edit(bot, starboard, sbmsg_obj, content, embed)
            else:
                await _edit(bot, starboard, sbmsg_obj, content, None)
            await asyncio.sleep(5)
        else:
            content, _ = await get_sbmsg_content(
                bot,
                starboard,
                None,
                orig_msg,
                starcount,
            )
            await _edit(bot, starboard, sbmsg_obj, content, None)

    else:
        sbmsg.sb_message_id = None

    sbmsg.last_known_star_count = starcount
    await sbmsg.save()


async def _edit(
    bot: Bot,
    starboard: Starboard,
    message: hikari.Message,
    content: str | None,
    embed: hikari.Embed | None,
) -> None:
    if message.author.id != bot.me.id:
        wh = await _webhook(bot, starboard, False)
        if (not wh) or wh.webhook_id != message.author.id:
            return

        await wh.edit_message(
            message,
            content=content or hikari.UNDEFINED,
            embed=embed or hikari.UNDEFINED,
        )

    else:
        await message.edit(
            content=content or hikari.UNDEFINED,
            embed=embed or hikari.UNDEFINED,
        )


async def _delete(
    bot: Bot,
    starboard: Starboard,
    message: hikari.Message,
) -> None:
    if message.author.id == bot.me.id:
        return await message.delete()

    else:
        wh = await _webhook(bot, starboard, False)
        if wh is not None:
            await wh.delete_message(message)

        else:
            # try anyways. will work if bot has manage_messages
            try:
                await message.delete()
            except hikari.ForbiddenError:
                pass


async def _send(
    bot: Bot,
    starboard: Starboard,
    content: str,
    embed: hikari.Embed,
) -> hikari.Message | None:
    webhook = await _webhook(bot, starboard)

    if webhook and starboard.use_webhook:
        try:
            botuser = bot.get_me()
            assert botuser
            return await webhook.execute(
                content,
                embed=embed,
                username=starboard.webhook_name,
                avatar_url=(
                    starboard.webhook_avatar
                    or botuser.avatar_url
                    or botuser.default_avatar_url
                ),
            )
        except hikari.NotFoundError:
            pass

    try:
        return await bot.rest.create_message(
            starboard.id,
            content,
            embed=embed,
        )
    except (hikari.ForbiddenError, hikari.NotFoundError):
        return None


async def _webhook(
    bot: Bot,
    starboard: Starboard,
    allow_create: bool = True,
) -> hikari.ExecutableWebhook | None:
    create = allow_create and starboard.use_webhook
    wh = None
    if starboard.webhook_id is not None:
        wh = await bot.cache.gof_webhook(starboard.webhook_id)
        if not wh:
            starboard.webhook_id = None
            await starboard.save()

    if wh is not None:
        assert isinstance(wh, hikari.ExecutableWebhook)
        return wh

    if not create:
        return None

    try:
        wh = await bot.rest.create_webhook(
            starboard.id,
            name="Starboard Webhook",
            reason="This starboard has use_webhook set to True.",
        )
    except (hikari.ForbiddenError, hikari.NotFoundError):
        return None

    starboard.webhook_id = wh.id
    await starboard.save()

    return wh


def _get_star_count(orig_msg_id: int, starboard_id: int) -> Awaitable[int]:
    return (
        Star.fetch_query()
        .where(
            message_id=orig_msg_id,
            starboard_id=starboard_id,
        )
        .count()
    )


@dataclass(order=True)
class _Actions:
    add: bool
    remove: bool


def _get_action(
    orig_msg: Message,
    starboard: Starboard,
    points: int,
    deleted: bool,
) -> _Actions:
    add_trib: bool | None = None

    # check points
    if points >= starboard.required:
        add_trib = True
    elif points <= starboard.required_remove:
        add_trib = False

    # check deletion
    if deleted and starboard.link_deletes:
        add_trib = False

    # check if forced
    if starboard.id in orig_msg.forced_to:
        add_trib = True

    # check trashed
    if orig_msg.trashed:
        add_trib = False

    # return
    if add_trib is True:
        return _Actions(True, False)
    elif add_trib is None:
        return _Actions(False, False)
    else:
        return _Actions(False, True)
