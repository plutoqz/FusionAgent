from __future__ import annotations

import inspect

import httpx


_HTTPX_CLIENT_INIT = httpx.Client.__init__


if "app" not in inspect.signature(_HTTPX_CLIENT_INIT).parameters:

    def _httpx_client_init_compat(self, *args, app=None, **kwargs):
        del app
        return _HTTPX_CLIENT_INIT(self, *args, **kwargs)

    httpx.Client.__init__ = _httpx_client_init_compat
