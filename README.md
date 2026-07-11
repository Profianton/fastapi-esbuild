# fastapi-esbuild

FastAPI helper for bundling frontend assets with esbuild.

This package is currently extracted from the FastAPI template and is intended
to be consumed as a local reusable package while the API settles.

## Usage

```python
from fastapi_esbuild import Bundler, Config
```

Create a `Bundler`, register `bundler.get_file` on an asset route, add entry
files with `bundler.add_build_file(...)`, and call `bundler.spa_response(...)`
from your FastAPI views.
