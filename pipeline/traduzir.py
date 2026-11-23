"""Legendas (.srt) e versões do vídeo em outras línguas, para enviar no YouTube Studio.

Para cada vídeo gera, em saida/<slug>/:
  - legenda.<língua>.srt     legenda da narração (o YouTube usa na busca e na tradução automática)
  - audio.<língua>.mp3       narração traduzida + música, no mesmo tempo do vídeo
                             (YouTube Studio > Idiomas > Adicionar áudio, onde estiver disponível)
  - traducoes.json           título, descrição e hashtags traduzidos
  e acrescenta a seção "TRADUÇÕES" no publicacao.txt.

Roda sozinho no fim de cada vídeo. Para um vídeo já feito:
    python -I pipeline/traduzir.py <slug>                 (legendas + traduções + áudios)
    python -I pipeline/traduzir.py <slug> --sem-traducao  (só a legenda .srt)

As traduções são feitas pelo Claude Code; sem ele, só sai a legenda na língua do canal.
"""
import asyncio
import importlib.util
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _modulo(nome):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "pipeline" / f"{nome}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


gv = _modulo("gerar_video")
canal_cfg, claude_cli, log = gv.canal_cfg, gv.claude_cli, gv.log
MARCA_SECAO = "TRADUÇÕES (YouTube Studio > Idiomas)"
VOLUME_MUSICA = {"short": 0.08, "longo": 0.06}  # o mesmo do vídeo (src/Short.tsx e src/Longo.tsx)


# ---------------------------------------------------------------- legenda .srt
def _tempo_srt(ms):
    ms = max(0, int(ms))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(palavras, max_palavras=8, max_letras=42):
    """Agrupa as palavras (com tempo, vindas da narração) em linhas de legenda."""
    blocos, atual = [], []
    for i, p in enumerate(palavras):
        atual.append(p)
        prox = palavras[i + 1] if i + 1 < len(palavras) else None
        texto = " ".join(x["texto"] for x in atual)
        if (not prox or len(atual) >= max_palavras or len(texto) >= max_letras
                or prox["inicioMs"] - p["fimMs"] > 300 or re.search(r"[.!?]$", p["texto"])):
            blocos.append(atual)
            atual = []
    linhas = []
    for n, b in enumerate(blocos, 1):
        fim = b[-1]["fimMs"] + 150
        if n < len(blocos):
            fim = min(fim, blocos[n][0]["inicioMs"])
        linhas.append(f"{n}\n{_tempo_srt(b[0]['inicioMs'])} --> {_tempo_srt(fim)}\n"
                      f"{' '.join(x['texto'] for x in b)}\n")
    return "\n".join(linhas)


# ---------------------------------------------------------------- dados do vídeo
def segmentos(props):
    """Trechos da fala com tempo. Vídeos antigos não guardavam: reconstrói pelas palavras."""
    if props.get("segmentos"):
        return props["segmentos"]
    palavras = props.get("palavras", [])
    if not palavras:
        return []
    # corta onde há pausa maior (entre trechos o gerador põe 0,25 s ou mais de silêncio)
    grupos, atual = [], [palavras[0]]
    for a, b in zip(palavras, palavras[1:]):
        if b["inicioMs"] - a["fimMs"] >= 230:
            grupos.append(atual)
            atual = []
        atual.append(b)
    grupos.append(atual)
    segs = []
    for i, g in enumerate(grupos):
        inicio = g[0]["inicioMs"] / 1000
        fim = grupos[i + 1][0]["inicioMs"] / 1000 if i + 1 < len(grupos) else props["duracaoSegundos"]
        segs.append({"inicio": round(inicio, 3), "duracao": round(fim - inicio, 3),
                     "texto": " ".join(p["texto"] for p in g), "palavras": len(g)})
    return segs


