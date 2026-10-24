"""
Catálogo de tools MCP.

Esto es una tabla, no lógica: nombre, descripción, esquema y handler. Se
mantiene aparte de `protocol.py` porque cambia cuando agregás una tool, no
cuando cambiás el transporte.
"""

from .handlers import agents, channels, contract, governance, mock, workspace
from .schema import schema


def _tool(name, description, handler, properties=None, required=None):
    return {
        "name": name,
        "description": description,
        "inputSchema": schema(properties, required),
        "handler": handler,
    }


TOOLS = [
    # --- Gobernanza -------------------------------------------------------
    _tool(
        "chelo_status",
        "Estado integral del workspace: si es repo git, archivos modificados vs el límite de 10, "
        "contrato OpenAPI, tests Hurl, mock activo y stack detectado.",
        governance.h_status,
    ),
    _tool(
        "chelo_audit_changes",
        "Disyuntor de seguridad: cuenta los archivos modificados y avisa si se superó el límite de 10 por ciclo.",
        governance.h_audit_changes,
    ),
    _tool(
        "chelo_quality_gate",
        "Quality Gate completo: freno de 10 archivos + tests de contrato en verde. No commitea.",
        governance.h_quality_gate,
    ),
    _tool(
        "chelo_commit",
        "Commitea con gobernanza: exige Conventional Commits, rechaza atribución de IA y aplica el freno de 10 archivos.",
        governance.h_commit,
        {"message": {"type": "string", "description": "Mensaje en formato Conventional Commits."}},
        ["message"],
    ),
    # --- Contrato ---------------------------------------------------------
    _tool(
        "chelo_spec_read",
        "Lee el contrato OpenAPI del workspace: ruta, tamaño y endpoints con sus métodos. "
        "Con include_content=true devuelve el YAML completo.",
        contract.h_spec_read,
        {
            "path": {"type": "string", "description": "Ruta explícita al contrato. Por defecto se autodetecta."},
            "include_content": {"type": "boolean", "description": "Incluir el YAML completo en la respuesta."},
        },
    ),
    _tool(
        "chelo_contract_test",
        "Ejecuta la suite Hurl contra el contrato. Levanta el mock automáticamente si no está corriendo.",
        contract.h_contract_test,
    ),
    # --- Mock -------------------------------------------------------------
    _tool(
        "chelo_mock_start",
        "Levanta el mock del contrato en segundo plano (Prism, o el servidor nativo de Python si Prism no está) "
        "y espera a que el puerto responda.",
        mock.h_mock_start,
        {"port": {"type": "integer", "description": "Puerto del mock. Por defecto 4010."}},
    ),
    _tool(
        "chelo_mock_status",
        "Informa si el mock responde, qué motor usa, su PID y el contrato que está sirviendo.",
        mock.h_mock_status,
        {"port": {"type": "integer", "description": "Puerto a verificar. Por defecto el registrado o 4010."}},
    ),
    _tool(
        "chelo_mock_stop",
        "Detiene el mock lanzado por chelo_mock_start y limpia el estado.",
        mock.h_mock_stop,
    ),
    # --- Workspace --------------------------------------------------------
    _tool(
        "chelo_stack",
        "Detecta el stack del proyecto (backend, frontend, package manager) y la disponibilidad de "
        "hurl, prism, gh y opencode.",
        workspace.h_stack,
    ),
    _tool(
        "chelo_doctor",
        "Diagnóstico del entorno: binarios disponibles y claves de API configuradas (enmascaradas). No modifica nada.",
        workspace.h_doctor,
    ),
    _tool(
        "chelo_init",
        "Inicializa la metodología Spec-First en el workspace: git, openapi.yaml base, AGENTS.md y un test Hurl "
        "de salud. Idempotente.",
        workspace.h_init,
    ),
    _tool(
        "chelo_board_init",
        "Inyecta el workflow de Daily Board (GitHub Pages) en el repo y configura Pages si gh está autenticado. "
        "Idempotente.",
        workspace.h_board_init,
        {"force": {"type": "boolean", "description": "Sobrescribir el workflow si ya existe."}},
    ),
    _tool(
        "chelo_board_url",
        "Resuelve el slug owner/repo del remoto origin y la URL pública del Daily Board.",
        workspace.h_board_url,
    ),
    # --- Canales ágiles ---------------------------------------------------
    _tool(
        "chelo_sync",
        "Daily Scrum: trae mensajes recientes de Slack y el milestone activo con issues abiertos de GitHub. Solo lectura.",
        channels.h_sync,
        {
            "channel_id": {"type": "string", "description": "Canal de Slack. Por defecto el configurado en el entorno."},
            "slack_limit": {"type": "integer", "description": "Cantidad de mensajes de Slack (por defecto 5)."},
            "include_slack": {"type": "boolean", "description": "Consultar Slack. Por defecto true."},
            "include_github": {"type": "boolean", "description": "Consultar GitHub. Por defecto true."},
        },
    ),
    _tool(
        "chelo_slack_post",
        "Publica un mensaje en Slack usando webhook o token del entorno.",
        channels.h_slack_post,
        {
            "text": {"type": "string", "description": "Mensaje a publicar."},
            "channel_id": {"type": "string", "description": "Canal destino."},
        },
        ["text"],
    ),
    # --- Agentes ----------------------------------------------------------
    _tool(
        "chelo_agent_turn",
        "Invoca un agente del arnés (story-agent, spec-architect, qa-tester, lead-architect, frontend-dev, "
        "backend-dev, git-agent) y devuelve el artefacto. Con use_tools=true entra en modo autónomo: lee "
        "archivos, lista directorios y escribe dentro de docs/. Consume la API key configurada.",
        agents.h_agent_turn,
        {
            "role": {"type": "string", "description": "Rol del agente."},
            "instruction": {"type": "string", "description": "Tarea a ejecutar."},
            "context": {"type": "string", "description": "Contexto adicional (contrato, historia, diff)."},
            "out_path": {"type": "string", "description": "Si se indica, escribe el artefacto en esa ruta relativa."},
            "use_tools": {"type": "boolean", "description": "Habilitar el bucle de function calling (read_file, list_dir, write_doc). Por defecto false."},
            "max_steps": {"type": "integer", "description": "Máximo de pasos autónomos (por defecto 5)."},
        },
        ["role", "instruction"],
    ),
    _tool(
        "chelo_pipeline",
        "Pipeline Spec-First completo: Story-Agent (BDD) → Spec-Architect (OpenAPI) → QA-Tester (Hurl) → "
        "verificación real contra el mock. Escribe archivos y consume tokens.",
        agents.h_pipeline,
        {
            "requirement": {"type": "string", "description": "Requerimiento a convertir en contrato."},
            "project": {"type": "string", "description": "Nombre del proyecto. Por defecto el directorio."},
            "trace": {"type": "boolean", "description": "Incluir traza de auditoría en el log."},
        },
        ["requirement"],
    ),
]

TOOL_INDEX = {tool["name"]: tool for tool in TOOLS}
