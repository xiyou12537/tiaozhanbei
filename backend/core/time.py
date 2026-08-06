from __future__ import annotations

import datetime as dt


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
