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

import asyncpg
import crescent
import hikari

from starboard.config import CONFIG
from starboard.core.permrole import get_permroles
from starboard.database import PermRole, Starboard, goc_guild
from starboard.database.models.permrole import PermRoleStarboard
from starboard.exceptions import StarboardErr, StarboardNotFound
from starboard.undefined import UNDEF

from ._checks import has_guild_perms
from ._converters import disid
from ._utils import TRIBOOL, TRIBOOL_CHOICES, optiond

if TYPE_CHECKING:
    from starboard.bot import Bot


plugin = crescent.Plugin("permrole-commands")
permrole = crescent.Group(
    "permroles",
    "Manage permroles",
    [has_guild_perms(hikari.Permissions.MANAGE_ROLES)],
)


@plugin.include
@permrole.child
@crescent.command(name="view", description="View PermRoles for this server")
async def view_permroles(ctx: crescent.Context) -> None:
    assert ctx.guild
    bot = cast("Bot", ctx.app)

    pr = await get_permroles(ctx.guild)

    if not pr:
        raise StarboardErr("This server has no PermRoles.")

    embed = bot.embed(title="PermRoles")
    for r in pr:
        obj = ctx.guild.get_role(r.permrole.id)
        if obj:
            name = obj.name
        else:
            name = f"Deleted Role {r.permrole.id}"
        embed.add_field(
            name=name,
            inline=True,
            value=(
                f"vote: {r.permrole.vote}\n"
                f"receive-votes: {r.permrole.recv_votes}\n"
                f"gain-xproles: {r.permrole.xproles}\n"
                + (
                    "\n".join(
                        f"\nPermissions for <#{sid}>\n"
                        f"vote: {conf.vote}\n"
                        f"receive-votes: {conf.recv_votes}\n"
                        for sid, conf in r.starboards.items()
                    )
                )
            ),
        )

    await ctx.respond(embed=embed)


@plugin.include
@permrole.child
@crescent.command(name="create", description="Create a PermRole")
class CreatePermRole:
    role = crescent.option(hikari.Role, "The role to use as a PermRole")

    async def callback(self, ctx: crescent.Context) -> None:
        assert ctx.guild_id

        count = await PermRole.count(guild_id=ctx.guild_id)
        if count > CONFIG.max_permroles:
            raise StarboardErr(
                f"You can only have up to {CONFIG.max_permroles} PermRoles."
            )

        await goc_guild(ctx.guild_id)
        try:
            await PermRole(id=self.role.id, guild_id=ctx.guild_id).create()
        except asyncpg.UniqueViolationError:
            raise StarboardErr(f"**{self.role}** is already a PermRole.")

        await ctx.respond(f"**{self.role}** is now a PermRole.")


@plugin.include
@permrole.child
@crescent.command(name="delete", description="Delete a PermRole")
class DeletePermRole:
    permrole = crescent.option(
        hikari.Role, "The PermRole to delete", default=None
    )
    permrole_id = crescent.option(
        str,
        "The ID of the PermRole to delete",
        default=None,
        name="permrole-id",
    )

    async def callback(self, ctx: crescent.Context) -> None:
        if not (self.permrole or self.permrole_id):
            raise StarboardErr("Please specify a PermRole to delete.")

        if self.permrole and self.permrole_id:
            raise StarboardErr(
                "You can only specify either the role or the ID."
            )

        roleid: int
        if self.permrole:
            roleid = self.permrole.id
        else:
            roleid = disid(self.permrole_id)

        ret = (
            await PermRole.delete_query()
            .where(id=roleid, guild_id=ctx.guild_id)
            .execute()
        )
        if self.permrole_id:
            name = self.permrole_id
        else:
            assert self.permrole
            name = self.permrole.name
        if not ret:
            raise StarboardErr(f"**{name}** is not a PermRole.")

        await ctx.respond(f"Deleted PermRole **{name}**.")


@plugin.include
@permrole.child
@crescent.command(
    name="edit", description="Edit the permissions for a PermRole"
)
class EditPermRoleGlobal:
    permrole = crescent.option(hikari.Role, "The PermRole to edit")

    vote = optiond(str, "Whether to allow voting", choices=TRIBOOL_CHOICES)
    recv_votes = optiond(
        str,
        "Whether to allow receiving votes",
        choices=TRIBOOL_CHOICES,
        name="receive-votes",
    )
    xproles = optiond(
        str,
        "Whether to allow gaining XPRoles",
        choices=TRIBOOL_CHOICES,
        name="gain-xproles",
    )

    async def callback(self, ctx: crescent.Context) -> None:
        pr = await PermRole.exists(id=self.permrole.id)
        if not pr:
            raise StarboardErr(f"**{self.permrole}** is not a PermRole.")

        for k, v in self.__dict__.items():
            if k == "permrole":
                continue

            if v is UNDEF.UNDEF:
                continue

            setattr(pr, k, TRIBOOL[v])

        await pr.save()
        await ctx.respond(f"Settings for **{self.permrole}** update.")


@plugin.include
@permrole.child
@crescent.command(
    name="edit-starboard",
    description="Edit the permissions of a PermRole for a specific starboard",
)
class EditPermRoleStarboard:
    permrole = crescent.option(hikari.Role, "The PermRole to edit")
    starboard = crescent.option(
        hikari.TextableGuildChannel, "The starboard to edit the PermRole for"
    )

    vote = optiond(str, "Whether to allow voting", choices=TRIBOOL_CHOICES)
    recv_votes = optiond(
        str,
        "Whether to allow receiving votes",
        choices=TRIBOOL_CHOICES,
        name="receive-votes",
    )

    async def callback(self, ctx: crescent.Context) -> None:
        sb = await Starboard.exists(id=self.starboard.id)
        if not sb:
            raise StarboardNotFound(self.starboard.id)

        try:
            pr = await PermRoleStarboard(
                permrole_id=self.permrole.id, starboard_id=sb.id
            ).create()
        except asyncpg.ForeignKeyViolationError:
            raise StarboardErr(f"**{self.permrole}** is not a PermRole.")
        except asyncpg.UniqueViolationError:
            pr = await PermRoleStarboard.fetch(
                permrole_id=self.permrole.id, starboard_id=sb.id
            )

        if self.vote is not UNDEF.UNDEF:
            pr.vote = TRIBOOL[self.vote]
        if self.recv_votes is not UNDEF.UNDEF:
            pr.recv_votes = TRIBOOL[self.recv_votes]

        await pr.save()
        await ctx.respond(
            f"Updated **{self.permrole}** for <#{self.starboard.id}>."
        )
