import mimetypes
import pathlib
import uuid
from collections.abc import Callable

from .config import Config
from .metafile import Metafile


def generate_public_path_placeholder():
    return f"/__fastapi-esbuild-{uuid.uuid4().hex}/"


def asset_loader_for_url_mode(url_for_available: bool) -> str:
    return "file" if url_for_available else "dataurl"


def loader_map(config: Config, asset_loader: str) -> dict[str, str]:
    return {
        ".png": asset_loader,
        ".jpg": asset_loader,
        ".jpeg": asset_loader,
        ".svg": asset_loader,
        ".gif": asset_loader,
        ".webp": asset_loader,
        ".mp3": asset_loader,
        ".module.css": "local-css",
        **config.loader_overwrites,
    }


def create_build_args(
    *,
    frontend_dir: pathlib.Path,
    build_files: list[str],
    dist_dir: pathlib.Path,
    metafile_path: pathlib.Path,
    tsconfig_path: pathlib.Path,
    public_path: str,
    config: Config,
    asset_loader: str,
) -> list[str]:
    return (
        [str(frontend_dir / file) for file in build_files]
        + [
            "--bundle",
            f"--outdir={dist_dir}",
            *(["--minify"] if config.minify else []),
            *(["--sourcemap"] if config.sourcemap else []),
            "--entry-names=[name]-[hash]",
            f"--metafile={metafile_path}",
            "--format=esm",
            f"--tsconfig={tsconfig_path}",
            f"--public-path={public_path}",
        ]
        + [f"--target={','.join(config.target)}"]
        + [
            f"--loader:{ext}={loader_type}"
            for ext, loader_type in loader_map(config, asset_loader).items()
        ]
    )


def output_files_from_meta(
    meta: Metafile,
    dist_dir: pathlib.Path,
    normalize_dist_path: Callable[[str], str],
) -> dict[str, tuple[bytes, str, list[str]]]:
    out_files: dict[str, tuple[bytes, str, list[str]]] = {}

    for out_path, data in meta.outputs.items():
        normalized_path = normalize_dist_path(out_path)
        media_type, _ = mimetypes.guess_type(normalized_path)

        out_files[normalized_path] = (
            (dist_dir / normalized_path).read_bytes(),
            media_type or "application/octet-stream",
            [normalize_dist_path(data.cssBundle)] if data.cssBundle is not None else [],
        )

    return out_files