def ler_publicacao(pasta):
    """Título e descrição do publicacao.txt (sem as partes fixas do canal)."""
    arq = pasta / "publicacao.txt"
    if not arq.exists():
        return "", ""
    t = arq.read_text(encoding="utf-8")
    titulo = (re.search(r"^TÍTULO\n(.*)\n", t) or [None, ""])[1]
    desc = (re.search(r"=+ DESCRIÇÃO[^\n]*\n(.*?)\n\n", t, re.S) or [None, ""])[1]
    return titulo.strip(), desc.strip()


# ---------------------------------------------------------------- tradução (Claude)
def traduzir_textos(titulo, descricao, hashtags, trechos, linguas, lingua_base):
    nomes = {k: canal_cfg.IDIOMAS[k]["lingua"] for k in linguas}
    entrada = json.dumps({"titulo": titulo, "descricao": descricao, "hashtags": hashtags, "trechos": trechos},
                         ensure_ascii=False, indent=1)
    prompt = f"""Traduza este vídeo do YouTube (escrito em {canal_cfg.IDIOMAS[lingua_base]['lingua']}) para:
{json.dumps(nomes, ensure_ascii=False)}

{entrada}

Regras:
- "trechos" é a narração, dividida em partes: devolva EXATAMENTE {len(trechos)} trechos, na mesma ordem.
  Linguagem falada e natural; cada trecho traduzido precisa caber no mesmo tempo do original, então
  prefira frases curtas (se ficar bem mais longo, resuma sem perder o fato).
- Título no mesmo estilo (1 ou 2 palavras em MAIÚSCULA, emoji se houver, mantenha #shorts se houver).
- Hashtags traduzidas, sem #, minúsculas, sem acento nem espaço.
- Nomes de animais e fatos exatos; não invente nada.

Responda SOMENTE com JSON, uma chave por língua:
{{"en-US": {{"titulo": "...", "descricao": "...", "hashtags": ["..."], "trechos": ["...", "..."]}}, ...}}"""
    resposta = claude_cli.perguntar(prompt, ("Read",), timeout=600)
    if resposta is None:
        return {}
    try:
        dados = claude_cli.extrair_json(resposta)
    except ValueError:
        return {}
    return {k: v for k, v in dados.items() if k in linguas and isinstance(v, dict) and v.get("titulo")}


# ---------------------------------------------------------------- áudio dublado
async def _tts(texto, destino, voz, velocidade):
    return await gv.narrar_segmento(texto, destino, velocidade, voz=voz)


def _soma_velocidade(base, extra):
    """'+8%' + 15 -> '+23%' (o edge-tts aceita a velocidade como porcentagem)."""
    n = int(re.sub(r"[^\d-]", "", base or "0") or 0) + extra
    return f"{'+' if n >= 0 else ''}{n}%"


