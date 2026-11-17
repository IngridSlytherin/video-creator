"""Mede se os vídeos feitos pelo app seguram mais o público do que os antigos.

Como usar:
  1. YouTube Studio > Insights (ou "Estatísticas") > "Modo avançado" (canto superior direito) > aba "Conteúdo".
     Escolha o período (ex.: "Últimos 365 dias") e clique na seta de download > "Valores separados
     por vírgula (.csv)". O YouTube baixa um .zip.
  2. No painel, aba Resultados, envie esse .zip (ou o "Dados da tabela.csv" de dentro dele).
     Ou pelo terminal:  python -I pipeline/medir.py caminho/do/arquivo.zip

Vídeos "do app" = os que estão no historico.json (comparados pelo título).
O resultado fica em dados/medicoes/AAAA-MM-DD.md e um resumo vai para dados/aprendizados.md.
"""
import csv
import io
import json
import re
import statistics
import sys
import unicodedata
import zipfile
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "dados" / "medicoes"
LIMITE_SHORT = 180  # segundos: até 3 min conta como Short
MESES = {"jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "out": 10, "oct": 10, "nov": 11,
         "dez": 12, "dec": 12}


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"#\w+", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# ---------------------------------------------------------------- leitura do arquivo do Studio
def ler_tabela(caminho: Path):
    """Aceita o .zip do Studio ou o CSV de dentro dele. Devolve lista de dicts (linhas)."""
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as z:
            nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
            # a tabela por vídeo ("Dados da tabela.csv" / "Table data.csv") é a que tem mais linhas
            textos = [z.read(n).decode("utf-8-sig", errors="replace") for n in nomes]
        texto = max(textos, key=lambda t: t.count("\n")) if textos else ""
    else:
        texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(texto)))


def achar_coluna(colunas, *opcoes, excluir=()):
    """Acha a coluna pelo nome, em português ou inglês (o Studio muda conforme o idioma)."""
    for opcao in opcoes:
        for c in colunas:
            n = norm(c)
            if n.startswith(opcao) and not any(e in n for e in excluir):
                return c
    return None


