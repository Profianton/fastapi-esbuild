from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import subprocess

from jinja2 import BaseLoader

from .build import (
    asset_loader_for_url_mode,
    create_build_args,
    generate_public_path_placeholder,
    output_files_from_meta,
)
from .cache import compute_cache_key as calculate_cache_key
from .cache_dir import cache_dir
from .config import Config
from .deps import download as download_deps
from .models import BuildResult, CacheData, TemplateAsset
from .page import PageGenerator
from .templates import create_templates, normalize_template_context

from .metafile import Metafile

from . import esbuild
from fastapi import HTTPException, Request, Response

from typing import Any, Callable

from functools import cache
from async_lru import alru_cache

import tempfile
import shutil


__all__ = [
    "Bundler",
    "Config",
    "PageGenerator",
    "BuildResult",
    "CacheData",
    "TemplateAsset",
]


class Bundler:
    def __init__(
        self,
        config: Config,
        frontend_dir: pathlib.Path,
        user_templates: pathlib.Path | BaseLoader | None = None,
        user_template_ctx: dict[str, Any]
        | Callable[[Request], dict[str, Any]]
        | None = None,
        deps: dict[str, str] | None = None,
        dist_dir: pathlib.Path | None = None,
        esbuild_version: str = "0.28.1",
        url_for: Callable[..., str] | None = None,
    ):
        self.user_template_ctx = normalize_template_context(user_template_ctx)
        self.templates = create_templates(user_templates)

        @cache
        def _deps():
            if deps is not None:
                return deps
            package_json_path = frontend_dir / "package.json"
            if not package_json_path.exists():
                return {}
            package_json_content = json.loads(package_json_path.read_text())
            assert isinstance(package_json_content, dict)
            return package_json_content.get("dependencies", {})

        self.deps = _deps
        self.frontend_dir = frontend_dir
        self.esbuild_version = esbuild_version
        self.url_for = url_for
        self.config = config
        self.dist_dir = (
            (
                pathlib.Path(tempfile.mkdtemp())
                if not self.config.cache
                else cache_dir
                / "by-folder-hashed"
                / hashlib.blake2b(str(frontend_dir).encode()).hexdigest()
            )
            if dist_dir is None
            else dist_dir
        )
        fd, tsconfig_path = tempfile.mkstemp(".json")
        os.close(fd)
        self.tsconfig_path = pathlib.Path(tsconfig_path)
        self.build_files: list[str] = []
        self.build = alru_cache(maxsize=None)(self.__build_nocache)

    @property
    def metafile_path(self):
        return self.dist_dir / "meta.json"

    def frontend_path_to_abspath(self, path: str):
        return (self.frontend_dir / path).resolve()

    def normalize_dist_path(self, path: str):
        return str(self.frontend_path_to_abspath(path).relative_to(self.dist_dir))

    def gen_out_path_map(self, meta: Metafile):
        out_path_map: dict[str, str] = {}
        for out_path, data in meta.outputs.items():
            if data.entryPoint is not None:
                out_path_map[data.entryPoint] = self.normalize_dist_path(out_path)
        return out_path_map

    @property
    def launcher(self):
        return esbuild.EsBuildLauncher(
            auto_install=True, cwd=self.frontend_dir, version=self.esbuild_version
        )

    @property
    def cache_key_file(self):
        return self.dist_dir / "cache_key.txt"

    @property
    def public_path_file(self):
        return self.dist_dir / "public_path.txt"

    @property
    async def public_path(self):
        return (await self.build()).public_path

    def compute_cache_key(self):
        return calculate_cache_key(
            metafile_path=self.metafile_path,
            frontend_path_to_abspath=self.frontend_path_to_abspath,
            config=self.config,
            deps=self.deps(),
            build_files=self.build_files,
            url_for_available=self.url_for is not None,
        )

    async def __build_nocache(
        self,
    ) -> BuildResult:
        """use the cached function (build)"""
        self.dist_dir.mkdir(parents=True, exist_ok=True)
        self.cached = False
        if self.config.cache:
            if self.cache_key_file.exists():
                if self.compute_cache_key() == self.cache_key_file.read_text():
                    self.cached = True
        if not self.cached:
            shutil.rmtree(self.dist_dir)
            self.dist_dir.mkdir(parents=True, exist_ok=True)
            self.tsconfig_path.write_text(
                json.dumps(
                    {
                        "compilerOptions": {
                            "paths": {
                                **{
                                    name: [str(path)]
                                    for name, path in download_deps(self.deps()).items()
                                },
                                **{
                                    f"{name}/*": [str(path / "*")]
                                    for name, path in download_deps(self.deps()).items()
                                },
                            }
                        },
                    }
                )
            )
            asset_loader = asset_loader_for_url_mode(self.url_for is not None)
            public_path = generate_public_path_placeholder()
            build_args = create_build_args(
                frontend_dir=self.frontend_dir,
                build_files=self.build_files,
                dist_dir=self.dist_dir,
                metafile_path=self.metafile_path,
                tsconfig_path=self.tsconfig_path,
                public_path=public_path,
                config=self.config,
                asset_loader=asset_loader,
            )
            try:
                await self.launcher.run(build_args)
            except subprocess.CalledProcessError:
                print(
                    f"to reproduce the error, run:\n"
                    f"{' '.join([str(arg) for arg in [self.launcher.bin_path, *build_args]])}"
                )
                raise
            self.public_path_file.write_text(public_path)
        else:
            public_path = self.public_path_file.read_text()

        meta = Metafile.model_validate_json(self.metafile_path.read_text())

        out_files = output_files_from_meta(
            meta, self.dist_dir, self.normalize_dist_path
        )
        if not self.cached:
            self.cache_key_file.write_text(self.compute_cache_key())

        return BuildResult(
            meta=meta,
            out_path_map=self.gen_out_path_map(meta),
            out_files=out_files,
            public_path=public_path,
        )

    async def url_from_built_file(self, file: str):
        if self.url_for is None:
            # Generate data url
            out_files = (await self.build()).out_files
            if file not in out_files:
                raise ValueError(f"file {file} not found")
            content, media_type, _ = out_files[file]
            return f"data:{media_type};base64,{base64.b64encode(content).decode()}"

        return self.url_for(self.get_file, path=file)

    async def path_for_js(self, file: str):
        return await self.url_from_built_file((await self.build()).out_path_map[file])

    async def get_file(self, path: str):
        out_files = (await self.build()).out_files
        if path not in out_files:
            raise HTTPException(status_code=404)

        content, media_type, _ = out_files[path]
        if self.url_for is not None:
            content = content.replace(
                (await self.public_path).encode(),
                self.url_for(self.get_file, path="").encode(),
            )

        return Response(
            content,
            media_type=media_type,
            headers={"cache-control": "max-age=31536000"},
        )

    async def build_header(self, path: str) -> list[TemplateAsset]:
        out_path_map = (await self.build()).out_path_map
        out_files = (await self.build()).out_files
        files: set[str] = set()
        files_todo: set[str] = {out_path_map[path]}
        while len(files_todo) > 0:
            file = files_todo.pop()
            files.add(file)
            for dep in out_files[file][2]:
                files_todo.add(dep)
        asset_handlers: dict[str | None, str] = {
            "text/css": "assets/css.html",
            None: "assets/module.html",
        }
        asset_handlers.update(self.config.asset_template_overrides)

        assets = [
            TemplateAsset(
                template=asset_handlers.get(out_files[file][1], asset_handlers[None]),
                context={
                    "url": await self.url_from_built_file(file),
                    "bundler": self,
                    "mime": out_files[file][1],
                },
            )
            for file in files
        ]

        return assets

    def add_build_file(self, file: str):
        self.build_files.append(file)
        self.build.cache_clear()

    async def spa_response(self, request: Request, file: str, title: str):
        files = await self.build_header(file)

        return self.templates.TemplateResponse(
            request,
            "built.html",
            {
                "files": files,
                "title": title,
                "ctx": self.user_template_ctx(request),
            },
        )

    def page(self, file: str) -> Callable[..., PageGenerator]:
        """This is the di style system to return a page

        ## Example
        ```python
        @app.get("/")
        async def index(page: Annotated[PageGenerator, Depends(bundler.page("index.tsx"))]):
            page.title = "Startseite"
            return await page()

        ```
        """

        self.add_build_file(file)

        def _page(request: Request):
            return PageGenerator(self, request, file)

        return _page

    def reload(self):
        self.build.cache_clear()
        self.deps.cache_clear()

    async def startup(self):
        if self.config.build_on_startup:
            await self.build()

    def shutdown(self):
        if not self.config.cache:
            shutil.rmtree(self.dist_dir)
        self.tsconfig_path.unlink(True)
