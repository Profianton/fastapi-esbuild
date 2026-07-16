import base64
import hashlib
import json
import mimetypes
import pathlib
import subprocess
import uuid

from fastapi.templating import Jinja2Templates
from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PrefixLoader,
)

from .jinja2_ContextChanger_extention import ContextChanger

from .metafile import Metafile
from .cache_dir import cache_dir
from .deps import download as download_deps

from . import esbuild
from fastapi import HTTPException, Request, Response

from typing import Any, Callable
from pydantic import BaseModel, Field

from functools import cache
from async_lru import alru_cache

import tempfile
import shutil


class Config(BaseModel):
    minify: bool = True
    sourcemap: bool = False
    build_on_startup: bool = False
    loader_overwrites: dict[str, str] = Field(default_factory=dict)
    target: list[str] = Field(
        default_factory=lambda: [
            "chrome111",
            "firefox114",
            "safari16.4",
            "edge111",
        ]
    )
    cache: bool = False


TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"


class CacheData(BaseModel):
    config: Config
    deps: dict[str, str]
    files: dict[str, str]
    build_files: list[str]
    url_for: bool


class PageGenerator:
    def __init__(self, bundler: Bundler, request: Request, file: str):
        self._bundler = bundler
        self._request = request
        self._file = file
        self.title = file.split("/")[-1].split(".")[0]

    async def __call__(self):
        return await self._bundler.spa_response(self._request, self._file, self.title)


def generate_public_path_placeholder():
    return f"/__fastapi-esbuild-{uuid.uuid4().hex}/"


class BuildResult(BaseModel):
    meta: Metafile
    out_path_map: dict[str, str]
    out_files: dict[str, tuple[bytes, str, list[str]]]
    public_path: str


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
        self.user_template_ctx = (
            user_template_ctx
            if callable(user_template_ctx)
            else (lambda _: user_template_ctx if user_template_ctx is not None else {})
        )
        self.templates = Jinja2Templates(
            env=Environment(
                extensions=[ContextChanger],
                loader=ChoiceLoader(
                    [
                        *(
                            [
                                PrefixLoader(
                                    {
                                        "user_templates": (
                                            FileSystemLoader(user_templates)
                                            if isinstance(user_templates, pathlib.Path)
                                            else user_templates
                                        )
                                    }
                                )
                            ]
                            if user_templates is not None
                            else []
                        ),
                        FileSystemLoader(TEMPLATES_DIR),
                    ]
                ),
            )
        )

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
        self.tsconfig_path = pathlib.Path(tempfile.mkstemp(".json")[1])
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
        if not self.metafile_path.exists():
            return uuid.uuid4().hex
        meta = Metafile.model_validate_json(self.metafile_path.read_text())
        files: dict[str, str] = {
            str(file): base64.b64encode(file.read_bytes()).decode()
            if file.exists()
            else uuid.uuid4().hex
            for file in [
                self.frontend_path_to_abspath(file) for file in meta.inputs.keys()
            ]
        }
        return hashlib.blake2b(
            CacheData(
                config=self.config,
                deps=self.deps(),
                files=files,
                build_files=self.build_files,
                url_for=self.url_for is not None,
            )
            .model_dump_json()
            .encode()
        ).hexdigest()

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
            asset_loader = "dataurl" if self.url_for is None else "file"
            public_path = generate_public_path_placeholder()
            build_args = (
                [str(self.frontend_dir / file) for file in self.build_files]
                + [
                    "--bundle",
                    f"--outdir={self.dist_dir}",
                    *(["--minify"] if self.config.minify else []),
                    *(["--sourcemap"] if self.config.sourcemap else []),
                    "--entry-names=[name]-[hash]",
                    f"--metafile={self.metafile_path}",
                    "--format=esm",
                    f"--tsconfig={self.tsconfig_path}",
                    f"--public-path={public_path}",
                ]
                + [f"--target={','.join(self.config.target)}"]
                + [
                    f"--loader:{ext}={loader_type}"
                    for ext, loader_type in {
                        ".png": asset_loader,
                        ".jpg": asset_loader,
                        ".jpeg": asset_loader,
                        ".svg": asset_loader,
                        ".gif": asset_loader,
                        ".webp": asset_loader,
                        ".mp3": asset_loader,
                        ".module.css": "local-css",
                        **self.config.loader_overwrites,
                    }.items()
                ]
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

        out_files: dict[str, tuple[bytes, str, list[str]]] = {}

        for out_path, d in meta.outputs.items():
            normalized_path = self.normalize_dist_path(out_path)

            media_type, _ = mimetypes.guess_type(normalized_path)

            out_files[normalized_path] = (
                (self.dist_dir / normalized_path).read_bytes(),
                media_type or "application/octet-stream",
                [self.normalize_dist_path(d.cssBundle)]
                if d.cssBundle is not None
                else [],
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

    async def build_header(self, path: str):
        out_path_map = (await self.build()).out_path_map
        out_files = (await self.build()).out_files
        files: set[str] = set()
        files_todo: set[str] = {out_path_map[path]}
        while len(files_todo) > 0:
            file = files_todo.pop()
            files.add(file)
            for dep in out_files[file][2]:
                files_todo.add(dep)
        return [
            (await self.url_from_built_file(file), out_files[file][1]) for file in files
        ]

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
