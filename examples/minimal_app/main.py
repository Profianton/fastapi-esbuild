from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Callable

from fastapi import Depends, FastAPI

from fastapi_esbuild import Bundler, Config
from fastapi_esbuild.bundler import PageGenerator


FRONTEND_DIR = Path(__file__).parent / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await bundler.startup()
    yield
    bundler.shutdown()


app = FastAPI(lifespan=lifespan)


def url_for(_: Callable, path: str) -> str:
    return f"/assets/{path}"


bundler = Bundler(
    config=Config(minify=False, sourcemap=True),
    frontend_dir=FRONTEND_DIR,
    url_for=url_for,
)


app.get("/assets/{path:path}")(bundler.get_file)


@app.get("/")
async def index(page: Annotated[PageGenerator, Depends(bundler.page("index.tsx"))]):
    page.title = "Home"
    return await page()
