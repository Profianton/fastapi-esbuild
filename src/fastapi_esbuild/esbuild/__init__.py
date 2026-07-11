import asyncio
import os
import pathlib
import shlex
from typing import Union

from platformdirs import user_cache_dir

from .installation import install


class EsBuildLauncher:
    def __init__(
        self,
        auto_install: bool = False,
        bin_path: str | pathlib.Path | None = None,
        cwd: str | pathlib.Path | None = None,
        version: str = "0.12.28",
    ):
        self.auto_install = auto_install
        self.cwd = cwd
        if isinstance(bin_path, str):
            bin_path = pathlib.Path(bin_path)
        self.version = version
        self.bin_path = bin_path or get_bin_path_root() / f"esbuild-{self.version}"

    async def run(
        self,
        cli_args: Union[list[str], str],
        cwd: pathlib.Path | None = None,
        env: dict | None = None,
        live_output=False,
    ):
        if self.auto_install and not self.bin_path.exists():
            self.install(self.version)

        if isinstance(cli_args, str):
            cli_args = shlex.split(cli_args)

        cwd_val = cwd or self.cwd or os.getcwd()
        env_val = env if env is not None else None

        if not live_output:
            proc = await asyncio.create_subprocess_exec(
                str(self.bin_path),
                *cli_args,
                cwd=cwd_val,
                env=env_val,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Command failed with exit code {proc.returncode}: "
                    f"{stderr.decode().strip()}"
                )

            return stdout.decode().strip()

        else:
            proc = await asyncio.create_subprocess_exec(
                str(self.bin_path),
                *cli_args,
                cwd=cwd_val,
                env=env_val,
            )

            await proc.wait()
            return proc

    def install(self, version="0.12.28"):  # todo: make async
        return install(version, self.bin_path)


def get_bin_path_root():
    return pathlib.Path(
        user_cache_dir("fastapi_esbuild_versions", "fastapi_esbuild", ensure_exists=True)
    )
