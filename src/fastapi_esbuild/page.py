from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from .bundler import Bundler


class PageGenerator:
    def __init__(self, bundler: Bundler, request: Request, file: str):
        self._bundler = bundler
        self._request = request
        self._file = file
        self.title = file.split("/")[-1].split(".")[0]

    async def __call__(self):
        return await self._bundler.spa_response(self._request, self._file, self.title)
