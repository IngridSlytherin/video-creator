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
import importlib.util
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import edge_tts
import requests

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
    # no longo, só horizontal (vertical recortado ficaria horrível) e menos downloads:
    # cada clipe baixado é reaproveitado em mais de um trecho do mesmo animal.
    "longo": {"orientacoes": ("landscape",), "seg_por_clipe": 4.5,
              "novos_por_segmento": 3},
}



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
                "evitar": seg.get("evitar") or cap.get("evitar") or [],
            })
    return capitulos, segs


# ---------- 1. Narração ----------
def voz_do_canal():
    """Voz da língua do canal (dados/canal.json, campo "voz"); o .env (VOZ) só vale se o canal não tiver."""
    canal = canal_cfg.carregar(obrigatorio=False) or {}
    return canal.get("voz") or ENV.get("VOZ") or canal_cfg.idioma(canal)["voz"]


async def narrar_segmento(texto, destino: Path, velocidade):
    """Gera mp3 e devolve a lista de palavras com tempo (ms)."""
    com = edge_tts.Communicate(
        texto,
        voice=voz_do_canal(),
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


def gerar_narracao(segs, pasta: Path, velocidade):
    log(f"Gerando narração ({len(segs)} trechos)...")
    lista_ffmpeg, cursor = [], 0.0
    for i, seg in enumerate(segs):
        mp3 = pasta / f"voz_{i:03d}.mp3"
        palavras = asyncio.run(narrar_segmento(seg["texto"], mp3, velocidade))
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
]
# Palavras curtas que só bloqueiam quando aparecem inteiras (evita "man" barrar "mangrove").
PROIBIDAS_EXATAS = {"man", "men", "hand", "hands", "eat", "raw", "3d", "pet", "art"}


def relevante(video, exigir, evitar=()):
    """A busca do Pexels é solta: só aceita o clipe se o endereço da página
    (que descreve o vídeo, ex.: /video/octopus-swimming-123/) citar o termo."""
    palavras = [p for p in re.split(r"[^a-z0-9]+", video.get("url", "").lower()) if p]
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
    arquivos.sort(key=lambda a: (min(a["width"], a["height"]) < 1080,
                                 abs(min(a["width"], a["height"]) - alvo)))
    return arquivos[0] if arquivos else None


def baixar(url, destino: Path):
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for bloco in r.iter_content(1 << 16):
                f.write(bloco)


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
            vistos, filtrados = set(), []
            for v in lista:
                if (v["id"] not in usados and v["id"] not in vistos
                        and relevante(v, seg["exigir"], seg["evitar"])
                        and v.get("duration", 0) >= dur_clipe + 0.5):
                    vistos.add(v["id"])
                    filtrados.append(v)
            random.Random(f"{slug}{idx}{orient}").shuffle(filtrados)
            pool += filtrados

        limite = cfg["novos_por_segmento"] or qtd
        novos = 0
        for k in range(qtd):
            inicio = seg["inicio"] + k * dur_clipe
            if pool and novos < limite:
                video = pool.pop(0)
                usados.add(video["id"])
                destino = pasta / f"clipe_{n_arquivos:03d}.mp4"
                baixar(melhor_arquivo(video)["link"], destino)
                n_arquivos += 1
                novos += 1
                meus.append({"arquivo": f"projetos/{slug}/{destino.name}",
                             "duracaoTotal": float(video.get("duration", 0)),
                             "usado": 0.0,
                             "autor": video.get("user", {}).get("name", ""),
                             "url": video.get("url", "")})
                base = meus[-1]
            else:
                # Reaproveita um clipe já baixado do mesmo animal, mostrando outro trecho.
                if not meus:
                    raise RuntimeError(f"Nenhum clipe encontrado para: {seg['busca']}")
                livres = [b for b in meus if b["duracaoTotal"] - b["usado"] >= dur_clipe]
                base = max(livres, key=lambda b: b["duracaoTotal"] - b["usado"]) if livres \
                    else min(meus, key=lambda b: b["usado"])
            trecho = base["usado"] % max(0.1, base["duracaoTotal"] - dur_clipe)
            base["usado"] = trecho + dur_clipe
            clipes.append({"arquivo": base["arquivo"], "inicio": inicio, "duracao": dur_clipe,
                           "inicioNoClipe": trecho, "autor": base["autor"], "url": base["url"]})
        log(f"  trecho {idx + 1}/{len(segs)}: {qtd} cortes, {novos} clipes novos")
    log(f"{n_arquivos} clipes baixados para {len(clipes)} cortes")
    return clipes


# ---------- 3. Render ----------
def npx(*args):
    cmd = ["npx.cmd" if os.name == "nt" else "npx", *args]
    subprocess.run(cmd, check=True, cwd=RAIZ)


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
    duracao = gerar_narracao(segs, pasta_pub, velocidade)
    faixa = roteiro.get("duracao", "padrao")
    if faixa in DURACOES:
        minimo, maximo = DURACOES[faixa]
        if not minimo <= duracao <= maximo:
            log(f"ATENÇÃO: narração com {duracao:.0f} s, fora da faixa '{faixa}' "
                f"({minimo}-{maximo} s). Ajuste o tamanho do roteiro.")
    clipes = baixar_clipes(segs, formato, pasta_pub, slug)
    caps = info_capitulos(roteiro, capitulos, segs)

    # Thumbnail só no vídeo longo: no Short o YouTube não deixa escolher a capa.
    com_thumbnail = formato != "short"
    if com_thumbnail:
        ci = roteiro.get("capaCapitulo", 0)
        clipe_capa = next((c for c, s in zip(clipes, _seg_de_cada_clipe(clipes, segs))
                           if s["capitulo"] == ci), clipes[0])
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-ss", str(clipe_capa["inicioNoClipe"] + 1.0),
                        "-i", str(RAIZ / "public" / clipe_capa["arquivo"]),
                        "-frames:v", "1", "-q:v", "2", str(pasta_pub / "capa.jpg")], check=True)

    musicas = sorted((RAIZ / "public" / "musica").glob("*.mp3"))
    props = {
        "duracaoSegundos": round(duracao + 0.6, 2),
        "narracao": f"projetos/{slug}/narracao.mp3",
        "musica": f"musica/{random.choice(musicas).name}" if musicas else None,
        "tituloTela": roteiro.get("tituloTela", ""),
        "marca": canal_cfg.carregar()["nome"].upper(),
        "capa": f"projetos/{slug}/capa.jpg" if com_thumbnail else None,
        "clipes": clipes,
        "palavras": [p for s in segs for p in s["palavras"]],
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
    secao_creditos = ("CRÉDITOS DAS IMAGENS (Pexels, uso gratuito; não é obrigatório citar)\n" + creditos + "\n"
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
- Em "Conteúdo alterado ou sintético": marque SIM (a narração é voz sintética).
- Público: "Não, não é conteúdo para crianças" (a menos que seja o seu caso).
{thumb}
SUGESTÃO DE DIA E HORÁRIO
{horarios}

DURAÇÃO: {tempo(duracao)}

{secao_creditos}"""
    (pasta / "publicacao.txt").write_text(texto, encoding="utf-8")


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
                 "[--so-publicacao] [--manter-clipes] [--sem-shorts]")
    if "--so-publicacao" in sys.argv:
        so_publicacao(args[0])
    else:
        main(args[0], manter_clipes="--manter-clipes" in sys.argv,
             gerar_shorts="--sem-shorts" not in sys.argv)