def dublar_trilha(segs, trechos, lingua, props, formato, destino_mp3, tmp):
    """Narra cada trecho traduzido no lugar do original (acelerando se não couber) e mistura a música."""
    voz = canal_cfg.IDIOMAS[lingua]["voz"]
    base = gv.ENV.get("VELOCIDADE_VOZ", "+0%")
    palavras, entradas, filtros = [], [], []
    for i, (seg, texto) in enumerate(zip(segs, trechos)):
        mp3 = tmp / f"{lingua}_{i:03d}.mp3"
        caber = max(0.6, seg["duracao"] - 0.12)
        p = gv.narrar(texto, mp3, base, voz=voz)
        dur = gv.duracao_audio(mp3)
        if dur > caber:  # não coube: fala mais rápido (até +60%) para não invadir o próximo trecho
            extra = min(60, math.ceil((dur / caber - 1) * 100) + 4)
            p = gv.narrar(texto, mp3, _soma_velocidade(base, extra), voz=voz)
        for w in p:
            w["inicioMs"] += seg["inicio"] * 1000
            w["fimMs"] += seg["inicio"] * 1000
        palavras += p
        entradas += ["-i", str(mp3)]
        ms = int(seg["inicio"] * 1000)
        filtros.append(f"[{i}:a]adelay={ms}|{ms}[t{i}]")
    n = len(segs)
    total = props["duracaoSegundos"]
    mistura = "".join(f"[t{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0:dropout_transition=0[voz]"
    filtros.append(mistura)
    musica = props.get("musica")
    k = n
    saida = "[voz]"
    if musica and (RAIZ / "public" / musica).exists():
        # como no vídeo: a música abaixa quando a voz fala e sobe nas pausas
        entradas += ["-stream_loop", "-1", "-i", str(RAIZ / "public" / musica)]
        alto = VOLUME_MUSICA.get(formato, 0.07) * 2.5
        filtros.append("[voz]asplit=2[voz1][chave]")
        filtros.append(f"[{k}:a]volume={alto:.3f}[mus]")
        filtros.append("[mus][chave]sidechaincompress=threshold=0.015:ratio=6:attack=60:release=700[musb]")
        filtros.append("[voz1][musb]amix=inputs=2:normalize=0:duration=first[mix]")
        saida = "[mix]"
        k += 1
    efeitos = [e for e in props.get("efeitos", []) if (RAIZ / "public" / e["arquivo"]).exists()]
    if efeitos:  # os mesmos whoosh/pop do vídeo, no mesmo tempo
        for j, e in enumerate(efeitos):
            entradas += ["-i", str(RAIZ / "public" / e["arquivo"])]
            ms = int(e["inicio"] * 1000)
            filtros.append(f"[{k + j}:a]volume={e['volume']},adelay={ms}|{ms}[e{j}]")
        rotulos = "".join(f"[e{j}]" for j in range(len(efeitos)))
        filtros.append(f"{saida}{rotulos}amix=inputs={len(efeitos) + 1}:normalize=0:duration=first[comefeitos]")
        saida = "[comefeitos]"
    # mesmo volume do vídeo original (os vídeos saem por volta de -18 LUFS)
    filtros.append(f"{saida}apad,atrim=0:{total:.3f},loudnorm=I=-18:TP=-1.5:LRA=11[fim]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", ";".join(filtros),
                    "-map", "[fim]", "-ar", "44100", "-b:a", "192k", str(destino_mp3)], check=True)
    return palavras


# ---------------------------------------------------------------- textos da publicação
def descricao_completa(cfg_canal, lingua, desc, hashtags):
    t = canal_cfg.IDIOMAS[lingua]["textos"]
    tags = " ".join(f"#{gv.hashtag(h)}" for h in hashtags if gv.hashtag(h))
    return (f"{desc.strip()}\n\n{t['pergunta']}\n{t['chamadaFinal'].format(nome=cfg_canal['nome'])}\n\n"
            f"{t['avisoIA']}\n\n{tags}").strip()


