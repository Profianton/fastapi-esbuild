import pathlib

from platformdirs import user_cache_dir

cache_dir = pathlib.Path(
    user_cache_dir("fastapi_esbuild", "fastapi_esbuild", ensure_exists=True)
)

__all__ = ["cache_dir"]
