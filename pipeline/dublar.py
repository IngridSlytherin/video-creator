"""Dublar um vídeo próprio: narração com a voz do canal + legenda sobre o vídeo que você enviou.

Uso (o painel chama sozinho):
    python -I pipeline/dublar.py <slug>

Lê public/projetos/<slug>/dublagem.json (texto e opções) e public/projetos/<slug>/original.*
Resultado em saida/<slug>/ (video.mp4 e publicacao.txt), como nos outros vídeos.
"""
import importlib.util
import json
import random
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gerar_video", RAIZ / "pipeline" / "gerar_video.py")
gv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gv)
log = gv.log

VOLUMES = {"sem": 0.0, "baixo": 0.15, "normal": 1.0}


def info_video(arq):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(arq)],
        capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), float(d["format"]["duration"])


def preparar_video(original, destino):
    """Converte para MP4 H.264 a 30 fps: abre em qualquer navegador e no Remotion
    (vídeo de celular costuma vir em HEVC/.mov, que o Remotion pode não ler)."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(original),
         "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(destino)],
        check=True)


def segmentos_do_texto(texto):
    """Cada linha (ou parágrafo) vira um trecho da narração, com uma pausa curta entre eles."""
    linhas = [l.strip() for l in texto.replace("\r", "").split("\n")]
    return [{"texto": l, "primeiroDoCapitulo": False} for l in linhas if l]


def main(slug):
    pasta = RAIZ / "public" / "projetos" / slug
    cfg = json.loads((pasta / "dublagem.json").read_text(encoding="utf-8"))
    original = next((a for a in pasta.glob("original.*")), None)
    if not original:
        sys.exit("Vídeo enviado não encontrado.")
    log(f"=== {slug} (dublagem) ===")

    log("Preparando o seu vídeo...")
    video = pasta / "seu_video.mp4"
    preparar_video(original, video)
    largura, altura, dur_video = info_video(video)
    formato = "short" if altura > largura else "longo"
    log(f"Vídeo {largura}x{altura}, {dur_video:.1f} s -> formato {'Short (vertical)' if formato == 'short' else 'horizontal'}")

    segs = segmentos_do_texto(cfg["texto"])
    if not segs:
        sys.exit("O roteiro está vazio.")
    velocidade = cfg.get("velocidade") or gv.ENV.get("VELOCIDADE_VOZ", "+0%")
    dur_narracao = gv.gerar_narracao(segs, pasta, velocidade)

    if cfg.get("ate") == "narracao" or dur_narracao + 0.6 > dur_video:
        total = dur_narracao + 0.6
    else:
        total = dur_video
    if dur_narracao + 0.6 > dur_video:
        log(f"A narração ({dur_narracao:.0f} s) é maior que o vídeo ({dur_video:.0f} s): o vídeo vai repetir.")

    # Repete o vídeo se a narração for mais longa que ele.
    clipes, inicio = [], 0.0
    while inicio < total - 0.05:
        trecho = min(dur_video, total - inicio)
        clipes.append({"arquivo": f"projetos/{slug}/seu_video.mp4", "inicio": round(inicio, 3),
                       "duracao": round(trecho, 3), "inicioNoClipe": 0})
        inicio += dur_video

    musicas = sorted((RAIZ / "public" / "musica").glob("*.mp3"))
    titulo = cfg.get("titulo") or segs[0]["texto"][:90]
    props = {
        "duracaoSegundos": round(total, 2),
        "narracao": f"projetos/{slug}/narracao.mp3",
        "musica": f"musica/{random.choice(musicas).name}" if musicas and cfg.get("musica") else None,
        "tituloTela": titulo,
        "marca": gv.canal_cfg.carregar()["nome"].upper(),
        "capa": None,
        "clipes": clipes,
        "palavras": [p for s in segs for p in s["palavras"]],
        "capitulos": [],
        "volumeOriginal": VOLUMES.get(cfg.get("somOriginal"), 0.15),
        "semZoom": True,
        "semLegendas": not cfg.get("legendas", True),
    }
    arq_props = pasta / "props.json"
    arq_props.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")

    pasta_saida = RAIZ / "saida" / slug
    pasta_saida.mkdir(parents=True, exist_ok=True)
    composicao = "Short" if formato == "short" else "Longo"
    log(f"Renderizando vídeo {composicao} ({total / 60:.1f} min)...")
    gv.npx("remotion", "render", "src/index.ts", composicao,
           str(pasta_saida / "video.mp4"), f"--props={arq_props}")

    roteiro = {
        "slug": slug,
        "formato": formato,
        "avisoIA": gv.canal_cfg.texto(gv.canal_cfg.carregar(), "avisoDublagem"),
        "publicacao": {
            "titulo": titulo + (" #shorts" if formato == "short" and "#shorts" not in titulo else ""),
            "descricao": cfg.get("descricao") or "",
            "hashtags": cfg.get("hashtags") or [],
            "fontes": [],
        },
    }
    # O Remotion copia a pasta public/ inteira a cada render: não deixar o vídeo enviado acumulando lá.
    for arq in [video, *pasta.glob("original.*")]:
        arq.unlink(missing_ok=True)

    gv.escrever_publicacao(roteiro, props, pasta_saida)
    gv.registrar_historico(roteiro)
    (pasta_saida / "info.json").write_text(
        json.dumps({"formato": formato, "origem": "dublagem"}, ensure_ascii=False), encoding="utf-8")
    log(f"Pronto! Pasta: saida/{slug}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python -I pipeline/dublar.py <slug>")
    main(sys.argv[1])
