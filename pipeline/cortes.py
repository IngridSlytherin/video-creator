"""Cortes: transforma um vídeo longo seu em Shorts.

1. analisar: transcreve a fala (Whisper, no seu computador) e pede ao Claude os melhores momentos.
2. montar: corta os trechos escolhidos, põe na vertical (vídeo no meio, fundo desfocado),
   com título e legenda animada, e entrega em saida/<slug>-corte-N/ (aparece em Vídeos prontos).

Uso (o painel chama sozinho):
    python -I pipeline/cortes.py analisar <slug>
    python -I pipeline/cortes.py montar <slug>      (lê trabalho/cortes/<slug>/montar.json)

O vídeo enviado fica em trabalho/cortes/<slug>/ (fora de public/, que o Remotion copia a cada render).
Modelo do Whisper: WHISPER_MODELO no .env (padrão "small"; "medium" erra menos e é ~2x mais lento).
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gerar_video", RAIZ / "pipeline" / "gerar_video.py")
gv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gv)  # também força IPv4 (o Whisper baixa o modelo na primeira vez)
log = gv.log
claude_cli = gv.claude_cli
canal_cfg = gv.canal_cfg

TRABALHO = RAIZ / "trabalho" / "cortes"
MIN_S, MAX_S = 20, 75


def etapa(n, total, texto):
    print(f"[etapa {n}/{total}] {texto}", flush=True)


def pasta_de(slug):
    return TRABALHO / slug


def info_video(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", str(arq)],
                       capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    return int(d["streams"][0]["width"]), int(d["streams"][0]["height"]), float(d["format"]["duration"])


def mmss(s):
    return f"{int(s) // 60:02d}:{s % 60:04.1f}"


# ------------------------------------------------------------------ 1. analisar
def transcrever(video, idioma):
    """Fala -> lista de frases com o tempo de cada palavra."""
    import numpy as np
    from faster_whisper import WhisperModel

    nome = gv.ENV.get("WHISPER_MODELO", "small")
    try:  # já baixado: não consulta a internet (em algumas redes isso leva minutos)
        modelo = WhisperModel(nome, device="cpu", compute_type="int8", local_files_only=True)
    except Exception:  # noqa: BLE001 - primeira vez: baixa o modelo (~500 MB no "small")
        log(f"  baixando o modelo de transcrição '{nome}' (só na primeira vez; pode levar alguns minutos)...")
        modelo = WhisperModel(nome, device="cpu", compute_type="int8")
    bruto = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-f", "s16le", "-ac", "1",
                            "-ar", "16000", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(bruto, np.int16).astype(np.float32) / 32768
    if not len(audio):
        raise SystemExit("Esse vídeo não tem áudio: os cortes são escolhidos pela fala.")
    trechos, info = modelo.transcribe(audio, language=idioma.split("-")[0], word_timestamps=True,
                                      vad_filter=True)
    frases, ultimo = [], -10
    for t in trechos:
        frases.append({"inicio": round(t.start, 2), "fim": round(t.end, 2), "texto": t.text.strip(),
                       "palavras": [{"t": w.word.strip(), "i": round(w.start, 2), "f": round(w.end, 2)}
                                    for w in (t.words or []) if w.word.strip()]})
        pct = int(100 * t.end / max(1, info.duration))
        if pct >= ultimo + 10:
            ultimo = pct
            log(f"  transcrevendo... {pct}%")
    return frases


PROMPT = """{canal}

Abaixo está a transcrição (feita por computador; pode ter palavras erradas) de um vídeo longo do canal,
com o tempo de cada frase em segundos. Escolha de 3 a 5 trechos que funcionem SOZINHOS como Shorts.

Leia antes, se existirem: dados/aprendizados.md (siga as "Regras do canal") e dados/videos-do-canal.json
(não repita títulos que já existem).

Regras para cada trecho:
- Entre {minimo} e {maximo} segundos (o ideal é 30 a 60). Começa no início de uma frase e termina no fim de uma.
- Começa com algo que prende logo (pergunta, fato surpreendente, "você sabia"), nunca com "como eu disse",
  "então", "e aí" ou algo que dependa do resto do vídeo.
- Conta uma ideia completa: quem assiste só esse pedaço entende e fica satisfeito.
- Trechos diferentes entre si (não repita o mesmo assunto) e sem sobrepor tempos.
- Se o vídeo tiver poucos momentos bons, escolha menos (no mínimo 1).

Para cada trecho, na língua do vídeo ({lingua}):
- "titulo": título do YouTube (até 70 caracteres, 1 ou 2 palavras em MAIÚSCULA, formatos variados,
  no máximo 1 começando com "Por que"); termine com " #shorts".
- "tela": frase curta que aparece em cima do vídeo (até 40 caracteres, ex.: "O POLVO TEM 3 CORAÇÕES?").
- "descricao": 1 ou 2 frases. "hashtags": 8 a 12, sem #, minúsculas, sem acento.
- "porque": por que esse trecho deve funcionar (em português, 1 frase).

