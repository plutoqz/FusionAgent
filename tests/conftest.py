from __future__ import annotations

import inspect

import httpx
import pytest


_HTTPX_CLIENT_INIT = httpx.Client.__init__


if "app" not in inspect.signature(_HTTPX_CLIENT_INIT).parameters:

    def _httpx_client_init_compat(self, *args, app=None, **kwargs):
        del app
        return _HTTPX_CLIENT_INIT(self, *args, **kwargs)

    httpx.Client.__init__ = _httpx_client_init_compat


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "realdata: tests that depend on local Benin source data")
