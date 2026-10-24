"""
Handlers de canales ágiles: Slack y GitHub.
"""

from ..runtime import enter


def h_sync(args):
    with enter(args):
        from lib.channels import get_github_sprint_context, get_slack_messages

        payload = {"slack": None, "github": None}

        if args.get("include_slack", True):
            payload["slack"] = get_slack_messages(
                channel_id=args.get("channel_id"),
                limit=int(args.get("slack_limit") or 5),
            )
        if args.get("include_github", True):
            payload["github"] = get_github_sprint_context()

        return payload


def h_slack_post(args):
    with enter(args):
        from lib.channels import post_slack_message

        text = (args.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "Falta el texto del mensaje."}
        return post_slack_message(text, channel_id=args.get("channel_id"))
