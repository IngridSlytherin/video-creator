"""Atualiza o app: baixa a versão nova do GitHub e instala só o que mudou.

Uso (o painel chama sozinho pelo botão "Atualizar agora"):
    python -I pipeline/atualizar.py

Seus dados (canal, chave do Pexels, roteiros, vídeos) não são tocados: eles não fazem parte do
GitHub (veja .gitignore).
"""
import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent


def git(*args):
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


def etapa(n, texto):
    print(f"[etapa {n}/3] {texto}", flush=True)


def main():
    etapa(1, "Baixando a versão nova")
    alterados = git("status", "--porcelain", "--untracked-files=no")
    if alterados:
        sys.exit("Você mudou arquivos do app, por isso a atualização automática parou para não "
                 "apagar suas mudanças:\n" + alterados +
                 "\nPeça ao Claude Code: 'atualize o projeto com git pull mantendo minhas mudanças'.")
    antes = git("rev-parse", "HEAD")
    try:
        print(git("pull", "--ff-only"), flush=True)
    except RuntimeError as e:
        sys.exit(f"Não consegui baixar a versão nova: {e}")
    depois = git("rev-parse", "HEAD")
    mudou = set(git("diff", "--name-only", antes, depois).splitlines()) if antes != depois else set()

    etapa(2, "Instalando o que mudou")
    if mudou & {"package.json", "package-lock.json"}:
        print("Instalando pacotes do Node (npm install)...", flush=True)
        subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "install"], cwd=RAIZ, check=True)
    if "requirements.txt" in mudou:
        print("Instalando pacotes do Python...", flush=True)
        # -s: instala onde o "python -I" enxerga
        subprocess.run([sys.executable, "-s", "-m", "pip", "install", "-r", "requirements.txt"],
                       cwd=RAIZ, check=True)
    if not mudou & {"package.json", "package-lock.json", "requirements.txt"}:
        print("Nenhum pacote novo para instalar.", flush=True)

    etapa(3, "Pronto")
    print(f"Atualizado: {len(mudou)} arquivo(s) mudaram.", flush=True)


if __name__ == "__main__":
    main()
