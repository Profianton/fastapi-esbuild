import base64
import hashlib
import pathlib
import uuid
from collections.abc import Callable

from .config import Config
from .metafile import Metafile
from .models import CacheData


def compute_cache_key(
    *,
    metafile_path: pathlib.Path,
    frontend_path_to_abspath: Callable[[str], pathlib.Path],
    config: Config,
    deps: dict[str, str],
    build_files: list[str],
    url_for_available: bool,
) -> str:
    if not metafile_path.exists():
        return uuid.uuid4().hex
    meta = Metafile.model_validate_json(metafile_path.read_text())
    files: dict[str, str] = {
        str(file): base64.b64encode(file.read_bytes()).decode()
        if file.exists()
        else uuid.uuid4().hex
        for file in [frontend_path_to_abspath(file) for file in meta.inputs.keys()]
    }
    return hashlib.blake2b(
        CacheData(
            config=config,
            deps=deps,
            files=files,
            build_files=build_files,
            url_for=url_for_available,
        )
        .model_dump_json()
        .encode()
    ).hexdigest()
