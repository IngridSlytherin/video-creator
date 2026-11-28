"""
Gera vídeos do seu canal (configurado em dados/canal.json) a partir de um roteiro JSON.

Uso:
    python -I pipeline/gerar_video.py roteiros/<arquivo>.json
    python -I pipeline/gerar_video.py roteiros/<arquivo>.json --so-publicacao
    python -I pipeline/gerar_video.py roteiros/<arquivo>.json --manter-clipes
    python -I pipeline/gerar_video.py roteiros/<arquivo>.json --sem-shorts

Formatos:
- "short": vertical 9:16, segmentos simples.
- "longo": horizontal 16:9, dividido em "capitulos". Capítulos com "short"
  viram Shorts verticais separados, gerados no final.

Passos: narração (edge-tts) -> clipes (Pexels) -> props -> render (Remotion)
-> thumbnail (só longo) -> publicacao.txt. Resultado em saida/<slug>/.
"""
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import edge_tts
import requests
import socket
import urllib3.util.connection as _conexao

# Algumas redes anunciam IPv6 mas não o entregam: cada conexão esperaria ~21 s antes de cair para o
# IPv4 (o radar chegou a levar 18 min). Todos os sites usados aqui têm IPv4, então usamos só ele.
_conexao.allowed_gai_family = lambda: socket.AF_INET

RAIZ = Path(__file__).resolve().parent.parent
FPS = 30
PAUSA_ENTRE_SEGMENTOS = 0.25
PAUSA_ENTRE_CAPITULOS = 0.8

# Faixas de duração (segundos). O YouTube aceita Shorts de até 3 min.
DURACOES = {
    "curto": (30, 45),     # Short: um fato só, direto ao ponto
    "padrao": (40, 65),    # Short: o formato que o canal já usa (~1 min)
    "longo": (75, 120),    # Short: listas, comparações, várias partes
    "video": (240, 720),   # vídeo longo horizontal: 4 a 12 min
}

# Ritmo e qualidade dos clipes por formato
CONFIG_FORMATO = {
    "short": {"orientacoes": ("portrait", "landscape"), "seg_por_clipe": 2.5,
              "novos_por_segmento": None},
    # no longo, primeiro os deitados; os em pé só entram depois (quando o assunto tem pouca filmagem),
    # no meio da tela com fundo desfocado (vertical recortado para deitado ficaria horrível).
    # Menos downloads: cada clipe baixado é reaproveitado em mais de um trecho do mesmo animal.
    "longo": {"orientacoes": ("landscape", "portrait"), "seg_por_clipe": 4.5,
              "novos_por_segmento": 3},
}


