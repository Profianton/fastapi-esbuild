from typing import Annotated

from annotated_doc import Doc
from pydantic import BaseModel, Field


class Config(BaseModel):
    minify: bool = True
    sourcemap: bool = False
    build_on_startup: bool = False
    loader_overwrites: dict[str, str] = Field(default_factory=dict)
    asset_template_overrides: dict[
        str | Annotated[None, Doc("the default/fallback template")], str
    ] = Field(default_factory=dict)
    target: list[str] = Field(
        default_factory=lambda: [
            "chrome111",
            "firefox114",
            "safari16.4",
            "edge111",
        ]
    )
    cache: bool = False
