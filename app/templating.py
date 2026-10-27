from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config

env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
                  autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
env.globals.update(APP_URL=config.app_url())

# Bump on every CSS/JS change — the service worker caches /static/ by this version.
ASSET_VERSION = "4"


def render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200,
           headers: dict | None = None) -> HTMLResponse:
    ctx = dict(ctx or {})
    ctx.setdefault("request", request)
    ctx.setdefault("current_user", getattr(request.state, "user", None))
    ctx.setdefault("v", ASSET_VERSION)
    ctx.setdefault("APP_NAME", config.APP_NAME)
    return HTMLResponse(env.get_template(name).render(**ctx), status_code=status_code, headers=headers)
