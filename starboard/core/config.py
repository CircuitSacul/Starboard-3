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

from typing import TYPE_CHECKING, Any, Iterable

import emoji
from apgorm import sql

from starboard.config import CONFIG
from starboard.database import Override
from starboard.exceptions import StarboardErr

if TYPE_CHECKING:
    from starboard.database import Starboard


class StarboardConfig:
    def __init__(
        self, starboard: Starboard, overrides: Iterable[Override] | None
    ) -> None:
        self.starboard = starboard
        self.overrides = overrides or []

    def __getattr__(self, key: str) -> Any:
        for ov in self.overrides:
            if key in ov.overrides.keys():
                return ov.overrides[key]
        return getattr(self.starboard, key)

    # Appearance
    color: int
    display_emoji: str | None
    ping_author: bool
    use_server_profile: bool
    extra_embeds: bool
    use_webhook: bool
    webhook_name: str
    webhook_avatar: str | None

    # Requirements
    required: int
    required_remove: int
    star_emojis: list[str]
    self_star: bool
    allow_bots: bool
    images_only: bool

    # Behaviour
    enabled: bool
    autoreact: bool
    remove_invalid: bool
    link_deletes: bool
    link_edits: bool
    disable_xp: bool
    private: bool
    cooldown_enabled: bool
    cooldown_count: int
    cooldown_period: int


async def get_config(sb: Starboard, channel_id: int) -> StarboardConfig:
    ov = await fetch_overrides(sb.id, channel_id)
    return StarboardConfig(sb, ov)


async def fetch_overrides(sb: int, ch: int) -> Iterable[Override]:
    q = Override.fetch_query()
    q.where(starboard_id=sb)
    q.where(sql(ch).eq(Override.channel_ids.any))
    return await q.fetchmany()


async def validate_changes(**changes: Any) -> None:
    if (v := changes.get("webhook_name")) and len(v) > CONFIG.max_whn_len:
        raise StarboardErr(
            f"`webhook-name` cannot be longer than {CONFIG.max_wha_len} "
            "characters."
        )
    if (v := changes.get("webhook_avatar")) and len(v) > CONFIG.max_wha_len:
        raise StarboardErr(
            f"`webhook-avatar` cannot be longer than {CONFIG.max_wha_len} "
            "characters."
        )
    if (v := changes.get("required")) and (
        v > CONFIG.max_required or v < CONFIG.min_required
    ):
        raise StarboardErr(
            f"`required` must be at least {CONFIG.min_required} and at most "
            f"{CONFIG.max_required}."
        )
    if (v := changes.get("required_remove")) and (
        v > CONFIG.max_required_remove or v < CONFIG.min_required_remove
    ):
        raise StarboardErr(
            f"`required-remove` must be at least {CONFIG.min_required_remove} "
            f"and at most {CONFIG.max_required_remove}."
        )
    if (v := changes.get("cooldown_period")) and (
        v > CONFIG.max_cooldown_period or v < 1
    ):
        raise StarboardErr(
            "The length (period) of the cooldown must be at least 1 and at "
            f"most {CONFIG.max_cooldown_period}. You passed {v}."
        )
    if (v := changes.get("cooldown_count")) and (
        v > CONFIG.max_cooldown_cap or v < 1
    ):
        raise StarboardErr(
            "The capacity of the cooldown must be at least 1 and at most "
            f"{CONFIG.max_cooldown_cap}. You passed {v}."
        )
    if v := changes.get("display_emoji"):
        _validate_emoji(v)


def _validate_emoji(value: str) -> None:
    if value.isalnum():
        return

    if emoji.is_emoji(value):  # type: ignore
        return

    raise StarboardErr(f"{value} is not a valid emoji.")
