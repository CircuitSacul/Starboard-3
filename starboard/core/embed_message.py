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

from textwrap import indent
from typing import TYPE_CHECKING

import hikari

if TYPE_CHECKING:
    from starboard.bot import Bot


ZWS = "​"


def get_raw_message_text(
    channel_id: int,
    author_id: int,
    display_emoji: hikari.UnicodeEmoji | hikari.CustomEmoji | None,
    ping_author: bool,
    point_count: int,
) -> str:
    text = ""
    if display_emoji:
        text += display_emoji.mention + " "

    text += f"**{point_count} |** <#{channel_id}>"

    if ping_author:
        text += f" **(**<@{author_id}>**)**"

    return text


async def embed_message(
    bot: Bot,
    message: hikari.Message,
    guild_id: int,
    color: int,
    display_emoji: hikari.CustomEmoji | hikari.UnicodeEmoji | None,
    nicknames: bool,
    ping_author: bool,
    point_count: int,
) -> tuple[str, hikari.Embed]:
    channel = await bot.cache.gof_guild_channel_wnsfw(message.channel_id)
    assert channel is not None
    nsfw = channel.is_nsfw
    assert nsfw is not None

    name, avatar = await _get_name_and_avatar(
        bot, guild_id, message.author, nicknames
    )

    embed = (
        hikari.Embed(
            description=_get_main_content(message),
            color=color,
            timestamp=message.created_at,
        )
        .set_author(
            name=name,
            icon=avatar,
        )
        .add_field(
            name=ZWS,
            value=f"[Go to Message]({message.make_link(guild_id)})",
        )
    )

    await _extract_reply(bot, message, guild_id, nicknames, embed)

    return (
        get_raw_message_text(
            message.channel_id,
            message.author.id,
            display_emoji,
            ping_author,
            point_count,
        ),
        embed,
    )


async def _get_name_and_avatar(
    bot: Bot,
    guild: hikari.SnowflakeishOr[hikari.PartialGuild],
    user: hikari.User,
    nicknames: bool,
) -> tuple[str, hikari.URL]:
    if not nicknames:
        return (user.username, user.avatar_url or user.default_avatar_url)

    member = await bot.cache.gof_member(guild, user)
    if not member:
        return (user.username, user.avatar_url or user.default_avatar_url)

    return (
        member.nickname or member.username,
        member.guild_avatar_url
        or member.avatar_url
        or member.default_avatar_url,
    )


async def _extract_reply(
    bot: Bot,
    message: hikari.Message,
    guild_id: int,
    nicknames: bool,
    embed: hikari.Embed,
) -> None:
    if (ref := message.referenced_message) is not None:
        name, _ = await _get_name_and_avatar(
            bot,
            guild_id,
            ref.author,
            nicknames,
        )
        embed.add_field(
            name=f"Replying To {name}", value=ref.content or "*file only*"
        )


def _str_embed(embed: hikari.Embed) -> str:
    return indent(
        (
            "\n\n"
            + (
                (
                    f"**__{embed.title}__**\n"
                    if not embed.url
                    else f"**__[{embed.title}]({embed.url})__**\n"
                )
                if embed.title
                else ""
            )
            + (f"{embed.description}\n" if embed.description else "")
            + (
                "\n".join(
                    [
                        (f"**{field.name}**\n{field.value}")
                        for field in embed.fields
                    ]
                )
            )
        ),
        "> ",
    )


def _get_main_content(message: hikari.Message) -> str | None:
    raw_content = message.content or ""

    for e in message.embeds:
        raw_content += _str_embed(e)

    return raw_content or None