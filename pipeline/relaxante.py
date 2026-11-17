"""Vídeo longo de sons relaxantes (chuva, vento, pássaros...) com imagens de natureza do Pexels.

Uso:
    python -I pipeline/relaxante.py relax/chuva-vento-passaros-12min.json

O roteiro (pasta relax/) diz as partes em ordem: título, som (de pipeline/sons.py), minutos,
volume (LUFS; mais negativo = mais baixo) e o que buscar no Pexels.
O som é sintetizado (pipeline/sons.py); o vídeo é montado com ffmpeg (bem mais rápido que o
Remotion para 10+ minutos). O Remotion faz só a thumbnail.
Resultado em saida/<slug>/: video.mp4, thumbnail.png e publicacao.txt.
"""
import importlib.util
import json
import random
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _modulo(nome):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "pipeline" / f"{nome}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gv = _modulo("gerar_video")
sons = _modulo("sons")
log = gv.log

CRUZ_AUDIO = 8.0  # segundos de transição entre um som e outro
TRECHO = 16.0  # quanto tempo cada clipe fica na tela
TRANSICAO = 2.0  # dissolve entre clipes
CLIPES_POR_PARTE = 9
LARGURA, ALTURA, FPS = 1920, 1080, 30
# crf 23: chuva tem muito detalhe e deixa o arquivo enorme; 23 mantém a qualidade e fica ~metade
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True)


# ---------------------------------------------------------------- som
def montar_audio(partes, pasta):
    arquivos = []
    for i, p in enumerate(partes):
        segundos = p["minutos"] * 60 + (CRUZ_AUDIO if i < len(partes) - 1 else 0)
        log(f"Sintetizando som {i + 1}/{len(partes)}: {p['titulo']} ({segundos / 60:.1f} min)...")
        bruto = pasta / f"som_{i}_bruto.wav"
        sons.gerar(p["som"], segundos, bruto, semente=random.randint(1, 10**6))
        final = pasta / f"som_{i}.wav"
        ff("-i", bruto, "-af", f"loudnorm=I={p.get('volume', -24)}:TP=-3:LRA=11", "-ar", "44100", final)
        bruto.unlink()
        arquivos.append(final)

    log("Juntando os sons com transições suaves...")
    entradas, filtro, ultimo = [], [], "[0:a]"
    for f in arquivos:
        entradas += ["-i", f]
    for i in range(1, len(arquivos)):
        saida = f"[a{i}]"
        filtro.append(f"{ultimo}[{i}:a]acrossfade=d={CRUZ_AUDIO}:c1=tri:c2=tri{saida}")
        ultimo = saida
    total = sum(p["minutos"] * 60 for p in partes)
    filtro.append(f"{ultimo}afade=t=in:d=4,afade=t=out:st={total - 20}:d=20[saida]")
    audio = pasta / "audio.wav"
    ff(*entradas, "-filter_complex", ";".join(filtro), "-map", "[saida]", audio)
    for f in arquivos:
        f.unlink()
    return audio, gv.duracao_audio(audio)


# ---------------------------------------------------------------- imagens
def arquivo_1080(video):
    arqs = [a for a in video["video_files"] if a.get("file_type") == "video/mp4" and a.get("height")]
    arqs.sort(key=lambda a: (a["height"] < 1080, abs(a["height"] - 1080)))
    return arqs[0] if arqs else None


def escolher_clipes(parte, evitar_geral, usados):
    evitar = set(evitar_geral) | set(parte.get("evitar", []))
    achados = []
    for busca in parte["buscas"]:
        if len(achados) >= CLIPES_POR_PARTE * 2:
            break
        for v in gv.buscar_pexels(busca, "landscape", paginas=1) + gv.buscar_pixabay(busca, "landscape"):
            if (v["id"] not in usados and v.get("duration", 0) >= TRECHO + TRANSICAO + 1
                    and gv.relevante(v, parte["exigir"], evitar)):
                usados.add(v["id"])
                achados.append(v)
    # mistura as buscas para não ficar tudo igual em sequência
    random.shuffle(achados)
    return achados[:CLIPES_POR_PARTE]


