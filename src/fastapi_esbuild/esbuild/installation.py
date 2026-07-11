import hashlib
import base64
import os
import pathlib
import platform
import shutil
from tempfile import mkdtemp
from packaging.version import Version

import httpx


NPM_REGISTRY = "https://registry.npmjs.org"


def install(version: str, bin_path: pathlib.Path):
    if bin_path.exists():
        bin_path.unlink()

    bin_path.parent.mkdir(parents=True, exist_ok=True)

    package_name = get_package_name(version)

    metadata = get_package_metadata(package_name)
    tarball_url, integrity, shasum = get_tarball_info(metadata, version)

    downloaded_tar = download_file(tarball_url)

    # SECURITY: verify before extraction
    verify_file_integrity(downloaded_tar, integrity, shasum)

    extract_dir = downloaded_tar.parent / "esbuild"
    extract_file(downloaded_tar, extract_dir)

    executable = extract_dir / "package" / "bin" / "esbuild"

    if platform.system().lower() == "windows":
        executable = extract_dir / "package" / "esbuild.exe"

    shutil.copy2(executable, bin_path)
    os.chmod(bin_path, 0o755)


def get_package_name(version: str) -> str:
    metadata = get_package_metadata("esbuild")

    try:
        version_info = metadata["versions"][version]
    except KeyError:
        raise ValueError(f"esbuild@{version} does not exist")

    optional = version_info.get("optionalDependencies", {})
    suffix = get_platform_suffix()

    # Modern esbuild (0.16+)
    for name in optional:
        if name.endswith(suffix):
            return name

    # Legacy esbuild (<0.16)
    if Version(version) < Version("0.16.0"):
        legacy_arch = suffix.replace("x64", "64").replace("ia32", "32")
        return f"esbuild-{legacy_arch}"

    raise RuntimeError(f"No esbuild binary package for {suffix} ({version})")


def get_tarball_info(metadata: dict, version: str):
    try:
        dist = metadata["versions"][version]["dist"]
        return (
            dist["tarball"],
            dist.get("integrity"),
            dist.get("shasum"),
        )
    except KeyError:
        raise RuntimeError(f"esbuild@{version} does not exist")


def get_package_metadata(package_name: str) -> dict:
    url = f"{NPM_REGISTRY}/{package_name}"

    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        http2=True,
    ) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()


def get_platform_suffix() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    os_map = {
        "linux": "linux",
        "darwin": "darwin",
        "windows": "win32",
    }

    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
        "armv7l": "arm",
        "i386": "ia32",
        "i686": "ia32",
    }

    if system not in os_map:
        raise RuntimeError(f"Unsupported OS: {system}")
    if machine not in arch_map:
        raise RuntimeError(f"Unsupported architecture: {machine}")

    return f"{os_map[system]}-{arch_map[machine]}"


def download_file(url: str) -> pathlib.Path:
    working_dir = pathlib.Path(mkdtemp())

    filename = url.rsplit("/", 1)[-1]
    destination = working_dir / filename

    with httpx.stream(
        "GET",
        url,
        timeout=60,
        follow_redirects=True,
    ) as r:
        r.raise_for_status()

        with destination.open("wb") as f:
            for chunk in r.iter_bytes():
                if chunk:
                    f.write(chunk)

    return destination


def verify_file_integrity(
    path: pathlib.Path, integrity: str | None, shasum: str | None
):
    data = path.read_bytes()

    # npm integrity (sha512-...)
    if integrity:
        algo, b64_digest = integrity.split("-", 1)

        if algo != "sha512":
            raise RuntimeError(f"Unsupported integrity algorithm: {algo}")

        expected = base64.b64decode(b64_digest)
        actual_sha512 = hashlib.sha512(data).digest()

        if actual_sha512 != expected:
            raise RuntimeError("Integrity check failed (sha512 mismatch)")

        return

    # fallback legacy sha1
    if shasum:
        actual_sha1 = hashlib.sha1(data).hexdigest()
        if actual_sha1 != shasum:
            raise RuntimeError("Integrity check failed (sha1 mismatch)")
        return

    raise RuntimeError("No integrity metadata available")


def extract_file(filename: pathlib.Path, extract_dir: pathlib.Path):
    shutil.unpack_archive(str(filename), str(extract_dir))


if __name__ == "__main__":
    install("0.10.0", pathlib.Path("/tmp/esbuild"))
