"""
Slack: leer los mensajes recientes del canal y publicar.

Si Slack cambia su API, este archivo cambia solo. Nada de GitHub acá.

Ningún canal ni usuario está hardcodeado: el canal sale de SLACK_CHANNEL_ID (o
de SLACK_CHANNEL_PRACTICAS, por compatibilidad) o del argumento, y el nombre de
publicación de SLACK_USERNAME, que es opcional.
"""

import json
import urllib.request

from .secrets import get_secret

MISSING_CHANNEL = "Falta el canal: definí SLACK_CHANNEL_ID o pasá channel_id."


def _channel(channel_id=None):
    return channel_id or get_secret("SLACK_CHANNEL_ID") or get_secret("SLACK_CHANNEL_PRACTICAS")


def _decorate(payload, username):
    """Agrega el nombre de publicación sólo si está configurado."""
    if username:
        payload["username"] = username
    return payload


def get_slack_messages(channel_id=None, limit=5):
    """Retorna lista de mensajes recientes de Slack en formato dict estructurado."""
    token = get_secret("SLACK_USER_TOKEN") or get_secret("SLACK_BOT_TOKEN")
    if not token or token == "DISABLED":
        return {"ok": False, "error": "No token configurado (SLACK_BOT_TOKEN / SLACK_USER_TOKEN)"}

    ch = _channel(channel_id)
    if not ch:
        return {"ok": False, "error": MISSING_CHANNEL}

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
    username = get_secret("SLACK_USERNAME")

    webhook = get_secret("SLACK_WEBHOOK_URL")
    if webhook:
        body = json.dumps(_decorate({"text": text}, username)).encode("utf-8")
        try:
            req = urllib.request.Request(webhook, data=body, headers={
                "Content-Type": "application/json"
            }, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    token = get_secret("SLACK_USER_TOKEN") or get_secret("SLACK_BOT_TOKEN")
    if not token:
        return {"ok": False, "error": "Sin credenciales de Slack para enviar mensaje"}

    ch = _channel(channel_id)
    if not ch:
        return {"ok": False, "error": MISSING_CHANNEL}

    payload = _decorate({"channel": ch, "text": text}, username)

    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {"ok": data.get("ok", False), "error": data.get("error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}