Transcrição:
{transcricao}

Responda SOMENTE com JSON: {{"cortes": [{{"inicio": 12.3, "fim": 58.0, "titulo": "...", "tela": "...",
"descricao": "...", "hashtags": ["..."], "porque": "..."}}]}}
"""


def por_frase(frases):
    """Uma linha por frase (pela pontuação). O Whisper às vezes junta o fim de uma frase com o começo
    da outra num trecho só, e aí o Claude não consegue dizer onde exatamente começar o corte."""
    linhas, atual = [], []
    for p in (p for f in frases for p in f["palavras"]):
        atual.append(p)
        if re.search(r"[.!?…]$", p["t"]) or len(atual) >= 40:
            linhas.append((atual[0]["i"], atual[-1]["f"], " ".join(x["t"] for x in atual)))
            atual = []
    if atual:
        linhas.append((atual[0]["i"], atual[-1]["f"], " ".join(x["t"] for x in atual)))
    return linhas


def ajustar(c, palavras, duracao):
    """Encaixa início e fim nas palavras mais próximas (não corta no meio de uma palavra)."""
    ini, fim = float(c["inicio"]), float(c["fim"])
    if palavras:
        ini = min(palavras, key=lambda p: abs(p["i"] - ini))["i"]
        fim = min(palavras, key=lambda p: abs(p["f"] - fim))["f"]
    ini, fim = max(0.0, ini - 0.15), min(duracao, fim + 0.35)
    return round(ini, 2), round(fim, 2)


def analisar(slug):
    pasta = pasta_de(slug)
    pasta.mkdir(parents=True, exist_ok=True)
    etapa(1, 3, "Preparando o vídeo")
    enviado = RAIZ / "public" / "projetos" / slug
    for arq in enviado.glob("original.*"):  # tira de public/ (o Remotion copia public/ inteira)
        shutil.move(str(arq), pasta / arq.name)
    shutil.rmtree(enviado, ignore_errors=True)
    video = next(pasta.glob("original.*"), None)
    if not video:
        raise SystemExit("Vídeo enviado não encontrado; envie de novo.")
    largura, altura, duracao = info_video(video)
    log(f"Vídeo {largura}x{altura}, {duracao / 60:.1f} min")
    if duracao < MIN_S + 5:
        raise SystemExit(f"O vídeo tem só {duracao:.0f} s: os cortes são para vídeos longos.")

    canal = canal_cfg.carregar()
    idioma = canal.get("idioma", canal_cfg.IDIOMA_PADRAO)
    arq_transcricao = pasta / "transcricao.json"
    if arq_transcricao.exists():
        frases = json.loads(arq_transcricao.read_text(encoding="utf-8"))
    else:
        etapa(2, 3, "Transcrevendo a fala")
        log(f"Transcrevendo {duracao / 60:.0f} min de vídeo (leva mais ou menos 1/3 do tempo do vídeo)...")
        frases = transcrever(video, idioma)
        arq_transcricao.write_text(json.dumps(frases, ensure_ascii=False), encoding="utf-8")
    if sum(len(f["palavras"]) for f in frases) < 60:
        raise SystemExit("Quase não tem fala nesse vídeo: os cortes são escolhidos pelo que é dito.")

    etapa(3, 3, "Escolhendo os melhores momentos")
    texto = "\n".join(f"[{a:.1f}-{b:.1f}] {t}" for a, b, t in por_frase(frases))
    lng = canal_cfg.idioma(canal)
    prompt = PROMPT.format(canal=f'Canal de YouTube "{canal["nome"]}", categoria "{canal["categoria"]}".',
                           minimo=MIN_S, maximo=MAX_S, lingua=lng["lingua"], transcricao=texto[:150000])
    resposta = None
    for _ in range(2):
        resposta = claude_cli.perguntar(prompt, ferramentas=("Read",), timeout=900)
        if resposta:
            break
    if not resposta:
        raise SystemExit("Não consegui falar com o Claude Code agora; tente de novo em alguns minutos.")
    cortes = claude_cli.extrair_json(resposta).get("cortes") or []
    palavras = [p for f in frases for p in f["palavras"]]
    finais = []
    for c in cortes:
        try:
            ini, fim = ajustar(c, palavras, duracao)
        except (KeyError, TypeError, ValueError):
            continue
        if fim - ini < MIN_S - 5:
            continue
        finais.append({"id": len(finais) + 1, "inicio": ini, "fim": min(fim, ini + MAX_S + 15),
                       "titulo": str(c.get("titulo", ""))[:100], "tela": str(c.get("tela", ""))[:60],
                       "descricao": str(c.get("descricao", ""))[:600],
                       "hashtags": [str(h) for h in (c.get("hashtags") or [])][:15],
                       "porque": str(c.get("porque", ""))[:300]})
    if not finais:
        raise SystemExit("O Claude não achou trechos bons o suficiente nesse vídeo.")
    dados = {"slug": slug, "video": video.name, "largura": largura, "altura": altura,
             "duracao": duracao, "cortes": finais}
    (pasta / "cortes.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in finais:
        log(f"  {c['id']}. {mmss(c['inicio'])}–{mmss(c['fim'])} ({c['fim'] - c['inicio']:.0f} s) {c['titulo']}")
    etapa(3, 3, "Pronto")


# ------------------------------------------------------------------ 2. montar
def montar(slug):
    pasta = pasta_de(slug)
    dados = json.loads((pasta / "cortes.json").read_text(encoding="utf-8"))
    pedido = json.loads((pasta / "montar.json").read_text(encoding="utf-8"))
    frases = json.loads((pasta / "transcricao.json").read_text(encoding="utf-8"))
    palavras = [p for f in frases for p in f["palavras"]]
    video = pasta / dados["video"]
    vertical = dados["altura"] > dados["largura"]
    canal = canal_cfg.carregar()
    por_id = {c["id"]: c for c in dados["cortes"]}

    for k, escolha in enumerate(pedido["cortes"], 1):
        c = {**por_id.get(escolha.get("id"), {}), **escolha}
        ini = max(0.0, float(c["inicio"]))
        fim = min(dados["duracao"], float(c["fim"]))
        if fim - ini < 3:
            log(f"Corte {k} ignorado: tempo inválido.")
            continue
        nome = f"{slug[:40]}-corte-{c.get('id', k)}"
        log(f"=== {nome} (short) ===")
        pasta_pub = RAIZ / "public" / "projetos" / nome
        shutil.rmtree(pasta_pub, ignore_errors=True)
        pasta_pub.mkdir(parents=True)
        log("Cortando o trecho...")
        corte = pasta_pub / "corte.mp4"
        # A tela vertical já sai pronta do ffmpeg (bem mais rápido que desfocar no Remotion):
        # vídeo deitado inteiro no meio e ele mesmo, desfocado e escurecido, ocupando o fundo.
        cobrir = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        quadro = (f"[0:v]{cobrir},setsar=1[v]" if vertical else
                  f"[0:v]split[a][b];[a]{cobrir},scale=270:480,boxblur=12:2,scale=1080:1920,"
                  f"eq=brightness=-0.22:saturation=1.1[fundo];[b]scale=1080:-2,setsar=1[frente];"
                  f"[fundo][frente]overlay=(W-w)/2:(H-h)/2[v]")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.2f}", "-i", str(video), "-t", f"{fim - ini:.2f}",
                        "-filter_complex", quadro,
                        "-map", "[v]", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
                        "-movflags", "+faststart", str(corte)], check=True)
        dur = gv.duracao_audio(corte)
        props = {
            "duracaoSegundos": round(dur, 2),
            "video": f"projetos/{nome}/corte.mp4",
            "vertical": vertical,
            "tituloTela": c.get("tela") or "",
            "marca": canal["nome"].upper(),
            "palavras": [{"texto": p["t"], "inicioMs": round((p["i"] - ini) * 1000),
                          "fimMs": round((p["f"] - ini) * 1000)}
                         for p in palavras if p["i"] >= ini - 0.05 and p["f"] <= fim + 0.05],
            "semLegendas": not pedido.get("legendas", True),
            "clipes": [],
        }
        arq_props = pasta_pub / "props.json"
        arq_props.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
        pasta_saida = RAIZ / "saida" / nome
        pasta_saida.mkdir(parents=True, exist_ok=True)
        log("Renderizando vídeo Corte...")
        gv.npx("remotion", "render", "src/index.ts", "Corte", str(pasta_saida / "video.mp4"), f"--props={arq_props}")
        titulo = c.get("titulo") or c.get("tela") or nome
        roteiro = {"slug": nome, "formato": "short", "vozPropria": True, "avisoIA": " ",
                   "publicacao": {"titulo": titulo if "#shorts" in titulo else titulo + " #shorts",
                                  "descricao": c.get("descricao", ""), "hashtags": c.get("hashtags", []),
                                  "fontes": []}}
        gv.escrever_publicacao(roteiro, {**props, "duracaoSegundos": dur + 0.6}, pasta_saida)
        (pasta_saida / "info.json").write_text(json.dumps({"formato": "short", "origem": "corte"}), encoding="utf-8")
        corte.unlink(missing_ok=True)  # o Remotion copia public/ inteira a cada render
        log(f"Pronto! Pasta: saida/{nome}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3 or sys.argv[1] not in ("analisar", "montar"):
        sys.exit("Uso: python -I pipeline/cortes.py analisar|montar <slug>")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", sys.argv[2]):
        sys.exit("slug inválido")
    {"analisar": analisar, "montar": montar}[sys.argv[1]](sys.argv[2])
