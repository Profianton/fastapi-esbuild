# fastapi-esbuild

FastAPI helper for bundling frontend assets with esbuild.

## Basic usage

```python
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi_esbuild import Bundler, Config
from fastapi_esbuild.bundler import PageGenerator

app = FastAPI()

bundler = Bundler(
    config=Config(),
    frontend_dir=Path('frontend'),
)

app.get('/assets/{path:path}')(bundler.get_file)

@app.get('/')
async def index(
    page: Annotated[PageGenerator, Depends(bundler.page('index.tsx'))],
):
    page.title = 'Home'
    return await page()
```

## Example app

See `examples/minimal_app` for a complete working example.
Run it with:

```bash
uvicorn examples.minimal_app.main:app --reload --reload-include '*.tsx'
```
