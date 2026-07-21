import pathlib
from typing import Any, Callable

from fastapi import Request
from fastapi.templating import Jinja2Templates
from jinja2 import BaseLoader, ChoiceLoader, Environment, FileSystemLoader, PrefixLoader

from .jinja2_ContextChanger_extention import ContextChanger

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"


def create_templates(
    user_templates: pathlib.Path | BaseLoader | None,
) -> Jinja2Templates:
    return Jinja2Templates(
        env=Environment(
            extensions=[ContextChanger],
            loader=ChoiceLoader(
                [
                    *(
                        [
                            PrefixLoader(
                                {
                                    "user_templates": (
                                        FileSystemLoader(user_templates)
                                        if isinstance(user_templates, pathlib.Path)
                                        else user_templates
                                    )
                                }
                            )
                        ]
                        if user_templates is not None
                        else []
                    ),
                    FileSystemLoader(TEMPLATES_DIR),
                ]
            ),
        )
    )


def normalize_template_context(
    user_template_ctx: dict[str, Any] | Callable[[Request], dict[str, Any]] | None,
) -> Callable[[Request], dict[str, Any]]:
    if callable(user_template_ctx):
        return user_template_ctx

    return lambda _: user_template_ctx if user_template_ctx is not None else {}
