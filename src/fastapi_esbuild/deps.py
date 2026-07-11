from functools import cache
import json
import shutil
from typing import Annotated

import httpx
import tarfile
import io

from .cache_dir import cache_dir

deps_dir = cache_dir / "npm_deps"

OUT_DIR = deps_dir / "libs"
META_DIR = deps_dir / "meta"


def pkg_folder(package: str, version: str):
    return OUT_DIR / package / version / package


def handle_version(package: str, version: str) -> str:
    import semantic_version

    if version in pkg_meta(package)["dist-tags"].keys():
        version = pkg_meta(package)["dist-tags"][version]

    allowed_versions = []
    for v in map(semantic_version.Version, pkg_meta(package)["versions"].keys()):
        if v in semantic_version.Spec(version):
            allowed_versions.append(v)
    if len(allowed_versions) == 0:
        raise ValueError(f"No version satisfies {version}")

    return str(sorted(allowed_versions)[-1])


@cache
def pkg_meta(package: str) -> dict:
    file = META_DIR / f"{package}.json"
    file.parent.mkdir(exist_ok=True, parents=True)
    if file.exists():
        return json.loads(file.read_text())
    meta_url = f"https://registry.npmjs.org/{package}"
    meta = httpx.get(meta_url).json()
    file.write_text(json.dumps(meta, indent=4))
    return meta


def download(deps: dict[Annotated[str, "package"], Annotated[str, "version"]]):
    subdeps: dict[str, str] = {}
    deps_todo = list(deps.items())
    while len(deps_todo) > 0:
        package, version = deps_todo.pop()
        version = handle_version(package, version)
        assert package not in subdeps or version == subdeps[package], (
            "invalid dependency graph"
        )

        subdeps[package] = version
        for dep_name, dep_version in (
            pkg_meta(package)["versions"][version].get("dependencies", {}).items()
        ):
            deps_todo.append((dep_name, dep_version))

    for package, version in subdeps.items():
        download_single(package, version)

    return {
        package: pkg_folder(package, version) for package, version in subdeps.items()
    }


def download_single(package: str, version: str):
    download_complete_path = pkg_folder(package, version) / "download_complete"
    if (download_complete_path).exists():
        return
    meta = pkg_meta(package)
    pkg = meta["versions"][version]
    tarball_url = pkg["dist"]["tarball"]
    tgz_data = httpx.get(tarball_url).content
    pkgfolder = pkg_folder(package, version).resolve()
    pkgfolder.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tgz_data), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = member.name.removeprefix("package/")
            target = (pkgfolder / name).resolve()

            if not target.is_relative_to(pkgfolder):
                raise ValueError(
                    f"package {package}@{version} has a file outside of its folder"
                )

            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(member)
                if src is None:
                    raise ValueError(f"could not extract {member.name!r}")

                with src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            else:
                raise ValueError(
                    f"package {package}@{version} contains unsupported tar member "
                    f"{member.name!r} of type {member.type!r}"
                )
    download_complete_path.touch()
