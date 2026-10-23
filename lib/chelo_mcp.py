#!/usr/bin/env python3
"""
chelo_mcp.py — Servidor MCP oficial de Chelo-Harness (Spec-First & Gobernanza)
Permite a cualquier cliente MCP (como Antigravity CLI / AGY) invocar las herramientas
de gobernanza, tests Hurl, Quality Gate y servidor Mock.
"""

import sys
import json
import os
import subprocess
from pathlib import Path

def get_git_status():
    res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    files = [l for l in res.stdout.splitlines() if l.strip()]
    return len(files), files

def run_tests():
    hurl_files = sorted(list(Path.cwd().glob("**/*.hurl")))
    if not hurl_files:
        return {"passed": False, "message": "No se encontraron archivos .hurl"}
    
    passed_count = 0
    errors = []
    for hf in hurl_files:
        res = subprocess.run(["hurl", "--test", str(hf)], capture_output=True, text=True)
        if res.returncode == 0:
            passed_count += 1
        else:
            errors.append(f"{hf.name}: {res.stderr.strip()[:300]}")
            
    return {
        "passed": len(errors) == 0,
        "total": len(hurl_files),
        "passed_count": passed_count,
        "errors": errors
    }

TOOLS = [
    {
        "name": "chelo_audit_changes",
        "description": "Verifica el disyuntor de seguridad de Chelo-Harness (máximo 10 archivos modificados por ciclo).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "chelo_contract_test",
        "description": "Ejecuta la suite de pruebas Hurl contra el contrato OpenAPI y el servidor Mock/Backend.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "chelo_quality_gate",
        "description": "Ejecuta el Quality Gate completo de Chelo-Harness (freno de 10 archivos + verificación Hurl sin sl-violations).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

def handle_call_tool(name, args):
    if name == "chelo_audit_changes":
        count, files = get_git_status()
        is_safe = count <= 10
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "modified_files_count": count,
                        "is_safe": is_safe,
                        "limit": 10,
                        "files": files
                    }, indent=2)
                }
            ],
            "isError": not is_safe
        }
    elif name == "chelo_contract_test":
        result = run_tests()
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ],
            "isError": not result["passed"]
        }
    elif name == "chelo_quality_gate":
        count, _ = get_git_status()
        if count > 10:
            return {
                "content": [{"type": "text", "text": f"❌ Freno de contención: {count} archivos modificados (límite: 10)."}],
                "isError": True
            }
        test_res = run_tests()
        if not test_res["passed"]:
            return {
                "content": [{"type": "text", "text": f"❌ Fallaron tests de contrato: {json.dumps(test_res['errors'])}"}],
                "isError": True
            }
        return {
            "content": [{"type": "text", "text": "✓ Quality Gate superado exitosamente (Contención <10 + Tests Hurl en verde)."}],
            "isError": False
        }
    else:
        return {
            "content": [{"type": "text", "text": f"Herramienta desconocida: {name}"}],
            "isError": True
        }

def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            
            if method == "initialize":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {
                            "name": "chelo-harness-mcp",
                            "version": "1.0.0"
                        },
                        "capabilities": {
                            "tools": {}
                        }
                    }
                }
            elif method == "tools/list":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS
                    }
                }
            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})
                result = handle_call_tool(name, args)
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": result
                }
            elif method == "notifications/initialized":
                continue
            else:
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_res = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
