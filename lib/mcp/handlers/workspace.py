"""
Handlers de workspace: stack, diagnóstico, inicialización y Daily Board.
"""

import os
import sys

from ..runtime import enter, invoke


def h_stack(args):
    with enter(args) as root:
        from lib.core.runner import find_agent_runner, find_opencode_runner
        from lib.core.stack_detector import detect_workspace_stack
        from lib.spec.mock_engine import find_openapi_spec, find_prism_runner
        from lib.spec.tester import find_hurl_runner

        spec = find_openapi_spec()
        return {
            "workspace": str(root),
            "stack": detect_workspace_stack(),
            "spec": str(spec) if spec else None,
            "toolchain": {
                "hurl": find_hurl_runner(),
                "prism": find_prism_runner(),
                "opencode": find_opencode_runner(),
                "agent_runner": find_agent_runner(),
            },
        }


def _mask(value):
    if not value:
        return None
    return f"{value[:4]}…{value[-4:]}" if len(value) > 8 else "…"


def h_doctor(args):
    with enter(args):
        import shutil

        from lib.core.runner import find_agent_runner, find_opencode_runner
        from lib.spec.mock_engine import find_prism_runner
        from lib.spec.tester import find_hurl_runner

        keys = {
            "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
            "SLACK_WEBHOOK_URL": os.environ.get("SLACK_WEBHOOK_URL"),
            "SLACK_BOT_TOKEN": os.environ.get("SLACK_BOT_TOKEN"),
            "SLACK_USER_TOKEN": os.environ.get("SLACK_USER_TOKEN"),
        }

        return {
            "tools": {
                "hurl": find_hurl_runner(),
                "prism": find_prism_runner(),
                "gh": shutil.which("gh"),
                "opencode": find_opencode_runner(),
                "agent_runner": find_agent_runner(),
                "python": sys.executable,
            },
            "api_keys": {name: _mask(value) for name, value in keys.items()},
            "configured": sorted(name for name, value in keys.items() if value),
        }


def h_init(args):
    with enter(args):
        from lib.core.init_project import cmd_init

        result = invoke(cmd_init)
        return {"ok": result["ok"], "error": result.get("error"), "log": result["log"]}


def h_board_init(args):
    with enter(args):
        from lib.core.board import board_init

        return board_init(force=bool(args.get("force")))


def h_board_url(args):
    with enter(args):
        from lib.core.board import board_url, repo_slug

        slug = repo_slug()
        return {"slug": slug, "url": board_url(slug)}
