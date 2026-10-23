"""
Handlers de agentes: turno individual y pipeline Spec-First completo.
"""

from pathlib import Path

from lib.core.paths import resolve_within

from ..runtime import agents_dir, enter, invoke


def available_roles():
    directory = agents_dir()
    return sorted(path.stem for path in directory.glob("*.md")) if directory else []


def h_agent_turn(args):
    with enter(args):
        from lib.core.orchestrator import run_agent_turn, strip_markdown_blocks
        from lib.core.runner import get_agent_prompt

        role = (args.get("role") or "").strip()
        instruction = (args.get("instruction") or "").strip()
        if not role or not instruction:
            return {"ok": False, "error": "Se requieren 'role' e 'instruction'."}

        if not get_agent_prompt(role):
            return {"ok": False, "error": f"Rol desconocido: {role}", "available_roles": available_roles()}

        use_tools = bool(args.get("use_tools"))
        response = run_agent_turn(
            role,
            instruction,
            context=args.get("context") or "",
            trace=False,
            use_tools=use_tools,
            max_steps=int(args.get("max_steps") or 5),
        )
        if not response.get("ok"):
            return {"ok": False, "error": response.get("error"), "model_used": response.get("model_used")}

        content = strip_markdown_blocks(response.get("text", ""))
        written = None
        if args.get("out_path"):
            target = resolve_within(args["out_path"], Path.cwd())
            if target is None:
                return {"ok": False, "error": f"out_path fuera del workspace: {args['out_path']}"}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written = str(target)

        return {
            "ok": True,
            "role": role,
            "model_used": response.get("model_used"),
            "used_tools": use_tools,
            "written_to": written,
            "content": content,
        }


def h_pipeline(args):
    with enter(args):
        from lib.core.orchestrator import run_pipeline

        requirement = (args.get("requirement") or "").strip()
        if not requirement:
            return {"ok": False, "error": "Falta 'requirement'."}

        project = args.get("project") or Path.cwd().name
        result = invoke(run_pipeline, project, requirement, bool(args.get("trace")))
        log = result["log"]
        return {
            "ok": result["ok"],
            "error": result.get("error"),
            "completed": "Pipeline Spec-First completado" in log,
            "log": log,
        }
