#!/usr/bin/env python
from __future__ import annotations

from loto.orchestration import resource_aware_broad_campaign_impl as _impl
from loto.orchestration.resource_aware_broad_campaign_impl import *  # noqa: F401,F403

os = _impl.os
subprocess = _impl.subprocess


if __name__ == "__main__":
    raise SystemExit(main())  # noqa: F405
