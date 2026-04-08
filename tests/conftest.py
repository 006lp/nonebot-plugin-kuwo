from __future__ import annotations

import sys
from pathlib import Path

import pytest
from nonebug import NONEBOT_INIT_KWARGS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def configure_nonebot(request: pytest.FixtureRequest) -> None:
    request.config.stash[NONEBOT_INIT_KWARGS] = {
        "command_start": {"/"},
        "driver": "~httpx",
    }


@pytest.fixture(scope="session", autouse=True)
def after_nonebot_init() -> None:
    from nonebot.adapters.onebot.v11 import Adapter

    import nonebot
    import nonebot_plugin_kuwo

    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)
    nonebot_plugin_kuwo.init_plugin()
