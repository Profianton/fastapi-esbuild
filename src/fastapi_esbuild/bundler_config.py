from pydantic import BaseModel, Field


class Config(BaseModel):
    minify: bool = True
    sourcemap: bool = False
    build_on_startup: bool = False
    loaders: dict[str, str] = Field(
        default_factory=lambda: {
            ".png": "dataurl",
            ".jpg": "dataurl",
            ".jpeg": "dataurl",
            ".svg": "dataurl",
            ".gif": "dataurl",
            ".webp": "dataurl",
            ".mp3": "dataurl",
            ".module.css": "local-css",
        }
    )
    target: list[str] = Field(
        default_factory=lambda: [
            "chrome111",
            "firefox114",
            "safari16.4",
            "edge111",
        ]
    )
    cache: bool = False


class CacheData(BaseModel):
    config: Config
    deps: dict[str, str]
    files: dict[str, str]
    build_files: list[str]
