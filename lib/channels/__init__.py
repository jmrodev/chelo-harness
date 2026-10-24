"""
Canales ágiles: Slack y GitHub.

    secrets.py  de dónde salen las credenciales
    slack.py    leer y publicar mensajes
    github.py   milestone activo e issues abiertos

Son dos servicios independientes: un cambio en la API de Slack no puede tocar
código de GitHub. Este `__init__` reexporta la superficie pública para que el
resto del código importe desde `lib.channels`.
"""

from .github import get_github_sprint_context
from .secrets import get_secret
from .slack import get_slack_messages, post_slack_message

__all__ = [
    "get_github_sprint_context",
    "get_secret",
    "get_slack_messages",
    "post_slack_message",
]
