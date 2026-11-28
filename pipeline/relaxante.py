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
import math
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
# chuva tem muito detalhe e deixa o arquivo enorme (crf 23: ~1 GB a cada 30 min). crf 30 com preset
# "medium" fica bem menor; o YouTube recomprime tudo de qualquer jeito, então a diferença não aparece lá.
# (O tempo de codificação não cresce com a duração: os trechos são feitos uma vez e repetidos.)
X264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "30", "-pix_fmt", "yuv420p", "-r", str(FPS)]


# Cada som disponível (pipeline/sons.py) com volume e as imagens que combinam com ele.
# O painel (opção "Sons relaxantes") monta o roteiro a partir daqui.
PRESETS = {
    "chuva_fraca": {"nome": "Chuva fraca", "volume": -27,
                    "buscas": ["light rain leaves", "rain drops on leaves", "drizzle nature", "raindrops puddle",
                               "rain on plants", "rain forest"],
                    "exigir": ["rain", "raindrop", "raindrops", "drizzle", "drops", "droplets"]},
    "chuva_media": {"nome": "Chuva", "volume": -22,
                    "buscas": ["rain forest", "rain falling nature", "rain on window", "rain lake",
                               "rainy day trees", "rain on leaves"],
                    "exigir": ["rain", "rainy", "raindrop", "raindrops"]},
    "vento_passaros": {"nome": "Vento e pássaros", "volume": -24,
                       "buscas": ["wind grass", "trees wind", "meadow wind", "forest morning", "bird on branch",
                                  "wheat field wind"],
                       "exigir": ["wind", "windy", "grass", "meadow", "tree", "trees", "forest", "bird", "birds",
                                  "field", "wheat"],
                       "evitar": ["rain", "rainy", "snow"]},
}
EVITAR = ["car", "cars", "traffic", "taxi", "umbrella", "road", "highway", "storm", "thunder", "lightning",
          "flood", "bus", "train", "fire", "court", "tennis", "parking", "asphalt", "sidewalk", "pavement",
          "basketball", "stadium"]


def montar_roteiro(slug, lista_sons, minutos, textos):
    """Roteiro de vídeo relaxante: os sons escolhidos em ordem, dividindo o tempo igualmente.
    textos: tituloTela, titulos (um por som, na língua do canal) e publicacao."""
    base, sobra = divmod(int(minutos), len(lista_sons))
    titulos = textos.get("titulos") or []
    partes = []
    for i, som in enumerate(lista_sons):
        p = PRESETS[som]
        partes.append({"titulo": str(titulos[i]) if i < len(titulos) and titulos[i] else p["nome"],
                       "som": som, "minutos": base + (1 if i < sobra else 0), "volume": p["volume"],
                       "buscas": p["buscas"], "exigir": p["exigir"], **({"evitar": p["evitar"]} if "evitar" in p else {})})
    return {"slug": slug, "tituloTela": textos.get("tituloTela") or partes[0]["titulo"].upper(),
            "capaParte": 0, "partes": partes, "evitar": EVITAR, "publicacao": textos["publicacao"]}


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True)


# ---------------------------------------------------------------- som
BLOCO_SOM = 6 * 60  # cada som é sintetizado com 6 min e repetido sem emenda (vídeos de horas sem gastar memória)
LACO = 5.0  # segundos de mistura entre o fim e o começo do bloco


def bloco_em_laco(origem, destino, segundos):
    """Transforma um som de (segundos + LACO) num bloco de `segundos` que pode tocar em repetição
    sem emenda: o começo é misturado com o que viria depois do fim."""
    taxa, x = sons.wavfile.read(str(origem))
    x = x.astype(sons.np.float32) / 32767
    n, f = int(segundos * taxa), int(LACO * taxa)
    laco = x[:n].copy()
    r = sons.np.linspace(0, 1, f, dtype=sons.np.float32)[:, None]
    # potência constante (ruído de chuva/vento não "afunda" no meio da mistura)
    laco[:f] = x[n:n + f] * sons.np.sqrt(1 - r) + x[:f] * sons.np.sqrt(r)
    sons.salvar_wav(laco, str(destino))