def deitar_clipe(arq: Path):
    """Clipe em pé num vídeo deitado: ele fica inteiro no meio, sobre uma cópia dele desfocada."""
    tmp = arq.with_suffix(".deitado.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(arq), "-an", "-r", "30", "-filter_complex",
                    "[0:v]split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                    "scale=480:270,boxblur=10:2,scale=1920:1080,eq=brightness=-0.2[fundo];"
                    "[b]scale=-2:1080,setsar=1[frente];[fundo][frente]overlay=(W-w)/2:0",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(arq)



def carregar_env():
    env = {}
    arq = RAIZ / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = carregar_env()

_spec_canal = importlib.util.spec_from_file_location("canal", RAIZ / "pipeline" / "canal.py")
canal_cfg = importlib.util.module_from_spec(_spec_canal)
_spec_canal.loader.exec_module(canal_cfg)
_spec_cli = importlib.util.spec_from_file_location("claude_cli", RAIZ / "pipeline" / "claude_cli.py")
claude_cli = importlib.util.module_from_spec(_spec_cli)
_spec_cli.loader.exec_module(claude_cli)


def log(msg):
    print(f"[curioso] {msg}", flush=True)


def hashtag(texto):
    """'Sangue azul' -> 'sangueazul' (sem acento, espaço ou símbolo)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


# ---------- 0. Roteiro ----------
def segmentos_do_roteiro(roteiro):
    """Achata o roteiro numa lista de segmentos, cada um sabendo seu capítulo
    e quais palavras o clipe precisa ter (exigir) ou não pode ter (evitar)."""
    capitulos = roteiro.get("capitulos") or [{"titulo": "", "segmentos": roteiro["segmentos"]}]
    segs = []
    for ci, cap in enumerate(capitulos):
        animal = cap.get("animal") or roteiro.get("animal")
        for si, seg in enumerate(cap["segmentos"]):
            exigir = seg.get("exigir") or ([animal] if animal else seg["busca"])
            segs.append({
                **seg,
                "capitulo": ci,
                "primeiroDoCapitulo": si == 0,
                "exigir": exigir,
                "evitar": seg.get("evitar") or cap.get("evitar") or roteiro.get("evitar") or [],
            })
    return capitulos, segs


# ---------- 1. Narração ----------
def voz_do_canal():
    """Voz da língua do canal (dados/canal.json, campo "voz"); o .env (VOZ) só vale se o canal não tiver."""
    canal = canal_cfg.carregar(obrigatorio=False) or {}
    return canal.get("voz") or ENV.get("VOZ") or canal_cfg.idioma(canal)["voz"]


async def narrar_segmento(texto, destino: Path, velocidade, voz=None):
    """Gera mp3 e devolve a lista de palavras com tempo (ms)."""
    com = edge_tts.Communicate(
        texto,
        voice=voz or voz_do_canal(),
        rate=velocidade,
        boundary="WordBoundary",
    )
    palavras = []
    with open(destino, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                ini = chunk["offset"] / 10_000
                palavras.append({
                    "texto": chunk["text"],
                    "inicioMs": ini,
                    "fimMs": ini + chunk["duration"] / 10_000,
                })
    return palavras


def narrar(texto, destino: Path, velocidade, voz=None, tentativas=8):
    """Narra um trecho conferindo se o áudio veio inteiro. O serviço de voz às vezes não devolve
    nada ou devolve a frase cortada: nesses casos, tenta de novo (com uma pequena espera)."""
    esperadas = len([t for t in texto.split() if re.search(r"\w", t)])
    ultimo_erro = None
    for n in range(tentativas):
        try:
            palavras = asyncio.run(narrar_segmento(texto, destino, velocidade, voz=voz))
            inteiro = len(palavras) >= max(1, int(esperadas * 0.8)) and destino.stat().st_size > 1500
            # às vezes chegam todas as palavras, mas o áudio para no meio: confere a duração
            # do arquivo com o fim da última palavra
            fala = max((p["fimMs"] for p in palavras), default=0) / 1000
            som = duracao_audio(destino) if inteiro else 0
            if inteiro and som >= fala - 0.3:
                return palavras
            ultimo_erro = (f"áudio cortado ({som:.1f} s de {fala:.1f} s)" if inteiro
                           else f"veio cortado ({len(palavras)} de {esperadas} palavras)")
        except Exception as e:  # noqa: BLE001 - erros do serviço de voz (sem áudio, conexão)
            ultimo_erro = e.__class__.__name__
        if n < tentativas - 1:
            log(f"  a voz falhou ({ultimo_erro}); tentando de novo...")
            time.sleep(min(2 * (n + 1), 10))  # ~1 min no total: o serviço costuma voltar
    raise RuntimeError(f"O serviço de voz da Microsoft não respondeu direito ({ultimo_erro}) depois de "
                       f"{tentativas} tentativas. Ele costuma voltar em alguns minutos: tente gerar de novo.")


# ---------- voz reserva (Piper: neural, grátis, roda sem internet) ----------
PASTA_RESERVA = RAIZ / "trabalho" / "vozes-reserva"
_VOZES_RESERVA = {}


def voz_reserva(idioma=None):
    """Carrega a voz reserva da língua do canal (baixa ~60 MB na primeira vez). None se não der."""
    try:
        from piper import PiperVoice
    except ImportError:
        return None
    canal = canal_cfg.carregar(obrigatorio=False) or {}
    modelo = canal_cfg.IDIOMAS.get(idioma or canal.get("idioma"), canal_cfg.IDIOMAS[canal_cfg.IDIOMA_PADRAO])["reserva"]
    if modelo not in _VOZES_RESERVA:
        arq = PASTA_RESERVA / modelo
        if not arq.exists() or not arq.with_name(arq.name + ".json").exists():
            try:
                from huggingface_hub import hf_hub_download
                log("  baixando a voz reserva (só na primeira vez, ~60 MB)...")
                for nome in (modelo, modelo + ".json"):
                    hf_hub_download("rhasspy/piper-voices", nome, local_dir=str(PASTA_RESERVA))
            except Exception as e:  # noqa: BLE001
                log(f"  não consegui baixar a voz reserva ({e.__class__.__name__})")
                return None
        _VOZES_RESERVA[modelo] = PiperVoice.load(str(arq))
    return _VOZES_RESERVA[modelo]


def narrar_reserva(texto, destino: Path, velocidade, idioma=None):
    """Narra com a voz reserva. O Piper não diz quando cada palavra é falada: o tempo de cada uma
    é estimado pelo tamanho dela, dentro do trecho com fala (sem os silêncios das pontas)."""
    import wave
    import numpy as np
    from piper import SynthesisConfig
    voz = voz_reserva(idioma)
    if voz is None:
        raise RuntimeError("voz reserva indisponível")
    m = re.match(r"([+-]\d+)%", velocidade or "")
    rapidez = 1 + int(m.group(1)) / 100 if m else 1.0
    wav = destino.with_suffix(".wav")
    with wave.open(str(wav), "wb") as w:
        voz.synthesize_wav(texto, w, syn_config=SynthesisConfig(length_scale=1 / max(0.5, rapidez)))
    with wave.open(str(wav), "rb") as w:
        taxa = w.getframerate()
        amostras = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    fala = np.nonzero(np.abs(amostras) > 600)[0]
    ini_s, fim_s = (fala[0] / taxa, fala[-1] / taxa) if len(fala) else (0, len(amostras) / taxa)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-ar", "24000", "-ac", "1",
                    "-c:a", "libmp3lame", "-q:a", "3", str(destino)], check=True)
    wav.unlink(missing_ok=True)
    tokens = [t for t in texto.split() if re.search(r"\w", t)]
    pesos = [len(t) + 2 + (6 if re.search(r"[.,!?;:]$", t) else 0) for t in tokens]
    total, cursor, palavras = sum(pesos) or 1, ini_s, []
    for t, p in zip(tokens, pesos):
        dur = (fim_s - ini_s) * p / total
        palavras.append({"texto": t, "inicioMs": cursor * 1000, "fimMs": (cursor + dur * 0.85) * 1000})
        cursor += dur
    return palavras


def duracao_audio(caminho: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(caminho)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def silencio(pasta: Path, segundos: float) -> Path:
    arq = pasta / f"silencio_{int(segundos * 1000)}.mp3"
    if not arq.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "anullsrc=r=24000:cl=mono", "-t", str(segundos),
                        "-q:a", "9", str(arq)], check=True)
    return arq


def gerar_narracao(segs, pasta: Path, velocidade, voz=None):
    log(f"Gerando narração ({len(segs)} trechos)...")
    try:
        return _gerar_narracao(segs, pasta, velocidade, voz, reserva=False)
    except RuntimeError as e:
        if voz_reserva() is None:
            raise
        # Se a voz da Microsoft cair de vez, o vídeo inteiro usa a reserva (para não misturar duas vozes).
        log(f"A voz da Microsoft não está respondendo ({str(e)[:80]}...). Usando a voz reserva neste vídeo.")
        return _gerar_narracao(segs, pasta, velocidade, voz, reserva=True)


def _gerar_narracao(segs, pasta: Path, velocidade, voz, reserva):
    lista_ffmpeg, cursor = [], 0.0
    for i, seg in enumerate(segs):
        mp3 = pasta / f"voz_{i:03d}.mp3"
        palavras = (narrar_reserva(seg["texto"], mp3, velocidade) if reserva
                    else narrar(seg["texto"], mp3, velocidade, voz=voz))
        proximo_novo_cap = i + 1 < len(segs) and segs[i + 1]["primeiroDoCapitulo"]
        pausa = PAUSA_ENTRE_CAPITULOS if proximo_novo_cap else PAUSA_ENTRE_SEGMENTOS
        dur = duracao_audio(mp3) + pausa
        for p in palavras:
            p["inicioMs"] += cursor * 1000
            p["fimMs"] += cursor * 1000
        seg.update({"inicio": cursor, "duracao": dur, "palavras": palavras})
        lista_ffmpeg += [mp3.name, silencio(pasta, pausa).name]
        cursor += dur

    lista = pasta / "lista.txt"
    lista.write_text("".join(f"file '{n}'\n" for n in lista_ffmpeg), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-c:a", "libmp3lame", "-q:a", "2",
                    str(pasta / "narracao.mp3")], check=True, cwd=pasta)
    for arq in list(pasta.glob("voz_*.mp3")) + list(pasta.glob("silencio_*.mp3")) + [lista]:
        arq.unlink()
    log(f"Narração pronta: {cursor:.1f} s ({cursor / 60:.1f} min)")
    return cursor


# ---------- 2. Clipes do Pexels ----------
def buscar_pexels(consulta, orientacao, paginas=2):
    videos = []
    for pagina in range(1, paginas + 1):
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": ENV["PEXELS_API_KEY"]},
            params={"query": consulta, "orientation": orientacao,
                    "per_page": 80, "page": pagina},
            timeout=30)
        r.raise_for_status()
        lote = r.json().get("videos", [])
        for v in lote:
            v["_vertical"] = orientacao == "portrait"
        videos += lote
        if len(lote) < 80:
            break
    return videos


PASTA_CACHE_PIXABAY = RAIZ / "dados" / "cache-pixabay"


def buscar_pixabay(consulta, orientacao):
    """Segunda fonte de vídeos (precisa de PIXABAY_API_KEY no .env; sem ela, devolve []).
    Devolve no mesmo formato do Pexels. As buscas ficam guardadas 24 h, como a API pede."""
    chave = ENV.get("PIXABAY_API_KEY")
    if not chave:
        return []
    PASTA_CACHE_PIXABAY.mkdir(parents=True, exist_ok=True)
    arq = PASTA_CACHE_PIXABAY / (hashlib.md5(consulta.lower().encode()).hexdigest() + ".json")
    if arq.exists() and time.time() - arq.stat().st_mtime < 24 * 3600:
        hits = json.loads(arq.read_text(encoding="utf-8"))
    else:
        try:
            r = requests.get("https://pixabay.com/api/videos/", timeout=30, params={
                "key": chave, "q": consulta[:100], "lang": "en", "video_type": "film",
                "safesearch": "true", "per_page": 100})
            r.raise_for_status()
            hits = r.json().get("hits", [])
        except (requests.RequestException, ValueError) as e:
            log(f"  aviso: Pixabay não respondeu para '{consulta}' ({e.__class__.__name__})")
            return []
        arq.write_text(json.dumps(hits), encoding="utf-8")
    videos = []
    for h in hits:
        arquivos = [{"file_type": "video/mp4", "width": v["width"], "height": v["height"], "link": v["url"]}
                    for v in (h.get("videos") or {}).values() if v.get("url") and v.get("width")]
        if not arquivos:
            continue
        maior = max(arquivos, key=lambda a: a["width"])
        if (maior["height"] > maior["width"]) != (orientacao == "portrait"):
            continue
        videos.append({"id": f"pb{h['id']}", "url": h.get("pageURL", ""), "_texto": h.get("tags", ""),
                       "duration": h.get("duration", 0), "user": {"name": h.get("user", "")},
                       "video_files": arquivos, "_vertical": orientacao == "portrait", "_fonte": "pixabay"})
    return videos


# Clipes que citam o animal mas não mostram o animal vivo e real.
PROIBIDAS = [
    "food", "dish", "grill", "cook", "fried", "fry", "plate", "restaurant", "kitchen",
    "market", "sushi", "salad", "meal", "seafood", "chef", "dinner", "lunch",
    "kite", "toy", "plush", "balloon", "cartoon", "animation", "animated", "illustration",
    "drawing", "painting", "sculpture", "statue", "costume", "tattoo", "render",
    "dead", "fishing", "fisherman", "caught",
    "inflatable", "float", "pool", "lawn", "ornament", "decoration", "neon", "wallpaper",
    "pattern", "print", "figurine", "souvenir", "fake", "plastic", "figure", "artificial",
    "woman", "women", "person", "people", "girl", "boy", "child", "kid", "tourist",
    "selfie", "model", "replica", "logo", "sticker",
    # telões/prédios e tomadas aéreas, em que o animal some ou nem é de verdade
    "display", "billboard", "screen", "building", "skyline", "city", "street",
    "aerial", "drone", "exploring",
    # parques de diversão (ex.: o brinquedo "Octopus" do Pixabay)
    "carousel", "fairground", "amusement", "carnival",
]
# Palavras curtas que só bloqueiam quando aparecem inteiras (evita "man" barrar "mangrove").
PROIBIDAS_EXATAS = {"man", "men", "hand", "hands", "eat", "raw", "3d", "pet", "art", "fair", "ride"}


def relevante(video, exigir, evitar=()):
    """A busca do Pexels é solta: só aceita o clipe se o endereço da página
    (que descreve o vídeo, ex.: /video/octopus-swimming-123/) citar o termo."""
    # Pexels descreve o vídeo no endereço; o Pixabay, nas tags (_texto)
    texto = f"{video.get('url', '')} {video.get('_texto', '')}".lower()
    palavras = [p for p in re.split(r"[^a-z0-9]+", texto) if p]
    if any(p in PROIBIDAS_EXATAS or p in evitar for p in palavras):
        return False
    if any(p.startswith(proib) for p in palavras for proib in PROIBIDAS):
        return False
    termos = [t.lower() for e in exigir for t in e.split()]
    return any(p.startswith(t) for p in palavras for t in termos)


def melhor_arquivo(video):
    arquivos = [a for a in video["video_files"]
                if a.get("file_type") == "video/mp4" and a.get("width") and a.get("height")]
    # Vertical: largura ~1080. Horizontal: ~1440 de altura dá folga para o recorte
    # vertical do Short e boa nitidez no longo, sem baixar 4K pesado à toa.
    alvo = 1080 if video["_vertical"] else 1440
    # 60 fps só pesa no render (o vídeo final é 30 fps): na dúvida, fica com o de 30.
    arquivos.sort(key=lambda a: (min(a["width"], a["height"]) < 1080,
                                 abs(min(a["width"], a["height"]) - alvo) + (200 if (a.get("fps") or 30) > 31 else 0)))
    return arquivos[0] if arquivos else None


def baixar(url, destino: Path, tentativas=4):
    """Baixa o arquivo. Se o site pedir para esperar (429) ou falhar por um instante (5xx, rede),
    espera e tenta de novo; se não der, apaga o pedaço baixado e levanta o erro."""
    for n in range(tentativas):
        try:
            with requests.get(url, stream=True, timeout=180) as r:
                if r.status_code == 429 or r.status_code >= 500:
                    espera = int(r.headers.get("Retry-After") or 0) or 3 * 2**n
                    raise requests.HTTPError(f"{r.status_code}", response=r) if n == tentativas - 1 \
                        else _Esperar(min(60, espera))
                r.raise_for_status()
                with open(destino, "wb") as f:
                    for bloco in r.iter_content(1 << 16):
                        f.write(bloco)
            return
        except _Esperar as e:
            time.sleep(e.segundos)
        except (requests.ConnectionError, requests.Timeout):
            if n == tentativas - 1:
                destino.unlink(missing_ok=True)
                raise
            time.sleep(3 * 2**n)
        except requests.HTTPError:
            destino.unlink(missing_ok=True)
            raise


class _Esperar(Exception):
    def __init__(self, segundos):
        super().__init__(segundos)
        self.segundos = segundos


# Guarda as buscas já feitas: o vídeo longo e os Shorts dele repetem consultas,
# e o Pexels limita a 200 buscas por hora.
CACHE_PEXELS = {}


def baixar_clipes(segs, formato, pasta: Path, slug):
    cfg = CONFIG_FORMATO[formato]
    log("Buscando clipes no Pexels...")
    usados, cache, clipes = set(), CACHE_PEXELS, []
    baixados = {}   # grupo (animal) -> clipes já baixados, para reaproveitar
    n_arquivos = 0
    for idx, seg in enumerate(segs):
        if seg.get("_animacao"):  # trecho com animação Manim: a cena ocupa o trecho inteiro
            clipes.append({"arquivo": seg["_animacao"], "inicio": seg["inicio"], "duracao": seg["duracao"],
                           "inicioNoClipe": 0, "animacao": True, "assunto": "animação"})
            log(f"  trecho {idx + 1}/{len(segs)}: animação")
            continue
        qtd = max(1, math.ceil(seg["duracao"] / cfg["seg_por_clipe"]))
        dur_clipe = seg["duracao"] / qtd
        grupo = tuple(sorted(seg["exigir"]))
        meus = baixados.setdefault(grupo, [])

        pool = []
        for orient in cfg["orientacoes"]:
            lista = []
            for consulta in seg["busca"]:
                chave = (consulta, orient)
                if chave not in cache:
                    cache[chave] = buscar_pexels(consulta, orient)
                lista += cache[chave]
                chave_pb = ("pixabay", consulta, orient)
                if chave_pb not in cache:
                    cache[chave_pb] = buscar_pixabay(consulta, orient)
                lista += cache[chave_pb]
            vistos, filtrados = set(), []
            for v in lista:
                if (v["id"] not in usados and v["id"] not in vistos
                        and v.get("url") not in BLOQUEADOS
                        and relevante(v, seg["exigir"], seg["evitar"])
                        and v.get("duration", 0) >= dur_clipe + 0.5):
                    vistos.add(v["id"])
                    filtrados.append(v)
            # embaralha de forma estável por clipe: se um clipe for bloqueado, os outros
            # continuam na mesma ordem (e não precisam ser baixados de novo)
            filtrados.sort(key=lambda v: hashlib.md5(f"{slug}{idx}{orient}{v['id']}".encode()).hexdigest())
            pool += filtrados

        limite = cfg["novos_por_segmento"] or qtd
        novos = 0
        for k in range(qtd):
            inicio = seg["inicio"] + k * dur_clipe
            video = None
            while pool and novos < limite and video is None:
                candidato = pool.pop(0)
                usados.add(candidato["id"])
                # nome = número do vídeo no Pexels: ao trocar clipes ruins, os bons não são baixados de novo
                destino = pasta / f"clipe_{candidato['id']}.mp4"
                if not destino.exists():
                    try:
                        baixar(melhor_arquivo(candidato)["link"], destino)
                        if formato == "longo" and candidato.get("_vertical"):
                            deitar_clipe(destino)
                    except subprocess.CalledProcessError:
                        destino.unlink(missing_ok=True)
                        log("  clipe pulado (não consegui ajustar o formato); tentando outro")
                        continue
                    except requests.RequestException as e:
                        # um clipe que não baixa não pode parar o vídeo: pula e tenta o próximo
                        log(f"  clipe pulado (não baixou: {e.__class__.__name__}); tentando outro")
                        continue
                    n_arquivos += 1
                    if candidato.get("_fonte") == "pixabay":
                        time.sleep(0.5)  # o Pixabay recusa downloads muito seguidos
                video = candidato
            if video is not None:
                novos += 1
                meus.append({"arquivo": f"projetos/{slug}/{destino.name}",
                             "duracaoTotal": float(video.get("duration", 0)),
                             "usado": 0.0,
                             "autor": video.get("user", {}).get("name", ""),
                             "url": video.get("url", "")})
                base = meus[-1]
            else:
                # Reaproveita um clipe já baixado do mesmo animal, mostrando outro trecho.
                opcoes = meus
                if not opcoes:
                    # Nenhum clipe para este trecho (ex.: o banco chama o jacaré de "crocodile", não
                    # "caiman"): usa os clipes já baixados que dividem algum termo (ex.: "jaguar"),
                    # ou, em último caso, qualquer clipe do vídeo. Um trecho não pode parar o vídeo.
                    termos = set(seg["exigir"])
                    opcoes = [b for g, lst in baixados.items() if termos & set(g) for b in lst] or \
                             [b for lst in baixados.values() for b in lst]
                    if not opcoes:
                        raise RuntimeError(f"Nenhum clipe encontrado para: {seg['busca']}")
                    if k == 0:
                        log(f"  trecho {idx + 1}: nenhum clipe de {', '.join(seg['exigir'])}; "
                            "usando clipes parecidos do vídeo")
                livres = [b for b in opcoes if b["duracaoTotal"] - b["usado"] >= dur_clipe]
                base = max(livres, key=lambda b: b["duracaoTotal"] - b["usado"]) if livres \
                    else min(opcoes, key=lambda b: b["usado"])
            trecho = base["usado"] % max(0.1, base["duracaoTotal"] - dur_clipe)
            base["usado"] = trecho + dur_clipe
            clipes.append({"arquivo": base["arquivo"], "inicio": inicio, "duracao": dur_clipe,
                           "inicioNoClipe": trecho, "autor": base["autor"], "url": base["url"],
                           "assunto": ", ".join(seg["exigir"])})
        log(f"  trecho {idx + 1}/{len(segs)}: {qtd} cortes, {novos} clipes novos")
    log(f"{n_arquivos} clipes baixados para {len(clipes)} cortes")
    return clipes


# ---------- 2b. Conferência das imagens pelo Claude ----------
ARQ_BLOQUEADOS = RAIZ / "dados" / "clipes-bloqueados.json"
BLOQUEADOS = {}  # url do Pexels -> motivo (vale para todos os vídeos seguintes)
if ARQ_BLOQUEADOS.exists():
    BLOQUEADOS.update(json.loads(ARQ_BLOQUEADOS.read_text(encoding="utf-8")))
FONTE_NUMEROS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf"
POR_FOLHA = 12  # 4 x 3 quadros por imagem


def _quadro(arquivo, segundo, destino, numero):
    """Um quadro do clipe, 320x180, com o número no canto (para o Claude citar)."""
    filtro = "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2"
    if FONTE_NUMEROS.exists():
        fonte = str(FONTE_NUMEROS).replace("\\", "/").replace(":", "\\:")
        filtro += (f",drawtext=fontfile='{fonte}':text='{numero}':x=8:y=6:fontsize=30:fontcolor=yellow"
                   ":box=1:boxcolor=black@0.7:boxborderw=4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{segundo:.2f}", "-i", str(arquivo),
                    "-frames:v", "1", "-vf", filtro, "-q:v", "4", str(destino)], check=True)


def conferir_clipes(clipes, pasta: Path, aprovados=()):
    """Mostra ao Claude um quadro de cada clipe e devolve {url: motivo} dos que não servem
    (telão, brinquedo, desenho, comida, bicho errado...). Pula os já aprovados.
    Sem Claude, devolve {} e segue."""
    if os.environ.get("CONFERIR_CLIPES", "1") == "0" or not claude_cli.achar_claude():
        return {}
    unicos = {}
    for c in clipes:  # um quadro por arquivo, no primeiro trecho usado
        if c.get("animacao"):
            continue
        if c.get("url") not in aprovados:
            unicos.setdefault(c["arquivo"], c)
    if not unicos:
        return {}
    log(f"Conferindo as imagens ({len(unicos)} clipes) com o Claude...")
    trabalho = pasta / "conferencia"
    trabalho.mkdir(exist_ok=True)
    por_assunto = {}
    for c in unicos.values():
        por_assunto.setdefault(c.get("assunto", ""), []).append(c)

    numerados, folhas, n = {}, [], 0
    for assunto, lista in por_assunto.items():
        for i in range(0, len(lista), POR_FOLHA):
            grupo, quadros = lista[i:i + POR_FOLHA], []
            for c in grupo:
                n += 1
                numerados[n] = c
                q = trabalho / f"q{n:03d}.jpg"
                _quadro(RAIZ / "public" / c["arquivo"], c.get("inicioNoClipe", 0) + 0.5, q, n)
                quadros.append(q)
            lista_txt = trabalho / f"folha{len(folhas)}.txt"
            lista_txt.write_text("".join(f"file '{q.name}'\n" for q in quadros), encoding="utf-8")
            folha = trabalho / f"folha{len(folhas)}.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                            "-i", lista_txt.name, "-vf", "tile=4x3", "-frames:v", "1", "-q:v", "4", folha.name],
                           check=True, cwd=trabalho)
            folhas.append((folha, assunto, list(range(n - len(grupo) + 1, n + 1))))

    descricao = "\n".join(f"- {f.resolve()}  → clipes {ns[0]} a {ns[-1]}; o vídeo precisa mostrar: {a}"
                          for f, a, ns in folhas)
    prompt = f"""Você confere imagens para um vídeo do YouTube. Leia (Read) cada imagem abaixo: são folhas com
quadros de clipes do Pexels, cada quadro com um número amarelo no canto.
{descricao}

Um clipe NÃO serve se: não mostra o assunto de verdade (vivo/real, em destaque), mostra outro bicho
ou coisa, é telão/prédio/estátua/brinquedo/desenho/pelúcia/comida, tem pessoas em destaque, ou está
escuro/borrado a ponto de não dar para ver nada. Na dúvida, o clipe serve.

Responda SOMENTE com JSON: {{"ruins": [{{"numero": 3, "motivo": "telão num prédio"}}]}}
(lista vazia se todos servem)."""
    resposta = claude_cli.perguntar(prompt, ("Read",), timeout=600)
    shutil.rmtree(trabalho, ignore_errors=True)
    if resposta is None:
        log("  Não consegui falar com o Claude; seguindo sem conferir.")
        return {}
    try:
        ruins = claude_cli.extrair_json(resposta).get("ruins", [])
    except ValueError:
        log("  Resposta do Claude fora do formato; seguindo sem conferir.")
        return {}
    saida = {}
    for r in ruins:
        c = numerados.get(int(r.get("numero", 0)))
        if c and c.get("url"):
            saida[c["url"]] = str(r.get("motivo", ""))[:120]
            log(f"  clipe {r.get('numero')} não serve: {r.get('motivo', '')} ({c['url'].rstrip('/').split('/')[-1]})")
    if not saida:
        log("  Todas as imagens conferem.")
    return saida


def baixar_clipes_conferidos(segs, formato, pasta: Path, slug):
    """Baixa, confere com o Claude e troca os clipes ruins (até 3 conferências; cada uma só olha
    os clipes que ainda não foram aprovados)."""
    clipes = baixar_clipes(segs, formato, pasta, slug)
    aprovados = set()
    for rodada in range(3):
        ruins = conferir_clipes(clipes, pasta, aprovados)
        aprovados |= {c["url"] for c in clipes if c.get("url") and c["url"] not in ruins}
        if not ruins or rodada == 2:
            break
        BLOQUEADOS.update(ruins)
        ARQ_BLOQUEADOS.parent.mkdir(parents=True, exist_ok=True)
        ARQ_BLOQUEADOS.write_text(json.dumps(BLOQUEADOS, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"Trocando {len(ruins)} clipe(s) (rodada {rodada + 1})...")
        try:
            clipes = baixar_clipes(segs, formato, pasta, slug)
        except RuntimeError as e:
            log(f"  Sem substitutos suficientes ({e}); mantendo os clipes da rodada anterior.")
            break
    usados = {Path(c["arquivo"]).name for c in clipes}
    for arq in pasta.glob("clipe_*.mp4"):  # remove os trocados
        if arq.name not in usados:
            arq.unlink()
    return clipes


# ---------- 2c. Animações Manim (campo "manim" de um trecho) ----------
TIPOS_MANIM = {"comparacao", "numero", "linha_do_tempo", "proporcao"}


def renderizar_animacoes(roteiro, segs, formato, pasta: Path):
    """Transforma cada trecho com "manim" numa cena animada do tamanho exato da fala desse trecho.
    A cena entra no lugar dos clipes do trecho. Se o Manim não estiver instalado ou a cena falhar,
    o trecho continua com clipes normais (o vídeo não para)."""
    pedidos = [(i, s) for i, s in enumerate(segs)
               if isinstance(s.get("manim"), dict) and s["manim"].get("tipo") in TIPOS_MANIM]
    if not pedidos:
        return
    if roteiro.get("animacoes") is False or os.environ.get("ANIMACOES", "1") == "0":
        log("Animações desligadas para este vídeo; usando só clipes.")
        return
    if importlib.util.find_spec("manim") is None:
        log("Aviso: o Manim não está instalado (pip install manim); os trechos animados vão usar clipes.")
        return
    largura, altura = (1080, 1920) if formato == "short" else (1920, 1080)
    idioma = canal_cfg.carregar().get("idioma", canal_cfg.IDIOMA_PADRAO)
    trabalho = RAIZ / "trabalho" / "manim" / pasta.name
    shutil.rmtree(trabalho, ignore_errors=True)
    trabalho.mkdir(parents=True, exist_ok=True)
    for n, (i, seg) in enumerate(pedidos, 1):
        log(f"Criando animação {n}/{len(pedidos)} ({seg['manim']['tipo']})...")
        dados = {**seg["manim"], "formato": formato, "idioma": idioma,
                 "duracao": round(seg["duracao"] + 1.2, 2)}  # sobra no fim: o vídeo nunca fica sem imagem
        arq_dados = trabalho / f"cena_{i:03d}.json"
        arq_dados.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        nome = f"animacao_{i:03d}"
        r = subprocess.run([sys.executable, "-I", "-m", "manim", "render", "-qh", "--fps", "30",
                            "-r", f"{largura},{altura}", "--media_dir", str(trabalho), "-o", nome,
                            str(RAIZ / "pipeline" / "cenas_manim.py"), "CenaRoteiro"],
                           cwd=trabalho, env={**os.environ, "CENA_MANIM": str(arq_dados)},
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        feito = next(trabalho.rglob(f"{nome}.mp4"), None)
        if r.returncode != 0 or not feito:
            erro = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["?"]
            log(f"  a animação falhou ({erro[0][:160]}); esse trecho vai usar clipes")
            continue
        destino = pasta / f"{nome}.mp4"
        shutil.move(str(feito), destino)
        seg["_animacao"] = f"projetos/{pasta.name}/{destino.name}"
    shutil.rmtree(trabalho, ignore_errors=True)


# ---------- 3. Render ----------
RE_SEM_QUADRO = re.compile(r"No frame found at position.*?original source = \S*/(projetos/[^/\s]+/clipe_[\w-]+\.mp4)")


def converter_clipe(arq: Path):
    """Regrava o clipe em H.264 comum (30 fps, até 1920 px). Alguns vídeos dos bancos (60 fps, 2K/4K,
    timestamps estranhos) fazem o Remotion dizer "No frame found" no meio do render."""
    tmp = arq.with_suffix(".conv.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(arq), "-an", "-r", "30",
                    "-vf", "scale='min(1920,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(arq)


def arquivos_do_video(args):
    """Arquivos de public/ que este render usa (os caminhos que aparecem no props.json)."""
    props = next((a.split("=", 1)[1] for a in args if str(a).startswith("--props=")), None)
    if not props:
        return None
    try:
        dados = json.loads(Path(props).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    usados = set()

    def andar(o):
        if isinstance(o, dict):
            for v in o.values():
                andar(v)
        elif isinstance(o, list):
            for v in o:
                andar(v)
        elif isinstance(o, str) and "/" in o and len(o) < 300 and (RAIZ / "public" / o).is_file():
            usados.add(o)
    andar(dados)
    return usados


def pacote_remotion():
    """O Remotion "empacota" o projeto (~8 s) e copia a pasta public/ inteira a cada render.
    Aqui o pacote é feito uma vez só (com public/ vazia) e reaproveitado até o código de src/ mudar.
    Devolve a pasta do pacote, ou None se não deu (aí o render segue do jeito normal)."""
    h = hashlib.md5()
    for arq in sorted([*(RAIZ / "src").rglob("*"), RAIZ / "package-lock.json", RAIZ / "remotion.config.ts"]):
        if arq.is_file():
            h.update(arq.name.encode())
            h.update(arq.read_bytes())
    base = RAIZ / "trabalho" / "pacote"
    pasta = base / h.hexdigest()[:12]
    if (pasta / "index.html").exists():
        return pasta
    shutil.rmtree(base, ignore_errors=True)  # pacotes de versões antigas
    vazia = RAIZ / "trabalho" / "public-vazia"
    vazia.mkdir(parents=True, exist_ok=True)
    log("Preparando o pacote do Remotion (só quando o app muda)...")
    r = subprocess.run(["npx.cmd" if os.name == "nt" else "npx", "remotion", "bundle", "src/index.ts",
                        f"--out-dir={pasta}", f"--public-dir={vazia}"], cwd=RAIZ, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not (pasta / "index.html").exists():
        shutil.rmtree(pasta, ignore_errors=True)
        return None
    return pasta


def preparar_render(args):
    """Troca src/index.ts pelo pacote pronto e põe nele só os arquivos deste vídeo (hardlinks:
    instantâneo, sem ocupar espaço). Devolve (args, pasta pública usada) — ou os args originais."""
    if len(args) < 3 or args[0] != "remotion" or args[1] not in ("render", "still") or args[2] != "src/index.ts":
        return list(args), None
    usados = arquivos_do_video(args)
    pacote = pacote_remotion() if usados is not None else None
    if not pacote:
        return list(args), None
    publico = pacote / "public"
    shutil.rmtree(publico, ignore_errors=True)
    for rel in usados:
        alvo = publico / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(RAIZ / "public" / rel, alvo)
        except OSError:  # outro disco ou sistema sem hardlink: copia
            shutil.copy2(RAIZ / "public" / rel, alvo)
    return [args[0], args[1], str(pacote), *args[3:]], publico


def npx(*args, tentativas=3):
    """Roda o Remotion. Se um clipe não puder ser lido, converte esse clipe e tenta de novo."""
    for n in range(tentativas):
        try:
            usar, publico = preparar_render(args)
        except OSError:
            usar, publico = list(args), None
        cmd = ["npx.cmd" if os.name == "nt" else "npx", *usar]
        proc = subprocess.Popen(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        ultimas = []
        for linha in proc.stdout:
            print(linha, end="", flush=True)
            ultimas = (ultimas + [linha])[-60:]
        codigo = proc.wait()
        if publico:
            shutil.rmtree(publico, ignore_errors=True)
        if codigo == 0:
            return
        m = RE_SEM_QUADRO.search(re.sub(r"\x1b\[[0-9;]*m", "", "".join(ultimas)))
        arq = RAIZ / "public" / m.group(1) if m else None
        if not arq or not arq.exists() or n == tentativas - 1:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
        log(f"  O clipe {arq.name} veio num formato que o Remotion não lê; convertendo e tentando de novo...")
        converter_clipe(arq)


def info_capitulos(roteiro, capitulos, segs):
    """Início de cada capítulo e número na contagem regressiva (#7 ... #1)."""
    if "capitulos" not in roteiro:
        return []
    com_animal = [i for i, c in enumerate(capitulos) if c.get("animal")]
    saida = []
    for ci, cap in enumerate(capitulos):
        inicio = next(s["inicio"] for s in segs if s["capitulo"] == ci)
        numero = len(com_animal) - com_animal.index(ci) if ci in com_animal else None
        saida.append({"titulo": cap["titulo"], "inicio": round(inicio, 2), "numero": numero})
    return saida


def main(caminho_roteiro, manter_clipes=False, gerar_shorts=True):
    """Gera o vídeo. Se der erro no meio, apaga os clipes baixados mesmo assim (não acumulam no disco;
    na próxima tentativa a pasta do vídeo é refeita do zero de qualquer jeito)."""
    try:
        _main(caminho_roteiro, manter_clipes, gerar_shorts)
    except BaseException:
        if not manter_clipes:
            try:
                slug = json.loads(Path(caminho_roteiro).read_text(encoding="utf-8"))["slug"]
                for a in (RAIZ / "public" / "projetos" / slug).glob("clipe_*.mp4"):
                    a.unlink(missing_ok=True)
            except (OSError, ValueError, KeyError):
                pass
        raise


def limpar_sobras(horas=2):
    """Clipes esquecidos por um vídeo cancelado (o programa fechado no meio não chega a apagar)."""
    limite = time.time() - horas * 3600
    for a in (RAIZ / "public" / "projetos").glob("*/clipe_*.mp4"):
        try:
            if a.stat().st_mtime < limite:
                a.unlink()
        except OSError:
            pass


def _main(caminho_roteiro, manter_clipes=False, gerar_shorts=True):
    limpar_sobras()
    caminho_roteiro = Path(caminho_roteiro)
    roteiro = json.loads(caminho_roteiro.read_text(encoding="utf-8"))
    slug = roteiro["slug"]
    formato = roteiro.get("formato", "short")
    pasta_pub = RAIZ / "public" / "projetos" / slug
    pasta_saida = RAIZ / "saida" / slug
    if pasta_pub.exists():
        shutil.rmtree(pasta_pub)
    pasta_pub.mkdir(parents=True)
    pasta_saida.mkdir(parents=True, exist_ok=True)
    log(f"=== {slug} ({formato}) ===")

    capitulos, segs = segmentos_do_roteiro(roteiro)
    velocidade = roteiro.get("velocidadeVoz") or ENV.get("VELOCIDADE_VOZ", "+0%")
    voz = roteiro.get("voz")  # voz escolhida para este roteiro (opcional); senão, a do canal
    if voz:
        log(f"Voz: {voz}")
    duracao = gerar_narracao(segs, pasta_pub, velocidade, voz=voz)
    faixa = roteiro.get("duracao", "padrao")
    if faixa in DURACOES:
        minimo, maximo = DURACOES[faixa]
        if not minimo <= duracao <= maximo:
            log(f"ATENÇÃO: narração com {duracao:.0f} s, fora da faixa '{faixa}' "
                f"({minimo}-{maximo} s). Ajuste o tamanho do roteiro.")
    renderizar_animacoes(roteiro, segs, formato, pasta_pub)
    clipes = baixar_clipes_conferidos(segs, formato, pasta_pub, slug)
    caps = info_capitulos(roteiro, capitulos, segs)

    # Thumbnail só no vídeo longo: no Short o YouTube não deixa escolher a capa.
    com_thumbnail = formato != "short"
    if com_thumbnail:
        ci = roteiro.get("capaCapitulo", 0)
        filmados = [c for c in clipes if not c.get("animacao")] or clipes
        clipe_capa = next((c for c, s in zip(clipes, _seg_de_cada_clipe(clipes, segs))
                           if s["capitulo"] == ci and not c.get("animacao")), filmados[0])
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-ss", str(clipe_capa["inicioNoClipe"] + 1.0),
                        "-i", str(RAIZ / "public" / clipe_capa["arquivo"]),
                        "-frames:v", "1", "-q:v", "2", str(pasta_pub / "capa.jpg")], check=True)

    musicas = sorted((RAIZ / "public" / "musica").glob("*.mp3"))
    # animações (campo "grafico" em um trecho do roteiro): número contando ou comparação
    graficos = [{**s["grafico"], "inicio": round(s["inicio"], 3), "duracao": round(s["duracao"], 3)}
                for s in segs if isinstance(s.get("grafico"), dict) and s["grafico"].get("tipo")
                and not s.get("_animacao")]
    efeitos = transicoes_e_efeitos(clipes, segs, graficos, formato)
    props = {
        "duracaoSegundos": round(duracao + 0.6, 2),
        "narracao": f"projetos/{slug}/narracao.mp3",
        "musica": f"musica/{random.choice(musicas).name}" if musicas else None,
        "tituloTela": roteiro.get("tituloTela", ""),
        "marca": canal_cfg.carregar()["nome"].upper(),
        "capa": f"projetos/{slug}/capa.jpg" if com_thumbnail else None,
        "clipes": clipes,
        "palavras": [p for s in segs for p in s["palavras"]],
        # trechos da fala com tempo: usados para dublar em outras línguas (pipeline/traduzir.py)
        "segmentos": [{"inicio": round(s["inicio"], 3), "duracao": round(s["duracao"], 3), "texto": s["texto"],
                       "palavras": len(s["palavras"])} for s in segs],
        "formato": formato,
        "graficos": graficos,
        # transições ficam em cada clipe ("transicao"); aqui os sons (whoosh/pop) com o tempo de cada um
        "efeitos": efeitos,
        "duracaoTransicao": DURACAO_TRANSICAO.get(formato, 0.5),
        "idioma": canal_cfg.carregar().get("idioma", canal_cfg.IDIOMA_PADRAO),
        "capitulos": caps,
    }
    arq_props = pasta_pub / "props.json"
    arq_props.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")

    composicao = "Longo" if formato == "longo" else "Short"
    log(f"Renderizando vídeo {composicao} ({duracao / 60:.1f} min; pode demorar)...")
    npx("remotion", "render", "src/index.ts", composicao,
        str(pasta_saida / "video.mp4"), f"--props={arq_props}")
    if com_thumbnail:
        log("Gerando thumbnail...")
        npx("remotion", "still", "src/index.ts", "Thumbnail",
            str(pasta_saida / "thumbnail.png"), f"--props={arq_props}", "--frame=0")

    escrever_publicacao(roteiro, props, pasta_saida)
    registrar_historico(roteiro)
    # legenda .srt + título/descrição/áudio nas outras línguas (falha aqui não estraga o vídeo)
    try:
        traduzir = importlib.util.spec_from_file_location("traduzir", RAIZ / "pipeline" / "traduzir.py")
        mod_traduzir = importlib.util.module_from_spec(traduzir)
        traduzir.loader.exec_module(mod_traduzir)
        mod_traduzir.main(slug, com_traducao=os.environ.get("TRADUZIR", "1") != "0")
    except Exception as e:  # noqa: BLE001
        log(f"Aviso: não consegui gerar legendas/traduções ({e}). O vídeo está pronto mesmo assim.")
    if not manter_clipes:
        apagados = sum(a.stat().st_size for a in pasta_pub.glob("clipe_*.mp4"))
        for a in pasta_pub.glob("clipe_*.mp4"):
            a.unlink()
        log(f"Clipes baixados apagados ({apagados / 1e6:.0f} MB liberados)")
    log(f"Pronto! Pasta: saida/{slug}")

    if formato == "longo" and gerar_shorts:
        for cap in capitulos:
            if cap.get("short"):
                arq = criar_roteiro_short(roteiro, cap)
                main(arq, manter_clipes=manter_clipes, gerar_shorts=False)


