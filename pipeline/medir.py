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
            # a tabela por vídeo é "Dados da tabela.csv" ("Table data.csv" em inglês); os outros são
            # o gráfico por dia e os totais
            def prioridade(n):
                b = norm(Path(n).stem)
                return 0 if ("tabela" in b or "table" in b) else 1 if not ("grafico" in b or "chart" in b or "total" in b) else 2
            nomes.sort(key=prioridade)
            texto = z.read(nomes[0]).decode("utf-8-sig", errors="replace") if nomes else ""
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


def separador_decimal(linhas):
    """Descobre se o arquivo usa ponto ou vírgula como decimal (o Studio muda conforme o idioma).
    Valores como '4.842' (horas) são ambíguos; '0.0096' ou '11.5678' não."""
    pontos = virgulas = 0
    for l in linhas:
        for v in l.values():
            t = str(v or "").strip()
            if re.fullmatch(r"\d+\.\d+", t) and not re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
                pontos += 1
            elif re.fullmatch(r"\d+,\d+", t) and not re.fullmatch(r"\d{1,3}(,\d{3})+", t):
                virgulas += 1
    if pontos > virgulas:
        return "."
    if virgulas > pontos:
        return ","
    return None


def numero(texto, decimal=None):
    if texto is None:
        return None
    t = str(texto).strip().replace("%", "")
    if not t or t in ("-", "—"):
        return None
    if decimal and ":" not in t:  # formato do arquivo já conhecido
        t = t.replace(" ", "").replace(" ", "")
        t = t.replace("," if decimal == "." else ".", "").replace(",", ".")
        try:
            return float(t)
        except ValueError:
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
        "horas": achar_coluna(cols, "tempo de exibicao", "watch time"),
    }
    # A exportação padrão do Studio não traz a retenção, mas traz tempo de exibição e views:
    # tempo médio assistido = horas x 3600 / views; % assistida = tempo médio / duração.
    da_pra_calcular = c["horas"] and c["views"] and c["duracao"]
    if not c["titulo"] or not (c["pct"] or c["media"] or da_pra_calcular):
        raise ValueError("não achei as colunas de título e retenção. Exporte a aba 'Conteúdo' do modo "
                         "avançado do YouTube Studio. Colunas encontradas: " + ", ".join(cols))
    dec = separador_decimal(linhas)
    num = lambda chave: numero(l.get(c[chave]), dec) if c[chave] else None  # noqa: E731
    videos = []
    for l in linhas:
        titulo = (l.get(c["titulo"]) or "").strip()
        if not titulo or norm(titulo) in ("total", ""):
            continue
        v = {
            "titulo": titulo,
            "publicado": data(l.get(c["publicado"])) if c["publicado"] else None,
            "duracao": num("duracao"),
            "views": num("views"),
            "media": num("media"),
            "pct": num("pct"),
            "ctr": num("ctr"),
        }
        if v["media"] is None and c["horas"]:
            horas = num("horas")
            if horas is not None and v["views"]:
                v["media"] = horas * 3600 / v["views"]
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
    linhas_padroes, regras = padroes(videos)
    L += linhas_padroes
    salvar_videos_do_canal(videos)

    PASTA.mkdir(parents=True, exist_ok=True)
    md = PASTA / f"{hoje:%Y-%m-%d}.md"
    md.write_text("\n".join(L), encoding="utf-8")
    (PASTA / f"{hoje:%Y-%m-%d}.json").write_text(
        json.dumps([{**v, "publicado": v["publicado"].isoformat() if v["publicado"] else None} for v in videos],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    anotar_aprendizados(hoje, linhas_resumo, regras)
    print("\n".join(L))
    print(f"\nRelatório: {md.relative_to(RAIZ)}")


def trocar_secao(texto, titulo, linhas):
    """Põe (ou substitui) a seção '## titulo' no texto, sem mexer nas outras seções."""
    bloco = titulo + "\n" + "\n".join(linhas) + "\n"
    padrao = re.compile(r"^" + re.escape(titulo) + r"\n.*?(?=^## |\Z)", re.S | re.M)
    if padrao.search(texto):
        return padrao.sub(lambda _: bloco + "\n", texto).rstrip() + "\n"
    return texto.rstrip() + "\n\n" + bloco


def anotar_aprendizados(hoje, linhas, regras=None):
    """Grava a conclusão e as regras do canal em dados/aprendizados.md (o Claude lê antes de
    sugerir ideias e escrever roteiros)."""
    arq = RAIZ / "dados" / "aprendizados.md"
    texto = arq.read_text(encoding="utf-8") if arq.exists() else "# O que funciona no canal\n"
    if regras:
        texto = trocar_secao(texto, "## Regras do canal (tiradas dos números; atualizadas a cada medição)", regras)
    if linhas:
        texto = trocar_secao(texto, f"## Medição {hoje:%d/%m/%Y} (vídeos do app x antes)", linhas)
    arq.write_text(texto, encoding="utf-8")


# ---------------------------------------------------------------- o que dá certo no canal
def formato_titulo(t):
    s = norm(t)
    if s.startswith("por que") or s.startswith("porque"):
        return "Pergunta “Por que…”"
    if "verdade ou mito" in s or s.startswith("mito"):
        return "Verdade ou mito"
    if re.match(r"^\d+ ", s):
        return "Lista com número"
    if "?" in t or s.startswith(("como ", "o que ", "qual ", "quem ", "e se ", "para que", "quanto")):
        return "Outra pergunta"
    return "Afirmação"


def faixa_duracao(d):
    return "até 45 s" if d <= 45 else "46 a 60 s" if d <= 60 else "61 a 70 s" if d <= 70 else "mais de 70 s"


DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
NOMES_GRUPO = {"mamifero": "mamíferos", "reptil": "répteis", "anfibio": "anfíbios", "aracnideo": "aracnídeos",
               "inseto": "insetos", "ave": "aves", "pet": "pets", "fazenda": "animais de fazenda",
               "marinho": "bichos do mar", "rio": "bichos de rio", "felino": "felinos", "primata": "primatas",
               "pre-historico": "pré-históricos", "molusco": "moluscos", "savana": "savana"}


def temas_do_canal():
    """Lista de temas do radar (com grupo e palavras de busca), para agrupar os vídeos por assunto."""
    try:
        canal = json.loads((RAIZ / "dados" / "canal.json").read_text(encoding="utf-8"))
        arq = RAIZ / canal.get("radar", {}).get("temas", "")
        temas = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    saida = []
    for t in temas:
        termos = [re.sub(r"[-_]", " ", norm(b)) for b in t.get("busca", []) if b]
        if termos:
            saida.append((t["pt"], t.get("grupo", ""),
                          re.compile(r"(?<![a-z0-9])(" + "|".join(map(re.escape, termos)) + r")s?(?![a-z0-9])")))
    return saida


def tabela_grupos(nome, videos, chave, minimo=3):
    grupos = {}
    for v in videos:
        k = chave(v)
        if k:
            grupos.setdefault(k, []).append(v)
    linhas = [f"### {nome}", "", "| | Vídeos | Views (mediana) | % assistida (mediana) |", "|---|---|---|---|"]
    ordem = sorted(grupos.items(), key=lambda kv: -statistics.median(x["views"] for x in kv[1]))
    for k, L in ordem:
        pcts = [x["pct"] for x in L if x.get("pct") is not None]
        aviso = " (poucos vídeos)" if len(L) < minimo else ""
        linhas.append(f"| {k}{aviso} | {len(L)} | {fmt(statistics.median(x['views'] for x in L), '', 0)} | "
                      f"{fmt(statistics.median(pcts), '%') if pcts else '—'} |")
    return linhas + [""], {k: L for k, L in grupos.items()}


def padroes(videos):
    """Analisa os Shorts com dados firmes e devolve (linhas do relatório, regras para o aprendizados)."""
    base = [v for v in videos if v["formato"] == "short" and not v["cedo"] and v.get("views")]
    if len(base) < 10:
        return [], []
    geral = statistics.median(v["views"] for v in base)
    L = ["## O que dá certo no canal (Shorts com 7+ dias)", "",
         f"Base: {len(base)} Shorts. Mediana do canal: {fmt(geral, '', 0)} views por Short.", ""]
    regras = []

    def compara(grupos, minimo=5):
        validos = {k: statistics.median(x["views"] for x in g) for k, g in grupos.items() if len(g) >= minimo}
        return sorted(validos.items(), key=lambda kv: -kv[1])

    linhas, g_titulo = tabela_grupos("Formato do título", base, lambda v: formato_titulo(v["titulo"]))
    L += linhas
    maior = max(g_titulo.items(), key=lambda kv: len(kv[1]))
    if len(maior[1]) / len(base) > 0.6:
        regras.append(f"- Títulos: {round(100 * len(maior[1]) / len(base))}% dos Shorts usam \"{maior[0]}\". "
                      "Esse formato não rende menos, mas deixa o canal repetitivo: use em no máximo 1 de cada 3 "
                      "vídeos e teste outros (afirmação surpreendente, número, comparação, verdade ou mito).")
    for k, mediana in compara(g_titulo):
        if mediana < geral * 0.6:
            regras.append(f"- Evite o formato \"{k}\" em Shorts: mediana de {fmt(mediana, '', 0)} views, "
                          f"bem abaixo do canal ({fmt(geral, '', 0)}).")
    pequenos = {k: g for k, g in g_titulo.items() if 2 <= len(g) < 5}
    for k, g in pequenos.items():
        m = statistics.median(x["views"] for x in g)
        if m < geral * 0.4:
            regras.append(f"- \"{k}\" foi mal nos {len(g)} Shorts em que foi usado ({fmt(m, '', 0)} views): evite.")

    linhas, g_dur = tabela_grupos("Duração", base, lambda v: faixa_duracao(v["duracao"]) if v.get("duracao") else None)
    L += linhas
    ranking = compara(g_dur)
    if len(ranking) >= 2 and ranking[-1][1] < ranking[0][1] * 0.8:
        regras.append(f"- Duração: Shorts de {ranking[0][0]} rendem mais (mediana {fmt(ranking[0][1], '', 0)} views); "
                      f"os de {ranking[-1][0]} rendem {round(100 * (1 - ranking[-1][1] / ranking[0][1]))}% menos. "
                      f"Evite {ranking[-1][0]}.")

    linhas, g_dia = tabela_grupos("Dia da publicação", base,
                                  lambda v: DIAS[v["publicado"].weekday()] if v.get("publicado") else None)
    L += linhas
    for k, mediana in compara(g_dia):
        if mediana < geral * 0.6:
            regras.append(f"- {k.capitalize()} tem rendido pouco ({fmt(mediana, '', 0)} views de mediana): "
                          "prefira outros dias.")

    temas = temas_do_canal()
    if temas:
        def grupo_de(v):
            t = re.sub(r"[-_]", " ", norm(v["titulo"]))
            g = next((g or nome for nome, g, r in temas if r.search(t)), "fora da lista de temas")
            return NOMES_GRUPO.get(g, g)
        linhas, g_assunto = tabela_grupos("Assunto", base, grupo_de)
        L += linhas
        ranking = compara(g_assunto)
        if ranking:
            regras.append(f"- Assuntos que mais rendem: {', '.join(k for k, _ in ranking[:3])}.")
        fora = g_assunto.get("fora da lista de temas", [])
        if len(fora) >= 5 and statistics.median(x["views"] for x in fora) < geral * 0.85:
            regras.append(f"- Temas fora da categoria do canal rendem menos (mediana "
                          f"{fmt(statistics.median(x['views'] for x in fora), '', 0)} views): fique na categoria.")

    # mesma pergunta publicada de novo (títulos quase iguais) divide o público
    duplicados = []
    for i, a in enumerate(base):
        for b in base[i + 1:]:
            if SequenceMatcher(None, norm(a["titulo"]), norm(b["titulo"])).ratio() >= 0.75:
                duplicados.append((a, b))
    if duplicados:
        L += ["### Mesma pergunta publicada mais de uma vez", ""]
        L += [f"- {fmt(a['views'], '', 0)} e {fmt(b['views'], '', 0)} views · {a['titulo'][:70]}" for a, b in duplicados[:8]]
        L.append("")
        regras.append(f"- Não publique a mesma pergunta de novo ({len(duplicados)} casos no canal): o mesmo animal "
                      "pode voltar, mas com um ângulo novo (outro fato, outra pergunta).")

    top = sorted(base, key=lambda v: -v["views"])[:5]
    L += ["### Os 5 Shorts mais vistos", ""] + [f"- {fmt(v['views'], '', 0)} views · {v['titulo']}" for v in top] + [""]
    if regras:
        L += ["### Regras que o app passa a seguir", ""] + regras + [""]
    return L, regras


def salvar_videos_do_canal(videos):
    """Lista de todos os vídeos publicados (título, data, views), para o Claude não repetir perguntas."""
    lista = [{"titulo": v["titulo"], "publicado": v["publicado"].isoformat() if v.get("publicado") else None,
              "views": v.get("views"), "formato": v["formato"]} for v in videos]
    lista.sort(key=lambda v: v["publicado"] or "", reverse=True)
    (RAIZ / "dados" / "videos-do-canal.json").write_text(json.dumps(lista, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        medir(Path(sys.argv[1]))
    except (ValueError, zipfile.BadZipFile, OSError) as e:
        sys.exit(f"Não consegui ler o arquivo: {e}")