def baixar_clipes(partes, evitar_geral, pasta):
    usados, por_parte = set(), []
    for i, p in enumerate(partes):
        log(f"Buscando imagens para '{p['titulo']}'...")
        lista = []
        for v in escolher_clipes(p, evitar_geral, usados):
            arq = arquivo_1080(v)
            if arq:
                lista.append({"arquivo": pasta / f"p{i}_{v['id']}.mp4", "link": arq["link"],
                              "duracao": float(v["duration"]), "autor": v["user"]["name"], "url": v["url"]})
        # 4 downloads ao mesmo tempo
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(lambda c: gv.baixar(c["link"], c["arquivo"]), lista))
        if not lista:
            sys.exit(f"Nenhuma imagem encontrada para '{p['titulo']}'. Mude as buscas no roteiro.")
        log(f"  {len(lista)} clipes")
        por_parte.append(lista)
    return por_parte


def montar_video(partes, por_parte, total, pasta):
    """Trechos de TRECHO s com dissolve de TRANSICAO s. Para não pesar na memória,
    cada trecho e cada transição viram arquivos e no fim tudo é emendado sem recodificar."""
    # que parte está tocando em cada momento (troca no meio da transição de áudio)
    limites, t = [], 0.0
    for p in partes:
        t += p["minutos"] * 60
        limites.append(t)

    plano, t, giro = [], 0.0, [0] * len(partes)
    while t < total + 1:
        parte = next((i for i, lim in enumerate(limites) if t < lim), len(partes) - 1)
        lista = por_parte[parte]
        c = lista[giro[parte] % len(lista)]
        rodada = giro[parte] // len(lista)  # se repetir o clipe, usa outro pedaço dele
        giro[parte] += 1
        folga = max(0.0, c["duracao"] - (TRECHO + TRANSICAO) - 0.5)
        inicio = min(folga, rodada * 7.0) if rodada else random.uniform(0, min(folga, 3))
        plano.append((c, inicio))
        t += TRECHO

    log(f"Preparando {len(plano)} trechos de imagem...")
    norm = (f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,crop={LARGURA}:{ALTURA},"
            f"fps={FPS},setsar=1,eq=saturation=0.92:brightness=-0.02,format=yuv420p")
    trechos = []
    for k, (c, ini) in enumerate(plano):
        destino = pasta / f"t{k:03d}.mp4"
        ff("-ss", f"{ini:.2f}", "-t", TRECHO + TRANSICAO, "-i", c["arquivo"], "-an", "-vf", norm, *X264, destino)
        trechos.append(destino)

    log("Montando as transições...")
    pedacos = []
    for k, tr in enumerate(trechos):
        # miolo do trecho (sem o começo, que já entrou na transição anterior, e sem o fim)
        ini = 0 if k == 0 else TRANSICAO
        fim = TRECHO
        miolo = pasta / f"m{k:03d}.mp4"
        ff("-ss", ini, "-to", fim, "-i", tr, *X264, miolo)
        pedacos.append(miolo)
        if k + 1 < len(trechos):
            trans = pasta / f"x{k:03d}.mp4"
            ff("-ss", TRECHO, "-i", tr, "-t", TRANSICAO, "-i", trechos[k + 1],
               "-filter_complex", f"[0:v][1:v]xfade=transition=fade:duration={TRANSICAO}:offset=0[v]",
               "-map", "[v]", *X264, trans)
            pedacos.append(trans)

    lista = pasta / "pedacos.txt"
    lista.write_text("".join(f"file '{p.name}'\n" for p in pedacos), encoding="utf-8")
    video = pasta / "imagem.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lista.name,
                    "-c", "copy", video.name], check=True, cwd=pasta)
    return video, plano