TRANSICOES = ("wipe", "deslize", "iris", "zoom")  # src/Transicao.tsx
DURACAO_TRANSICAO = {"short": 0.4, "longo": 0.6}  # segundos


def transicoes_e_efeitos(clipes, segs, graficos, formato):
    """Marca a transição de cada clipe que começa um trecho novo da fala (nunca a mesma duas vezes
    seguidas; dentro do mesmo trecho o corte continua seco) e monta a lista de efeitos sonoros:
    um pop quando aparece um número/gráfico (e um whoosh por transição, se WHOOSH=1). Devolve os efeitos."""
    try:
        sons = _carregar_modulo("efeitos").arquivos()
    except Exception as e:  # sem numpy/scipy ou erro ao gravar: segue sem efeitos
        log(f"  (efeitos sonoros desligados: {e})")
        sons = None
    inicios = [s["inicio"] for s in segs]
    dur = DURACAO_TRANSICAO.get(formato, 0.5)
    anterior, efeitos = None, []
    for i, c in enumerate(clipes):
        if i == 0 or c["arquivo"] == clipes[i - 1]["arquivo"]:
            continue
        if not any(abs(c["inicio"] - x) < 0.05 for x in inicios):
            continue
        tipo = random.choice([t for t in TRANSICOES if t != anterior])
        c["transicao"] = anterior = tipo
        if sons and ENV.get("WHOOSH", "0") == "1":  # desligado por padrão (WHOOSH=1 no .env liga)
            # o arquivo do whoosh tem ~0,7 s e o ponto mais forte perto do meio: cai no corte
            efeitos.append({"arquivo": random.choice(sons["whoosh"]), "volume": 0.22 if formato == "short" else 0.16,
                            "inicio": round(max(0.0, c["inicio"] - dur / 2 - 0.38), 3)})
    if sons:
        for g in graficos:
            efeitos.append({"arquivo": sons["pop"], "volume": 0.35, "inicio": round(g["inicio"] + 0.05, 3)})
    return sorted(efeitos, key=lambda e: e["inicio"])


