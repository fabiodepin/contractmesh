#!/usr/bin/env python3
"""No-op structural adapter for tests and default registration."""

from __future__ import annotations

from typing import Any


def load_edges(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
    return []
