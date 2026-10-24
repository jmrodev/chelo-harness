"""
GitHub: contexto de sprint vía `gh` (milestone activo e issues abiertos).

Habla con el CLI, no con la API HTTP: si el equipo cambia de `gh` a otra cosa,
este archivo cambia solo.
"""

import json
import subprocess


def get_github_sprint_context():
    """Consulta Milestones e Issues vía gh CLI para alimentar la Daily."""
    try:
        # 1. Milestone activo
        res_m = subprocess.run(["gh", "api", "repos/:owner/:repo/milestones?state=open"], capture_output=True, text=True)
        milestones = json.loads(res_m.stdout) if res_m.returncode == 0 else []
        active_milestone = milestones[0] if milestones else None

        # 2. Issues pendientes
        res_i = subprocess.run(["gh", "issue", "list", "--state", "open", "--json", "number,title,labels,milestone"], capture_output=True, text=True)
        issues = json.loads(res_i.stdout) if res_i.returncode == 0 else []

        return {
            "ok": True,
            "milestone": active_milestone,
            "issues": issues
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
