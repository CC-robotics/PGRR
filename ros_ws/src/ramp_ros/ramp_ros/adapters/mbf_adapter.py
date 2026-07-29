"""Capability probe for legacy MBF profiles.

The selected Arena profile is Nav2/DWB. Business logic imports this module only
when an MBF action package is present, avoiding fixed backend action names.
"""

from __future__ import annotations

import importlib.util


def mbf_messages_available() -> bool:
    return importlib.util.find_spec("mbf_msgs") is not None
