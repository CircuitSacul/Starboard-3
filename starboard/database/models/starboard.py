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

from typing import Any, Callable

import apgorm
from apgorm import types

from starboard.config import CONFIG

from ._validators import str_len, int_range, valid_emoji
from ._converters import DecimalC, NonNullArray, NullDecimalC
from .guild import Guild


def _validate(
    key: str, changes: dict[str, Any], func: Callable[[Any], bool]
) -> None:
    if key in changes:
        assert func(changes[key])


def validate_sb_changes(**changes: Any) -> None:
    _validate(
        "webhook_name", changes, str_len("webhook-name", CONFIG.max_whn_len)
    )
    _validate(
        "webhook_avatar",
        changes,
        str_len("webhook-avatar", CONFIG.max_wha_len),
    )
    _validate(
        "required",
        changes,
        int_range("required", CONFIG.min_required, CONFIG.max_required),
    )
    _validate(
        "required_remove",
        changes,
        int_range(
            "required-remove",
            CONFIG.min_required_remove,
            CONFIG.max_required_remove,
        ),
    )
    _validate(
        "cooldown_period",
        changes,
        int_range(
            "the cooldown period (seconds)", None, CONFIG.max_cooldown_period
        ),
    )
    _validate(
        "cooldown_count",
        changes,
        int_range(
            "the capacity of the cooldown (count)",
            None,
            CONFIG.max_cooldown_cap,
        ),
    )
    _validate("display_emoji", changes, valid_emoji)


class Starboard(apgorm.Model):
    id = types.Numeric().field().with_converter(DecimalC)
    guild_id = types.Numeric().field().with_converter(DecimalC)

    webhook_id = types.Numeric().nullablefield().with_converter(NullDecimalC)

    # Appearance
    color = types.Int().field(default=CONFIG.color)
    display_emoji = types.Text().nullablefield(default="⭐")
    ping_author = types.Boolean().field(default=False)
    use_server_profile = types.Boolean().field(default=True)
    extra_embeds = types.Boolean().field(default=True)
    use_webhook = types.Boolean().field(default=False)
    webhook_name = types.Text().field(default="Starboard")
    webhook_avatar = types.Text().nullablefield()

    # Requirements
    required = types.SmallInt().field(default=3)
    required_remove = types.SmallInt().field(default=0)
    star_emojis = (
        types.Array(types.Text())
        .field(default_factory=lambda: list(["⭐"]))
        .with_converter(NonNullArray(str))
    )
    self_star = types.Boolean().field(default=False)
    allow_bots = types.Boolean().field(default=True)
    require_image = types.Boolean().field(default=False)

    # Behaviour
    enabled = types.Boolean().field(default=True)
    autoreact = types.Boolean().field(default=True)
    remove_invalid = types.Boolean().field(default=True)
    link_deletes = types.Boolean().field(default=False)
    link_edits = types.Boolean().field(default=True)
    disable_xp = types.Boolean().field(default=False)
    private = types.Boolean().field(default=False)
    cooldown_enabled = types.Boolean().field(default=False)
    cooldown_count = types.SmallInt().field(default=5)
    cooldown_period = types.SmallInt().field(default=5)

    # ForeignKeys & PrimaryKey
    guild_id_fk = apgorm.ForeignKey(guild_id, Guild.id)

    primary_key = (id,)
