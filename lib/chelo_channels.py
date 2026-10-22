"""
chelo_channels.py — Módulo desacoplado para consulta y sincronización de Canales (Slack, Gmail, GitHub).
Estilo Daily Scrum aceitada: retorna datos estructurados y maneja fallbacks gracefully.
"""

import os
import sys
import json
import urllib.request
from pathlib import Path

def get_secret(key, default=None):
    """Obtiene credenciales desde variables de entorno, .env local, o secrets centrales."""
    # 1. Variables de entorno activas
    if os.environ.get(key):
        return os.environ.get(key)

    # 2. Archivo .env en el directorio actual o padres
    curr = Path.cwd()
    for parent in [curr] + list(curr.parents)[:3]:
        env_file = parent / ".env"
        if env_file.exists():
            try:
                with open(env_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == key:
                                return v.strip().strip('"').strip("'")
            except Exception:
                pass

    # 3. Fallback a la ubicación de InstituteProjects2026
    inst_env = Path.home() / "Documents/Academy/TECDA/TERCERO/Practicas_profesionalizantes/InstituteProjects2026/.env"
    if inst_env.exists():
        try:
            with open(inst_env, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == key:
                            return v.strip().strip('"').strip("'")
        except Exception:
            pass

    return default

def get_slack_messages(channel_id=None, limit=5):
    """Retorna lista de mensajes recientes de Slack en formato dict estructurado."""
    token = get_secret("SLACK_USER_TOKEN") or get_secret("SLACK_BOT_TOKEN")
    if not token:
        return {"ok": False, "error": "No token configurado (SLACK_BOT_TOKEN / SLACK_USER_TOKEN)"}

    ch = channel_id or get_secret("SLACK_CHANNEL_PRACTICAS", "C0APHGKPTHA")
    url = f"https://slack.com/api/conversations.history?channel={ch}&limit={limit}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    })

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                return {"ok": False, "error": data.get("error")}
            
            messages = []
            for m in data.get("messages", []):
                messages.append({
                    "user": m.get("user", m.get("bot_id", "bot")),
                    "text": m.get("text", "").strip(),
                    "ts": m.get("ts", "")
                })
            return {"ok": True, "channel": ch, "messages": messages}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def post_slack_message(text, channel_id=None):
    """Envía un mensaje a Slack de forma segura."""
    webhook = get_secret("SLACK_WEBHOOK_URL")
    if webhook:
        try:
            req = urllib.request.Request(webhook, data=json.dumps({"text": text}).encode("utf-8"), headers={
                "Content-Type": "application/json"
            }, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    token = get_secret("SLACK_USER_TOKEN") or get_secret("SLACK_BOT_TOKEN")
    if not token:
        return {"ok": False, "error": "Sin credenciales de Slack para enviar mensaje"}

    ch = channel_id or get_secret("SLACK_CHANNEL_PRACTICAS", "C0APHGKPTHA")
    url = "https://slack.com/api/chat.postMessage"
    req = urllib.request.Request(url, data=json.dumps({
        "channel": ch,
        "text": text,
        "username": "Juan Marcelo Rodriguez"
    }).encode("utf-8"), headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8"
    }, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {"ok": data.get("ok", False), "error": data.get("error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_github_sprint_context():
    """Consulta Milestones e Issues vía gh CLI para alimentar la Daily."""
    import subprocess
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