def numero(texto):
    if texto is None:
        return None
    t = str(texto).strip().replace("%", "")
    if not t or t in ("-", "—"):
        return None
    if ":" in t:  # duração "0:00:31" ou "0:31"
        partes = [float(p) for p in t.split(":")]
        seg = 0.0
        for p in partes:
            seg = seg * 60 + p
        return seg
    t = t.replace(" ", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):  # separador de milhar: "1,500" ou "1.500"
        return float(re.sub(r"[.,]", "", t))
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def data(texto):
    """'Nov 16, 2026', '16 de nov. de 2026', '2026-11-16'..."""
    t = norm(texto)
    m = re.search(r"(\d{4}) (\d{1,2}) (\d{1,2})", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    ano = re.search(r"\b(\d{4})\b", t)
    mes = next((MESES[p[:3]] for p in t.split() if p[:3] in MESES), None)
    dia = re.search(r"\b(\d{1,2})\b", t)
    if ano and mes and dia:
        try:
            return date(int(ano.group(1)), mes, int(dia.group(1)))
        except ValueError:
            return None
    return None


def interpretar(linhas):
    if not linhas:
        raise ValueError("arquivo vazio")
    cols = list(linhas[0].keys())
    c = {
        "titulo": achar_coluna(cols, "titulo do video", "video title", "titulo", "title"),
        "publicado": achar_coluna(cols, "horario de publicacao", "data de publicacao", "video publish time",
                                  "publish"),
        "duracao": achar_coluna(cols, "duracao", "duration", excluir=("media", "average")),
        "views": achar_coluna(cols, "visualizacoes", "views", excluir=("engajada", "engaged", "unica", "unique")),
        "media": achar_coluna(cols, "duracao media", "average view duration"),
        "pct": achar_coluna(cols, "porcentagem media", "average percentage viewed"),
        "ctr": achar_coluna(cols, "taxa de cliques", "impressions click through", "click through"),
    }
    if not c["titulo"] or not (c["pct"] or c["media"]):
        raise ValueError("não achei as colunas de título e retenção. Exporte a aba 'Conteúdo' do modo "
                         "avançado do YouTube Studio. Colunas encontradas: " + ", ".join(cols))
    videos = []
    for l in linhas:
        titulo = (l.get(c["titulo"]) or "").strip()
        if not titulo or norm(titulo) in ("total", ""):
            continue
        v = {
            "titulo": titulo,
            "publicado": data(l.get(c["publicado"])) if c["publicado"] else None,
            "duracao": numero(l.get(c["duracao"])) if c["duracao"] else None,
            "views": numero(l.get(c["views"])) if c["views"] else None,
            "media": numero(l.get(c["media"])) if c["media"] else None,
            "pct": numero(l.get(c["pct"])) if c["pct"] else None,
            "ctr": numero(l.get(c["ctr"])) if c["ctr"] else None,
        }
        if v["pct"] is None and v["media"] and v["duracao"]:
            v["pct"] = 100 * v["media"] / v["duracao"]
        videos.append(v)
    return videos


# ---------------------------------------------------------------- comparação
def titulos_do_app():
    arq = RAIZ / "historico.json"
    if not arq.exists():
        return []
    return [norm(h.get("titulo", "")) for h in json.loads(arq.read_text(encoding="utf-8"))]


def eh_do_app(titulo, do_app):
    t = norm(titulo)
    return any(t and (t == h or SequenceMatcher(None, t, h).ratio() >= 0.8) for h in do_app)


def resumo(lista):
    def media(chave):
        valores = [v[chave] for v in lista if v.get(chave) is not None]
        return statistics.mean(valores) if valores else None

    views = [v["views"] for v in lista if v.get("views") is not None]
    return {"n": len(lista), "pct": media("pct"), "media": media("media"), "ctr": media("ctr"),
            "views": statistics.median(views) if views else None}


def fmt(valor, sufixo="", casas=1):
    return "—" if valor is None else f"{valor:.{casas}f}{sufixo}".replace(".", ",")


def seta(novo, antigo):
    if novo is None or antigo is None:
        return ""
    d = novo - antigo
    return f" ({'▲' if d > 0 else '▼'} {fmt(abs(d), casas=1)})" if abs(d) >= 0.05 else " (=)"


def medir(caminho: Path):
    videos = interpretar(ler_tabela(caminho))
    do_app = titulos_do_app()
    hoje = date.today()
    for v in videos:
        v["app"] = eh_do_app(v["titulo"], do_app)
        v["formato"] = "short" if (v["duracao"] or 0) and v["duracao"] <= LIMITE_SHORT else "longo"
        v["dias"] = (hoje - v["publicado"]).days if v["publicado"] else None
        v["cedo"] = (v["dias"] is not None and v["dias"] < 7) or (v["views"] or 0) < 100

    L = [f"# Resultados — {hoje:%d/%m/%Y}", "",
         f"Arquivo: `{caminho.name}` · {len(videos)} vídeos · do app: {sum(v['app'] for v in videos)}", ""]
    linhas_resumo = []
    for formato, rotulo in (("short", "Shorts"), ("longo", "Vídeos longos")):
        grupo = [v for v in videos if v["formato"] == formato]
        if not grupo:
            continue
        antes = resumo([v for v in grupo if not v["app"]])
        app_todos = [v for v in grupo if v["app"]]
        app = resumo([v for v in app_todos if not v["cedo"]])
        L += [f"## {rotulo}", "",
              "| | Vídeos | % média assistida | Tempo médio assistido | Views (mediana) | CTR |",
              "|---|---|---|---|---|---|",
              f"| Antes do app | {antes['n']} | {fmt(antes['pct'], '%')} | {fmt(antes['media'], ' s', 0)} | "
              f"{fmt(antes['views'], '', 0)} | {fmt(antes['ctr'], '%')} |",
              f"| Feitos pelo app | {app['n']} | {fmt(app['pct'], '%')}{seta(app['pct'], antes['pct'])} | "
              f"{fmt(app['media'], ' s', 0)}{seta(app['media'], antes['media'])} | {fmt(app['views'], '', 0)} | "
              f"{fmt(app['ctr'], '%')} |", ""]
        cedo = [v for v in app_todos if v["cedo"]]
        if cedo:
            L.append(f"_{len(cedo)} vídeo(s) do app ainda são novos (menos de 7 dias ou 100 views) e ficaram "
                     "de fora da média: os números deles ainda vão mudar._")
            L.append("")
        if app["n"] >= 3 and antes["pct"] is not None and app["pct"] is not None:
            dif = app["pct"] - antes["pct"]
            veredito = ("as regras de roteiro estão ajudando" if dif >= 3 else
                        "ainda não fez diferença clara" if dif > -3 else "os vídeos do app estão segurando menos")
            linhas_resumo.append(f"- {rotulo}: % média assistida {fmt(app['pct'], '%')} nos vídeos do app "
                                 f"contra {fmt(antes['pct'], '%')} antes ({app['n']} vs {antes['n']} vídeos): "
                                 f"{veredito}.")
        elif app_todos:
            linhas_resumo.append(f"- {rotulo}: ainda poucos vídeos do app com dados ({app['n']} prontos para comparar; "
                                 "o ideal é ter 3 ou mais com 7+ dias).")
        if app_todos:
            L += [f"### {rotulo} feitos pelo app", "", "| Vídeo | Publicado | % assistida | Tempo médio | Views |",
                  "|---|---|---|---|---|"]
            for v in sorted(app_todos, key=lambda v: -(v["pct"] or 0)):
                marca = " ⏳" if v["cedo"] else ""
                pub = v["publicado"].strftime("%d/%m") if v["publicado"] else "—"
                L.append(f"| {v['titulo']}{marca} | {pub} | {fmt(v['pct'], '%')} | {fmt(v['media'], ' s', 0)} | "
                         f"{fmt(v['views'], '', 0)} |")
            L.append("")
        melhores = sorted([v for v in grupo if not v["cedo"] and v["pct"] is not None], key=lambda v: -v["pct"])[:5]
        if melhores:
            L += [f"### Os {len(melhores)} {rotulo.lower()} que mais seguram o público", ""]
            L += [f"- {fmt(v['pct'], '%')} · {v['titulo']}{' (app)' if v['app'] else ''}" for v in melhores]
            L.append("")

    L += ["## Conclusão", ""] + (linhas_resumo or ["- Sem dados suficientes para comparar ainda."])
    L += ["", "⏳ = vídeo novo (menos de 7 dias ou 100 views): espere antes de tirar conclusões.", ""]

    PASTA.mkdir(parents=True, exist_ok=True)
    md = PASTA / f"{hoje:%Y-%m-%d}.md"
    md.write_text("\n".join(L), encoding="utf-8")
    (PASTA / f"{hoje:%Y-%m-%d}.json").write_text(
        json.dumps([{**v, "publicado": v["publicado"].isoformat() if v["publicado"] else None} for v in videos],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    anotar_aprendizados(hoje, linhas_resumo)
    print("\n".join(L))
    print(f"\nRelatório: {md.relative_to(RAIZ)}")


def anotar_aprendizados(hoje, linhas):
    """Acrescenta a conclusão em dados/aprendizados.md (o Claude lê antes de sugerir ideias)."""
    if not linhas:
        return
    arq = RAIZ / "dados" / "aprendizados.md"
    texto = arq.read_text(encoding="utf-8") if arq.exists() else "# O que funciona no canal\n"
    titulo = f"## Medição {hoje:%d/%m/%Y} (vídeos do app x antes)"
    if titulo in texto:  # mesma data: substitui
        texto = texto.split(titulo)[0].rstrip() + "\n"
    arq.write_text(texto.rstrip() + "\n\n" + titulo + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        medir(Path(sys.argv[1]))
    except (ValueError, zipfile.BadZipFile, OSError) as e:
        sys.exit(f"Não consegui ler o arquivo: {e}")