def montar_audio(partes, pasta):
    blocos, duracoes = [], []
    for i, p in enumerate(partes):
        segundos = p["minutos"] * 60 + (CRUZ_AUDIO if i < len(partes) - 1 else 0)
        base = min(segundos, BLOCO_SOM)
        log(f"Sintetizando som {i + 1}/{len(partes)}: {p['titulo']} ({segundos / 60:.0f} min)...")
        bruto = pasta / f"som_{i}_bruto.wav"
        sons.gerar(p["som"], base + LACO, bruto, semente=random.randint(1, 10**6))
        laco = pasta / f"som_{i}_laco.wav"
        bloco_em_laco(bruto, laco, base)
        final = pasta / f"som_{i}.wav"
        ff("-i", laco, "-af", f"loudnorm=I={p.get('volume', -24)}:TP=-3:LRA=11", "-ar", "44100", final)
        bruto.unlink()
        laco.unlink()
        blocos.append(final)
        duracoes.append(segundos)

    log("Juntando os sons com transições suaves...")
    entradas, filtro = [], []
    for i, (f, d) in enumerate(zip(blocos, duracoes)):
        entradas += ["-stream_loop", "-1", "-i", f]
        filtro.append(f"[{i}:a]atrim=0:{d:.2f},asetpts=PTS-STARTPTS[s{i}]")
    ultimo = "[s0]"
    for i in range(1, len(blocos)):
        filtro.append(f"{ultimo}[s{i}]acrossfade=d={CRUZ_AUDIO}:c1=tri:c2=tri[a{i}]")
        ultimo = f"[a{i}]"
    total = sum(p["minutos"] * 60 for p in partes)
    filtro.append(f"{ultimo}afade=t=in:d=4,afade=t=out:st={total - 20}:d=20[saida]")
    audio = pasta / "audio.m4a"  # comprimido: 3 h em WAV passariam de 1,9 GB
    ff(*entradas, "-filter_complex", ";".join(filtro), "-map", "[saida]", "-c:a", "aac", "-b:a", "192k", audio)
    for f in blocos:
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
        # 4 downloads ao mesmo tempo; um clipe que não baixa é deixado de fora (não para o vídeo)
        def tentar(c):
            try:
                gv.baixar(c["link"], c["arquivo"])
                return c
            except Exception as e:  # noqa: BLE001
                log(f"  clipe pulado (não baixou: {e.__class__.__name__})")
                return None
        with ThreadPoolExecutor(4) as ex:
            lista = [c for c in ex.map(tentar, lista) if c]
        if not lista:
            sys.exit(f"Nenhuma imagem encontrada para '{p['titulo']}'. Mude as buscas no roteiro.")
        log(f"  {len(lista)} clipes")
        por_parte.append(lista)
    return por_parte


def montar_video(partes, por_parte, total, pasta):
    """Trechos de TRECHO s com dissolve de TRANSICAO s. Cada parte tem um ciclo de trechos (cada clipe
    aparece até 2 vezes, em pedaços diferentes) que se repete até cobrir a duração: um vídeo de 3 h
    prepara só algumas dezenas de arquivos, e no fim tudo é emendado sem recodificar."""
    sequencia, ciclos = [], []
    for i, p in enumerate(partes):
        lista = por_parte[i]
        unidades = math.ceil(p["minutos"] * 60 / TRECHO) + (1 if i == len(partes) - 1 else 0)
        ciclo = []
        for k in range(min(unidades, 2 * len(lista))):
            c = lista[k % len(lista)]
            rodada = k // len(lista)  # na 2ª volta, usa outro pedaço do mesmo clipe
            folga = max(0.0, c["duracao"] - (TRECHO + TRANSICAO) - 0.5)
            inicio = min(folga, 7.0) if rodada else random.uniform(0, min(folga, 3))
            ciclo.append((c, inicio))
        ciclos.append(ciclo)
        sequencia += [(i, k % len(ciclo)) for k in range(unidades)]

    unicos = [(i, k) for i, ciclo in enumerate(ciclos) for k in range(len(ciclo))]
    log(f"Preparando {len(unicos)} trechos de imagem...")
    norm = (f"scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,crop={LARGURA}:{ALTURA},"
            f"fps={FPS},setsar=1,eq=saturation=0.92:brightness=-0.02,format=yuv420p")
    trechos, miolos = {}, {}
    for i, k in unicos:
        c, ini = ciclos[i][k]
        destino = pasta / f"t{i}_{k:03d}.mp4"
        ff("-ss", f"{ini:.2f}", "-t", TRECHO + TRANSICAO, "-i", c["arquivo"], "-an", "-vf", norm, *X264, destino)
        trechos[(i, k)] = destino
        # miolo: sem o começo (que entra na transição anterior) e sem o fim (que entra na próxima)
        miolo = pasta / f"m{i}_{k:03d}.mp4"
        ff("-ss", TRANSICAO, "-to", TRECHO, "-i", destino, *X264, miolo)
        miolos[(i, k)] = miolo

    log("Montando as transições...")
    transicoes, pedacos = {}, []
    for j, atual in enumerate(sequencia):
        pedacos.append(miolos[atual])
        if j + 1 == len(sequencia):
            break
        prox = sequencia[j + 1]
        if (atual, prox) not in transicoes:
            trans = pasta / f"x{len(transicoes):03d}.mp4"
            ff("-ss", TRECHO, "-i", trechos[atual], "-t", TRANSICAO, "-i", trechos[prox],
               "-filter_complex", f"[0:v][1:v]xfade=transition=fade:duration={TRANSICAO}:offset=0[v]",
               "-map", "[v]", *X264, trans)
            transicoes[(atual, prox)] = trans
        pedacos.append(transicoes[(atual, prox)])
    plano = [ciclos[i][k] for i, k in unicos]

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
