"""Guarda os títulos de todos os vídeos já publicados no canal, mesmo que você apague os vídeos
e o histórico do computador. O Claude usa essa lista para não repetir perguntas.

Fontes (públicas, sem chave):
  - feed RSS oficial do canal (os 15 mais recentes, com data)
  - página pública de Shorts e de vídeos do canal (os ~48 mais recentes de cada)
  - exportação do YouTube Studio enviada na aba Resultados (todos os vídeos)
A lista só cresce: nada é apagado. O painel sincroniza sozinho uma vez por dia.

Uso manual:
    python -I pipeline/titulos_canal.py
"""
import json
import re
import sys
import unicodedata
from datetime import datetime
from html import unescape
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "dados" / "videos-do-canal.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9"}


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"#\w+", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def ler():
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def juntar(novos):
    """Acrescenta vídeos à lista sem duplicar (pelo id do YouTube ou pelo título). Devolve quantos entraram."""
    lista = ler()
    ids = {v.get("id") for v in lista if v.get("id")}
    titulos = {norm(v.get("titulo")) for v in lista}
    entraram = 0
    for v in novos:
        chave = norm(v.get("titulo"))
        if not chave:
            continue
        existente = next((x for x in lista if (v.get("id") and x.get("id") == v["id"]) or norm(x.get("titulo")) == chave), None)
        if existente:  # completa dados que faltavam (id, data, views)
            for k in ("id", "publicado", "views", "formato"):
                if v.get(k) and not existente.get(k):
                    existente[k] = v[k]
            continue
        if v.get("id") in ids or chave in titulos:
            continue
        lista.append(v)
        ids.add(v.get("id"))
        titulos.add(chave)
        entraram += 1
    lista.sort(key=lambda v: v.get("publicado") or "", reverse=True)
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")
    return entraram


def id_do_canal(endereco):
    """Aceita o id (UC...), o link do canal ou o @nome; devolve o id UC..."""
    endereco = (endereco or "").strip()
    m = re.search(r"(UC[\w-]{22})", endereco)
    if m:
        return m.group(1)
    if not endereco:
        return None
    url = endereco if endereco.startswith("http") else f"https://www.youtube.com/{endereco.lstrip('/')}"
    if "youtube.com/" not in url:
        url = f"https://www.youtube.com/@{endereco.lstrip('@')}"
    try:
        r = requests.get(url, headers=UA, timeout=30)
        m = re.search(r'"(?:externalId|channelId)":"(UC[\w-]{22})"', r.text)
        return m.group(1) if m else None
    except requests.RequestException:
        return None


def do_feed(canal_id):
    r = requests.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": canal_id}, timeout=30)
    r.raise_for_status()
    videos = []
    for bloco in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
        titulo = re.search(r"<media:title>(.*?)</media:title>", bloco, re.S)
        vid = re.search(r"<yt:videoId>(.*?)</yt:videoId>", bloco)
        pub = re.search(r"<published>(.*?)</published>", bloco)
        link = re.search(r'<link rel="alternate" href="([^"]+)"', bloco)
        if titulo:
            videos.append({"titulo": unescape(titulo.group(1)).strip(), "id": vid.group(1) if vid else None,
                           "publicado": pub.group(1)[:10] if pub else None,
                           "formato": "short" if link and "/shorts/" in link.group(1) else None})
    return videos


def da_pagina(canal_id, aba):
    """Títulos da página pública do canal (/shorts ou /videos), só a primeira página."""
    r = requests.get(f"https://www.youtube.com/channel/{canal_id}/{aba}", headers=UA, timeout=30,
                     params={"hl": "pt", "gl": "BR"})
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", r.text, re.S)
    if not m:
        return []
    videos = []

    def andar(o):
        if isinstance(o, dict):
            if "shortsLockupViewModel" in o:
                v = o["shortsLockupViewModel"]
                t = v.get("overlayMetadata", {}).get("primaryText", {}).get("content")
                vid = (v.get("onTap", {}).get("innertubeCommand", {}).get("reelWatchEndpoint") or {}).get("videoId")
                if t:
                    videos.append({"titulo": t, "id": vid, "formato": "short"})
            elif "lockupViewModel" in o:
                v = o["lockupViewModel"]
                t = v.get("metadata", {}).get("lockupMetadataViewModel", {}).get("title", {}).get("content")
                if t:
                    videos.append({"titulo": t, "id": v.get("contentId"), "formato": "longo"})
            elif "videoRenderer" in o:
                v = o["videoRenderer"]
                t = "".join(x.get("text", "") for x in v.get("title", {}).get("runs", []))
                if t:
                    videos.append({"titulo": t, "id": v.get("videoId"), "formato": "longo"})
            for x in o.values():
                andar(x)
        elif isinstance(o, list):
            for x in o:
                andar(x)

    andar(json.loads(m.group(1)))
    return videos


def sincronizar(endereco):
    """Busca os vídeos recentes do canal e junta na lista. Devolve (quantos entraram, total)."""
    canal_id = id_do_canal(endereco)
    if not canal_id:
        raise ValueError("não achei o canal; confira o link em ⚙ Canal")
    novos = do_feed(canal_id)
    for aba in ("shorts", "videos"):
        try:
            novos += da_pagina(canal_id, aba)
        except (requests.RequestException, ValueError):
            pass
    entraram = juntar(novos)
    return entraram, len(ler())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    canal = json.loads((RAIZ / "dados" / "canal.json").read_text(encoding="utf-8"))
    if not canal.get("youtube"):
        sys.exit('Coloque o link do canal em ⚙ Canal (ou "youtube" em dados/canal.json).')
    entraram, total = sincronizar(canal["youtube"])
    print(f"{entraram} título(s) novo(s). Total guardado: {total} ({ARQUIVO.relative_to(RAIZ)}). "
          f"Atualizado em {datetime.now():%d/%m %H:%M}.")