def _carregar_modulo(nome):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "pipeline" / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seg_de_cada_clipe(clipes, segs):
    for c in clipes:
        yield next(s for s in reversed(segs) if s["inicio"] <= c["inicio"] + 0.01)


def criar_roteiro_short(roteiro, cap):
    """Transforma um capítulo do vídeo longo num Short vertical: mesmo texto,
    sem o "Número X" do início, com chamada no fim e clipes verticais próprios."""
    info = cap["short"]
    nome = re.sub(r"^(o|a|os|as)\s+", "", cap["titulo"].lower())   # "O panda" -> "panda"
    slug = f"{roteiro['slug']}-short-{hashtag(nome)}"
    segmentos = [dict(s) for s in cap["segmentos"][1:]]
    segmentos.append({"texto": canal_cfg.carregar()["chamadaFinal"], "busca": [cap["animal"]]})
    pub = roteiro["publicacao"]
    novo = {
        "slug": slug,
        "formato": "short",
        "duracao": "curto",
        "animal": cap["animal"],
        "tituloTela": info.get("tituloTela", ""),
        "origem": roteiro["slug"],
        **({"voz": roteiro["voz"]} if roteiro.get("voz") else {}),
        "segmentos": [{**s, "evitar": s.get("evitar") or cap.get("evitar") or []}
                      for s in segmentos],
        "publicacao": {
            "titulo": info["titulo"],
            "descricao": info["descricao"]
            + "\n\n" + canal_cfg.texto(canal_cfg.carregar(), "videoCompleto", titulo=pub["titulo"]),
            "hashtags": info.get("hashtags", []),
            "fontes": pub.get("fontes", []),
        },
    }
    arq = RAIZ / "roteiros" / f"{slug}.json"
    arq.write_text(json.dumps(novo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return arq


# ---------- 4. Publicação ----------
def montar_hashtags(pub, canal):
    """Ordem: fixas do início + as do vídeo + fixas do fim, sem repetir."""
    lista = canal.get("hashtagsInicio", []) + pub.get("hashtags", pub.get("tags", [])) \
        + canal.get("hashtagsFim", [])
    vistas, final = set(), []
    for h in map(hashtag, lista):
        if h and h not in vistas:
            vistas.add(h)
            final.append(h)
    return final[:30]  # o YouTube ignora todas se passar de 60; 30 é folgado


def tempo(segundos):
    s = int(segundos)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def escrever_publicacao(roteiro, props, pasta):
    pub = roteiro["publicacao"]
    canal = canal_cfg.carregar()
    tags = montar_hashtags(pub, canal)
    com_cerquilha = " ".join(f"#{t}" for t in tags)
    sem_cerquilha = ", ".join(tags)
    fontes = "\n".join(f"- {f}" for f in pub.get("fontes", []))
    creditos = "\n".join(sorted({f"- {c['autor']} ({c['url']})" for c in props["clipes"] if c.get("autor")}))
    aviso = roteiro.get("avisoIA") or canal["avisoIA"]  # vídeo próprio: sem "Imagens: Pexels"
    if any("pixabay.com" in (c.get("url") or "") for c in props["clipes"]) and "Pixabay" not in aviso:
        aviso = aviso.replace("Pexels", "Pexels/Pixabay")
    secao_creditos = ("CRÉDITOS DAS IMAGENS (Pexels/Pixabay, uso gratuito; não é obrigatório citar)\n" + creditos + "\n"
                      if creditos else "")
    bloco_fontes = f"{canal_cfg.texto(canal, 'fontes')}\n{fontes}\n\n" if fontes else ""
    duracao = props["duracaoSegundos"] - 0.6
    eh_longo = roteiro.get("formato") == "longo"
    horarios = "\n".join(canal.get("horarios") or canal_cfg.HORARIOS_PADRAO)

    capitulos = ""
    if props.get("capitulos"):
        linhas = [f"{tempo(c['inicio'])} {'#' + str(c['numero']) + ' ' if c['numero'] else ''}{c['titulo']}"
                  for c in props["capitulos"]]
        capitulos = canal_cfg.texto(canal, "capitulos") + "\n" + "\n".join(linhas) + "\n\n"

    descricao = f"""{pub['descricao'].strip()}

{capitulos}{canal['pergunta']}
{canal['chamada']}

{bloco_fontes}{aviso}

{com_cerquilha}"""

    thumb = ("- Thumbnail: envie o arquivo thumbnail.png desta pasta.\n" if eh_longo else "")
    tiktok = "" if eh_longo else secao_tiktok(roteiro, pub, canal, tags, duracao)
    texto = f"""TÍTULO
{pub['titulo']}

================ DESCRIÇÃO (copie tudo até a próxima linha) ================
{descricao}
=============================================================================

HASHTAGS COM #
{com_cerquilha}

HASHTAGS SEM # (cole no campo "Tags" do YouTube Studio)
{sem_cerquilha}

AO PUBLICAR NO YOUTUBE STUDIO
{'- Em "Conteúdo alterado ou sintético": marque NÃO se o vídeo e a voz forem seus (nada gerado por IA).'
 if roteiro.get("vozPropria") else
 '- Em "Conteúdo alterado ou sintético": marque SIM (a narração é voz sintética).'}
- Público: "Não, não é conteúdo para crianças" (a menos que seja o seu caso).
{thumb}
SUGESTÃO DE DIA E HORÁRIO
{horarios}

DURAÇÃO: {tempo(duracao)}

{tiktok}{secao_creditos}"""
    (pasta / "publicacao.txt").write_text(texto, encoding="utf-8")


def secao_tiktok(roteiro, pub, canal, tags, duracao):
    """Legenda no jeito do TikTok: o título sem as hashtags do YouTube, a pergunta do canal e
    poucas hashtags (lá, 3 a 5 funcionam melhor que 30; #shorts não serve)."""
    titulo = re.sub(r"\s*#\S+", "", pub["titulo"]).strip()
    # 3 do próprio vídeo (o assunto) + 1 geral do canal (o nicho)
    fora = ("shorts", "short", "youtubeshorts")
    do_video = [t for t in map(hashtag, pub.get("hashtags", pub.get("tags", []))) if t and t not in fora]
    do_canal = [t for t in map(hashtag, canal.get("hashtagsFim", []) + canal.get("hashtagsInicio", []))
                if t and t not in fora]
    proprias = list(dict.fromkeys(do_video[:3] + do_canal[:1] + do_video[3:] + do_canal[1:]))[:4]
    hashtags = " ".join(f"#{t}" for t in [*proprias, "fyp"])
    legenda = f"{titulo}\n\n{canal['pergunta']}\n\n{hashtags}"
    if duracao > 60:
        paga = f"- Duração {tempo(duracao)}: passa de 1 minuto, então conta para as Recompensas para criadores."
    else:
        paga = (f"- Duração {tempo(duracao)}: o TikTok só paga (Recompensas para criadores) vídeos com mais "
                "de 1 minuto. Para os temas mais fortes, use a duração \"longo\" do Short.")
    ia = ("" if roteiro.get("vozPropria") else
          '- Em "Mais opções", ative "Conteúdo gerado por IA" (a narração é voz sintética).\n')
    return f"""================ PARA O TIKTOK (legenda: copie até a próxima linha) ================
{legenda}
=============================================================================
- Envie o video.mp4 desta pasta (não um baixado do YouTube: marca d'água de outra rede é menos mostrada).
{paga}
{ia}- Horário: no TikTok o público costuma ser maior à noite (19h às 22h).

"""


def so_publicacao(caminho_roteiro):
    """Refaz só o publicacao.txt, usando o vídeo já gerado."""
    roteiro = json.loads(Path(caminho_roteiro).read_text(encoding="utf-8"))
    slug = roteiro["slug"]
    props = json.loads((RAIZ / "public" / "projetos" / slug / "props.json")
                       .read_text(encoding="utf-8"))
    escrever_publicacao(roteiro, props, RAIZ / "saida" / slug)
    log(f"publicacao.txt atualizado: saida/{slug}")


def registrar_historico(roteiro):
    arq = RAIZ / "historico.json"
    hist = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
    hist = [h for h in hist if h["slug"] != roteiro["slug"]]
    hist.append({"slug": roteiro["slug"], "formato": roteiro.get("formato", "short"),
                 "titulo": roteiro["publicacao"]["titulo"]})
    arq.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit("Uso: python -I pipeline/gerar_video.py roteiros/<arquivo>.json "
                 "[--so-publicacao] [--manter-clipes] [--sem-shorts] [--sem-conferir] [--sem-traducao]")
    if "--sem-conferir" in sys.argv:  # pula a conferência das imagens pelo Claude
        os.environ["CONFERIR_CLIPES"] = "0"
    if "--sem-traducao" in sys.argv:  # só a legenda .srt, sem traduzir para as outras línguas
        os.environ["TRADUZIR"] = "0"
    if "--so-publicacao" in sys.argv:
        so_publicacao(args[0])
    else:
        main(args[0], manter_clipes="--manter-clipes" in sys.argv,
             gerar_shorts="--sem-shorts" not in sys.argv)
