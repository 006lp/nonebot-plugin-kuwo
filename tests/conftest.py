from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from nonebug import NONEBOT_INIT_KWARGS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCALSTORE_ROOT = PROJECT_ROOT / "tests" / ".localstore"

os.environ.setdefault("LOCALSTORE_CACHE_DIR", str(LOCALSTORE_ROOT / "cache"))
os.environ.setdefault("LOCALSTORE_CONFIG_DIR", str(LOCALSTORE_ROOT / "config"))
os.environ.setdefault("LOCALSTORE_DATA_DIR", str(LOCALSTORE_ROOT / "data"))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session", autouse=True)
def configure_nonebot(request: pytest.FixtureRequest) -> None:
    request.config.stash[NONEBOT_INIT_KWARGS] = {
        "command_start": {"/"},
        "driver": "~httpx",
        "localstore_cache_dir": LOCALSTORE_ROOT / "cache",
        "localstore_config_dir": LOCALSTORE_ROOT / "config",
        "localstore_data_dir": LOCALSTORE_ROOT / "data",
    }


@pytest.fixture(scope="session", autouse=True)
def after_nonebot_init() -> None:
    import nonebot

    nonebot.load_plugin("nonebot_plugin_kuwo")

    driver = nonebot.get_driver()
    lifespan = getattr(driver, "_lifespan", None)
    if lifespan is None:
        return

    for attr_name in ("_startup_funcs", "_shutdown_funcs"):
        funcs = getattr(lifespan, attr_name, None)
        if not isinstance(funcs, list):
            continue
        setattr(
            lifespan,
            attr_name,
            [
                func
                for func in funcs
                if getattr(func, "__module__", "") != "nonebot_plugin_htmlrender"
            ],
        )
