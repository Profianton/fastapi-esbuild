from typing import Any

from pydantic import BaseModel

from .config import Config
from .metafile import Metafile


class CacheData(BaseModel):
    config: Config
    deps: dict[str, str]
    files: dict[str, str]
    build_files: list[str]
    url_for: bool


class BuildResult(BaseModel):
    meta: Metafile
    out_path_map: dict[str, str]
    out_files: dict[str, tuple[bytes, str, list[str]]]
    public_path: str


class TemplateAsset(BaseModel):
    template: str
    context: dict[str, Any]