# ---------------------------------------------------------------- textos
def escrever_publicacao(roteiro, partes, total, creditos, pasta):
    pub = roteiro["publicacao"]
    tags = []
    for h in map(gv.hashtag, pub.get("hashtags", [])):
        if h and h not in tags:
            tags.append(h)
    tags = tags[:30]
    com, sem = " ".join(f"#{t}" for t in tags), ", ".join(tags)
    t, capitulos = 0.0, []
    for p in partes:
        capitulos.append(f"{gv.tempo(t)} {p['titulo']}")
        t += p["minutos"] * 60
    canal = gv.canal_cfg.carregar()
    aviso = gv.canal_cfg.texto(canal, "relaxAviso")
    if any("pixabay.com" in c for c in creditos):
        aviso = aviso.replace("Pexels", "Pexels/Pixabay")
    texto = f"""TÍTULO
{pub['titulo']}

================ DESCRIÇÃO (copie tudo até a próxima linha) ================
{pub['descricao'].strip()}

{gv.canal_cfg.texto(canal, "capitulos")}
{chr(10).join(capitulos)}

{gv.canal_cfg.texto(canal, "relaxPergunta")}
{canal['chamada']}

{aviso}

{com}
=============================================================================

HASHTAGS COM #
{com}

HASHTAGS SEM # (cole no campo "Tags" do YouTube Studio)
{sem}

AO PUBLICAR NO YOUTUBE STUDIO
- "Conteúdo alterado ou sintético": não é obrigatório para sons de ambiente; marcar SIM também não prejudica.
- Público: "Não, não é conteúdo para crianças".
- Thumbnail: envie o arquivo thumbnail.png desta pasta.
- Dica: crie a playlist "Sons para dormir" e coloque este vídeo nela.

SUGESTÃO DE DIA E HORÁRIO (no fuso do seu público)
Vídeos para dormir são procurados à noite: publique entre 19h e 20h,
de preferência de domingo a quinta (noites antes de dia de trabalho/escola).

DURAÇÃO: {gv.tempo(total)}

CRÉDITOS DAS IMAGENS (Pexels/Pixabay, uso gratuito; não é obrigatório citar)
{chr(10).join(sorted(creditos))}
"""
    (pasta / "publicacao.txt").write_text(texto, encoding="utf-8")


def main(caminho):
    roteiro = json.loads(Path(caminho).read_text(encoding="utf-8"))
    slug, partes = roteiro["slug"], roteiro["partes"]
    trabalho = RAIZ / "trabalho" / slug
    if trabalho.exists():
        shutil.rmtree(trabalho)
    trabalho.mkdir(parents=True)
    pasta_saida = RAIZ / "saida" / slug
    pasta_saida.mkdir(parents=True, exist_ok=True)
    log(f"=== {slug} (relaxante) ===")

    audio, total = montar_audio(partes, trabalho)
    por_parte = baixar_clipes(partes, roteiro.get("evitar", []), trabalho)
    imagem, plano = montar_video(partes, por_parte, total, trabalho)

    log("Juntando imagem e som...")
    ff("-i", imagem, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
       "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", "-movflags", "+faststart",
       pasta_saida / "video.mp4")

    log("Gerando thumbnail...")
    pub_proj = RAIZ / "public" / "projetos" / slug
    pub_proj.mkdir(parents=True, exist_ok=True)
    capa = por_parte[roteiro.get("capaParte", 0)][0]
    ff("-ss", min(5, capa["duracao"] / 2), "-i", capa["arquivo"], "-frames:v", "1", "-q:v", "2",
       pub_proj / "capa.jpg")
    props = {"duracaoSegundos": 1, "narracao": "", "musica": None, "tituloTela": roteiro["tituloTela"],
             "marca": gv.canal_cfg.carregar()["nome"].upper(),
             "capa": f"projetos/{slug}/capa.jpg", "clipes": [], "palavras": []}
    arq_props = pub_proj / "props.json"
    arq_props.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    gv.npx("remotion", "still", "src/index.ts", "Thumbnail", str(pasta_saida / "thumbnail.png"),
           f"--props={arq_props}", "--frame=0")

    creditos = {f"- {c['autor']} ({c['url']})" for c, _ in plano}
    escrever_publicacao(roteiro, partes, total, creditos, pasta_saida)
    gv.registrar_historico({"slug": slug, "formato": "longo", "publicacao": roteiro["publicacao"]})
    (pasta_saida / "info.json").write_text(json.dumps({"formato": "longo", "origem": "relaxante"}),
                                           encoding="utf-8")
    shutil.rmtree(trabalho)  # clipes e trechos temporários
    log(f"Pronto! Pasta: saida/{slug}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python -I pipeline/relaxante.py relax/<arquivo>.json")
    main(sys.argv[1])
