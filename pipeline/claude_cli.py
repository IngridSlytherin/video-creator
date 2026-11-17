"""Chamar o Claude Code em segundo plano (modo -p), usado pelo painel e pelo gerador.

Usa o comando 'claude' do sistema, o caminho em CLAUDE_EXE (.env) ou o que vem com o app do Claude.
Modelo: CLAUDE_MODELO no .env (padrão: sonnet).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def ler_env():
    env = {}
    arq = RAIZ / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def achar_claude():
    """Comando 'claude': do .env (CLAUDE_EXE), do sistema, ou o que vem com o app do Claude."""
    exe = ler_env().get("CLAUDE_EXE") or shutil.which("claude")
    if exe:
        return exe
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Claude-Data"
    achados = sorted(base.glob("*/claude-code/*/*/claude.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(achados[0]) if achados else None


def modelo():
    return ler_env().get("CLAUDE_MODELO", "sonnet")


def ambiente():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("CLAUDECODE", None)  # permite chamar o Claude mesmo de dentro de uma sessão do Claude Code
    return env


def perguntar(prompt, ferramentas=("Read",), timeout=300):
    """Faz um pedido ao Claude e devolve o texto da resposta final (ou None se não deu)."""
    exe = achar_claude()
    if not exe:
        return None
    cmd = [exe, "-p", "--output-format", "json", "--model", modelo(), "--allowedTools", *ferramentas]
    try:
        r = subprocess.run(cmd, input=prompt, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=ambiente(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        dados = json.loads(r.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if dados.get("is_error"):
        return None
    return dados.get("result") or ""


def extrair_json(texto):
    """Pega o primeiro objeto JSON de uma resposta (o Claude às vezes escreve algo em volta)."""
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini < 0 or fim < ini:
        raise ValueError("a resposta não trouxe JSON")
    return json.loads(texto[ini: fim + 1])
