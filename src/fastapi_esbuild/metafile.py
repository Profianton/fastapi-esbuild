from typing import Optional

from pydantic import BaseModel, Field


class Metafile(BaseModel):
    class InputFile(BaseModel):
        class ImportItem(BaseModel):
            path: str
            kind: str
            external: Optional[bool] = None
            original: Optional[str] = None
            with_: Optional[dict[str, str]] = Field(default=None, alias="with")

        bytes: int
        imports: list[ImportItem]
        format: Optional[str] = None
        with_: Optional[dict[str, str]] = Field(default=None, alias="with")

    inputs: dict[str, InputFile]

    class OutputFile(BaseModel):
        bytes: int

        class OutputInput(BaseModel):
            bytesInOutput: int

        inputs: dict[str, OutputInput]

        class OutputImport(BaseModel):
            path: str
            kind: str
            external: Optional[bool] = None

        imports: list[OutputImport]
        exports: list[str] = Field(default_factory=list)
        entryPoint: Optional[str] = None
        cssBundle: Optional[str] = None

    outputs: dict[str, OutputFile]