def escrever_secao(pasta, traducoes, lingua_base, arquivos_base):
    arq = pasta / "publicacao.txt"
    if not arq.exists():
        return
    texto = arq.read_text(encoding="utf-8").split(MARCA_SECAO)[0].rstrip() + "\n\n"
    L = [MARCA_SECAO,
         "Em cada vídeo: Idiomas > Adicionar idioma > cole título e descrição. Se aparecer a opção",
         '"Adicionar áudio", envie o audio.<língua>.mp3 (o vídeo passa a tocar na língua de quem assiste).',
         f"Legendas: envie legenda.{lingua_base}.srt em Legendas > Adicionar > Enviar arquivo (com tempo).", ""]
    for lingua, t in traducoes.items():
        L += [f"===== {canal_cfg.IDIOMAS[lingua]['nome']} ({lingua}) =====", "TÍTULO", t["titulo"], "",
              "DESCRIÇÃO", t["descricaoCompleta"], ""]
        extras = [f for f in (t.get("legenda"), t.get("audio")) if f]
        if extras:
            L += ["Arquivos: " + ", ".join(extras), ""]
    if arquivos_base:
        L += [f"Legenda na língua do canal: {arquivos_base}", ""]
    arq.write_text(texto + "\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------- principal
def main(slug, com_traducao=True, com_audio=True):
    pasta = RAIZ / "saida" / slug
    arq_props = RAIZ / "public" / "projetos" / slug / "props.json"
    if not arq_props.exists() or not pasta.exists():
        log(f"Legendas: vídeo '{slug}' não encontrado.")
        return
    props = json.loads(arq_props.read_text(encoding="utf-8"))
    if not props.get("palavras"):
        return  # vídeo sem narração (ex.: sons relaxantes)
    cfg_canal = canal_cfg.carregar()
    lingua_base = cfg_canal.get("idioma", canal_cfg.IDIOMA_PADRAO)
    nome_srt = f"legenda.{lingua_base}.srt"
    (pasta / nome_srt).write_text(srt(props["palavras"]), encoding="utf-8")
    log(f"Legenda salva: saida/{slug}/{nome_srt}")

    info = json.loads((pasta / "info.json").read_text(encoding="utf-8")) if (pasta / "info.json").exists() else {}
    roteiro_arq = RAIZ / "roteiros" / f"{slug}.json"
    roteiro = json.loads(roteiro_arq.read_text(encoding="utf-8")) if roteiro_arq.exists() else {}
    formato = props.get("formato") or roteiro.get("formato") or info.get("formato") or "short"
    linguas = [k for k in cfg_canal.get("traducoes", list(canal_cfg.IDIOMAS)) if k != lingua_base]
    if not com_traducao or not linguas:
        escrever_secao(pasta, {}, lingua_base, nome_srt)
        return
    if not claude_cli.achar_claude():
        log("Traduções: o Claude Code não foi encontrado; só a legenda foi gerada.")
        escrever_secao(pasta, {}, lingua_base, nome_srt)
        return

    segs = segmentos(props)
    titulo, desc = ler_publicacao(pasta)
    pub = roteiro.get("publicacao", {})
    titulo = pub.get("titulo") or titulo
    desc = pub.get("descricao") or desc
    log(f"Traduzindo título, descrição e narração para {', '.join(linguas)}...")
    trad = traduzir_textos(titulo, desc, pub.get("hashtags", []), [s["texto"] for s in segs], linguas, lingua_base)
    if not trad:
        log("Traduções: o Claude não respondeu no formato esperado; só a legenda foi gerada.")
        escrever_secao(pasta, {}, lingua_base, nome_srt)
        return

    dublagem = info.get("origem") == "dublagem"  # o vídeo enviado tinha som próprio: não refazemos a trilha
    tmp = RAIZ / "trabalho" / f"traducao-{slug}"
    tmp.mkdir(parents=True, exist_ok=True)
    final = {}
    for lingua, t in trad.items():
        item = {"titulo": t["titulo"], "descricao": t.get("descricao", ""), "hashtags": t.get("hashtags", []),
                "descricaoCompleta": descricao_completa(cfg_canal, lingua, t.get("descricao", ""),
                                                        t.get("hashtags", []))}
        trechos = t.get("trechos") or []
        if com_audio and not dublagem and len(trechos) == len(segs):
            log(f"  Gravando a narração em {canal_cfg.IDIOMAS[lingua]['nome']}...")
            audio = f"audio.{lingua}.mp3"
            try:
                palavras = dublar_trilha(segs, trechos, lingua, props, formato, pasta / audio, tmp)
                (pasta / f"legenda.{lingua}.srt").write_text(srt(palavras), encoding="utf-8")
                item.update(audio=audio, legenda=f"legenda.{lingua}.srt")
            except (subprocess.CalledProcessError, OSError, ValueError, RuntimeError) as e:
                log(f"  Não consegui gravar o áudio em {lingua} ({e}).")
        elif com_audio and not dublagem:
            log(f"  {lingua}: a tradução veio com {len(trechos)} trechos (eram {len(segs)}); sem áudio.")
        final[lingua] = item
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    (pasta / "traducoes.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    escrever_secao(pasta, final, lingua_base, nome_srt)
    log(f"Traduções prontas: {', '.join(final)} (veja a seção TRADUÇÕES no publicacao.txt)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    main(args[0], com_traducao="--sem-traducao" not in sys.argv, com_audio="--sem-audio" not in sys.argv)
