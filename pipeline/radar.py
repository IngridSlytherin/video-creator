"""Radar de assuntos em alta para o seu canal (categoria em dados/canal.json).

Fontes gratuitas, sem chave de API:
  - Wikipedia (PT e EN): quais temas da lista tiveram pico de acessos na última semana
  - Google Notícias: notícias dos últimos 7 dias com os termos da categoria
  - Google Trends (país da língua do canal): buscas em alta hoje que citam algum tema da lista
  - YouTube: vídeos em português da categoria publicados esta semana e suas views

A lista de temas fica em dados/temas/<categoria>.json (para Animais já vem pronta;
para outras categorias o painel pede ao Claude Code para criar). Sem lista, o radar
mostra as notícias e vídeos da semana mesmo assim, só sem a pontuação por tema.

Uso:
    python -I pipeline/radar.py

Resultado: dados/radar/AAAA-MM-DD.md (para ler) e .json (dados completos).
"""
import html
import importlib.util
import json
import math
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RADAR = RAIZ / "dados" / "radar"
UA_API = {"User-Agent": "VideoCreatorRadar/1.0 (uso pessoal) python-requests"}
UA_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

_spec = importlib.util.spec_from_file_location("canal", RAIZ / "pipeline" / "canal.py")
canal_cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canal_cfg)

# Preenchidos em main() a partir de dados/canal.json
BUSCAS_NOTICIAS, BUSCAS_YOUTUBE, PESO_GRUPO = [], [], {}
IDIOMA = canal_cfg.IDIOMAS[canal_cfg.IDIOMA_PADRAO]  # região/língua do radar


# ---------------------------------------------------------------- utilidades
def normalizar(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[-_]", " ", t)


def compilar_padroes(animais):
    for a in animais:
        termos = [normalizar(t) for t in a["busca"]]
        a["_re"] = (
            re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in termos) + r")s?(?![a-z0-9])")
            if termos
            else None
        )


def animais_no_texto(texto, animais):
    t = normalizar(texto)
    return [a["pt"] for a in animais if a["_re"] and a["_re"].search(t)]


def get(url, cab=UA_API, silencioso=False, **kw):
    """GET com até 4 tentativas quando o site pede para esperar (429)."""
    for tentativa in range(4):
        try:
            r = requests.get(url, headers=cab, timeout=25, **kw)
        except requests.RequestException as e:
            if not silencioso:
                print(f"  aviso: {url[:70]}... falhou ({e.__class__.__name__})")
            return None
        if r.status_code == 200:
            return r
        if r.status_code == 429 and tentativa < 3:
            time.sleep(min(60, int(r.headers.get("retry-after") or 0) or 3 * 2**tentativa))
            continue
        if not silencioso:
            print(f"  aviso: {url[:70]}... respondeu {r.status_code}")
        return None
    return None


def numero(texto):
    """'136.717 visualizações' -> 136717; 'Nenhuma visualização' -> 0."""
    d = re.sub(r"\D", "", texto or "")
    return int(d) if d else 0


# ---------------------------------------------------------------- Wikipedia
def views_em_lote(projeto, titulos):
    """Acessos diários (35 dias) de até 50 páginas por pedido, seguindo redirecionamentos.
    Devolve {titulo_original: [views por dia] ou None se a página não existe}."""
    res = {}
    lista = list(dict.fromkeys(titulos))
    for i in range(0, len(lista), 50):
        lote = lista[i : i + 50]
        mapa = {t: t for t in lote}
        dias = {}
        params = {"action": "query", "prop": "pageviews", "titles": "|".join(lote), "pvipdays": 35,
                  "redirects": 1, "format": "json", "formatversion": 2}
        cont = {}
        while True:
            r = get(f"https://{projeto}/w/api.php", params={**params, **cont})
            if not r:
                break
            d = r.json()
            q = d.get("query", {})
            for chave in ("normalized", "redirects"):
                for n in q.get(chave, []):
                    for orig, atual in mapa.items():
                        if atual == n["from"]:
                            mapa[orig] = n["to"]
            for pg in q.get("pages", []):
                if pg.get("missing"):
                    dias[pg["title"]] = None
                elif pg.get("pageviews"):
                    dias[pg["title"]] = pg["pageviews"]
            if "continue" not in d:
                break
            cont = d["continue"]
            time.sleep(0.5)
        for orig, atual in mapa.items():
            pv = dias.get(atual)
            res[orig] = None if pv is None else [v or 0 for _, v in sorted(pv.items())]
        time.sleep(0.5)
    return res


def tendencia(views):
    """Média dos últimos 7 dias contra as 4 semanas anteriores."""
    if not views or len(views) < 14:
        return None
    rec = sum(views[-7:]) / 7
    base_lista = views[:-7][-28:]
    base = sum(base_lista) / len(base_lista)
    return {"semana": round(rec), "antes": round(base), "razao": round((rec + 10) / (base + 10), 2)}


def titulo_wiki(tema, lang):
    """Título do artigo na Wikipedia daquela língua (wiki_pt, wiki_en, wiki_es...)."""
    return tema.get(f"wiki_{lang}") or (tema.get("wiki_local") if lang == IDIOMA["wiki"] else None)


def coletar_wikipedia(animais):
    """Acessos na Wikipedia da língua do canal ('local') e na inglesa ('en', interesse mundial)."""
    local = IDIOMA["wiki"]
    projetos = [("local", local)] + ([("en", "en")] if local != "en" else [])
    print(f"Wikipedia: conferindo acessos de {len(animais)} temas ({', '.join(l.upper() for _, l in projetos)})...")
    res, lidas = {}, 0
    for chave, lang in projetos:
        titulos = [titulo_wiki(a, lang) for a in animais if titulo_wiki(a, lang)]
        views = views_em_lote(f"{lang}.wikipedia.org", titulos)
        for a in animais:
            t = tendencia(views.get(titulo_wiki(a, lang) or ""))
            res.setdefault(a["pt"], {})[chave] = t
            lidas += t is not None
    print(f"  {lidas} de {len(projetos) * len(animais)} páginas lidas")
    return res


# ---------------------------------------------------------------- Google Notícias / Trends
def itens_rss(texto):
    for bloco in re.findall(r"<item>(.*?)</item>", texto, re.S):
        def campo(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", bloco, re.S)
            v = m.group(1) if m else ""
            v = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v.strip(), flags=re.S)
            return html.unescape(v).strip()

        yield bloco, campo


def coletar_noticias(animais):
    print("Google Notícias: buscando notícias dos últimos 7 dias...")
    vistas, saida = set(), []
    for busca in BUSCAS_NOTICIAS:
        r = get(
            "https://news.google.com/rss/search",
            params={"q": f"{busca} when:7d", **IDIOMA["noticias"]},
        )
        if not r:
            continue
        for _, campo in itens_rss(r.text):
            titulo, fonte = campo("title"), campo("source")
            if fonte and titulo.endswith(" - " + fonte):
                titulo = titulo[: -len(fonte) - 3]
            chave = normalizar(titulo)
            if chave in vistas:
                continue
            vistas.add(chave)
            achados = animais_no_texto(titulo, animais)
            if animais and not achados:  # sem lista de temas, mostra tudo
                continue
            try:
                quando = parsedate_to_datetime(campo("pubDate")).strftime("%d/%m")
            except (TypeError, ValueError):
                quando = ""
            saida.append({"titulo": titulo, "fonte": fonte, "data": quando, "link": campo("link"), "animais": achados})
    print(f"  {len(saida)} notícias encontradas")
    return saida


def coletar_trends(animais):
    print(f"Google Trends: buscas em alta hoje ({IDIOMA['trends']})...")
    r = get("https://trends.google.com/trending/rss", params={"geo": IDIOMA["trends"]})
    if not r:
        return [], []
    todos, saida = [], []
    for _, campo in itens_rss(r.text):
        termo = campo("title")
        todos.append(termo)
        noticia = campo("ht:news_item_title")
        achados = animais_no_texto(f"{termo} {noticia}", animais)
        if achados:
            saida.append({"termo": termo, "trafego": campo("ht:approx_traffic"), "noticia": noticia, "animais": achados})
    print(f"  {len(todos)} assuntos em alta, {len(saida)} da sua lista")
    return saida, todos


# ---------------------------------------------------------------- YouTube
def videos_da_busca(texto_html):
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", texto_html, re.S)
    if not m:
        return []
    achados = []

    def andar(o):
        if isinstance(o, dict):
            v = o.get("videoRenderer")
            if v:
                achados.append(
                    {
                        "id": v.get("videoId"),
                        "titulo": "".join(x.get("text", "") for x in v.get("title", {}).get("runs", [])),
                        "views": numero(v.get("viewCountText", {}).get("simpleText")),
                        "publicado": v.get("publishedTimeText", {}).get("simpleText", ""),
                        "duracao": v.get("lengthText", {}).get("simpleText", ""),
                        "canal": (v.get("ownerText", {}).get("runs") or [{}])[0].get("text", ""),
                    }
                )
            for x in o.values():
                andar(x)
        elif isinstance(o, list):
            for x in o:
                andar(x)

    andar(json.loads(m.group(1)))
    return achados


def coletar_youtube(animais):
    print("YouTube: vídeos da categoria publicados esta semana...")
    vistos = {}
    for busca in BUSCAS_YOUTUBE:
        # sp=EgQIAxAB -> filtro "esta semana" + "vídeo"
        r = get(
            "https://www.youtube.com/results",
            cab=UA_WEB,
            params={"search_query": busca, "sp": "EgQIAxAB", **IDIOMA["youtube"]},
        )
        if not r:
            continue
        try:
            for v in videos_da_busca(r.text):
                if v["id"] and v["id"] not in vistos:
                    v["animais"] = animais_no_texto(v["titulo"], animais)
                    vistos[v["id"]] = v
        except (ValueError, KeyError) as e:
            print(f"  aviso: não consegui ler a busca '{busca}' ({e.__class__.__name__})")
    lista = sorted(vistos.values(), key=lambda v: -v["views"])
    print(f"  {len(lista)} vídeos encontrados")
    return lista


# ---------------------------------------------------------------- já feitos
def animais_ja_feitos(animais):
    feitos = set()

    def andar(o):
        if isinstance(o, dict):
            if isinstance(o.get("animal"), str):
                feitos.add(o["animal"].lower())
            for v in o.values():
                andar(v)
        elif isinstance(o, list):
            for v in o:
                andar(v)

    for arq in (RAIZ / "roteiros").glob("*.json"):
        try:
            andar(json.loads(arq.read_text(encoding="utf-8")))
        except ValueError:
            pass
    return {a["pt"] for a in animais if a["en"] in feitos or a["pt"] in feitos or feitos & set(a["busca"])}


# ---------------------------------------------------------------- pontuação
def mil(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} mi".replace(".", ",")
    if n >= 1000:
        return f"{n // 1000} mil"
    return str(n)


def pontuar(animais, wiki, noticias, trends, videos, feitos):
    lg = lambda x: math.log2(x) if x and x > 0 else 0
    lista = []
    for a in animais:
        nome = a["pt"]
        w = wiki.get(nome, {})
        pt, en = w.get("local"), w.get("en")
        n_not = sum(nome in n["animais"] for n in noticias)
        n_tr = sum(nome in t["animais"] for t in trends)
        vids = [v for v in videos if nome in v["animais"]]
        yt = sum(v["views"] for v in vids)

        pontos = 0.0
        motivos = []
        if pt:
            pontos += max(0, lg(pt["razao"])) * 4 + 0.6 * math.log10(1 + pt["antes"])
            if pt["razao"] >= 1.25:
                motivos.append(f"Wikipedia {IDIOMA['wiki'].upper()} +{round((pt['razao'] - 1) * 100)}% na semana")
        if en:
            pontos += max(0, lg(en["razao"])) * 2.5
            if en["razao"] >= 1.25:
                motivos.append(f"Wikipedia EN +{round((en['razao'] - 1) * 100)}% (interesse mundial)")
        if n_not:
            pontos += min(n_not, 8) * 0.7
            motivos.append(f"{n_not} notícia{'s' if n_not > 1 else ''} na semana")
        if n_tr:
            pontos += 4 * n_tr
            motivos.append("no Google Trends hoje")
        if yt:
            pontos += 1.2 * math.log10(1 + yt)
            motivos.append(f"YouTube: {len(vids)} vídeo{'s' if len(vids) > 1 else ''}, {mil(yt)} views na semana")
        pontos *= PESO_GRUPO.get(a.get("grupo", ""), 1.0)
        if nome in feitos:
            pontos *= 0.4
            motivos.append("⚠️ já tem vídeo no canal")
        lista.append(
            {
                "animal": nome,
                "en": a["en"],
                "grupo": a["grupo"],
                "pontos": round(pontos, 1),
                "motivos": motivos,
                "wiki_pt": pt,
                "wiki_en": en,
                "noticias": n_not,
                "trends": n_tr,
                "youtube_views": yt,
                "ja_feito": nome in feitos,
            }
        )
    return sorted(lista, key=lambda x: -x["pontos"])


# ---------------------------------------------------------------- relatório
def escrever_md(hoje, ranking, noticias, trends, todos_trends, videos):
    L = [f"# Radar {NOME_CANAL} — {hoje:%d/%m/%Y}", ""]
    L.append("Fontes: Wikipedia (acessos dos últimos 7 dias contra as 4 semanas anteriores), "
             f"Google Notícias (7 dias), Google Trends {IDIOMA['trends']} (hoje) e busca do YouTube (esta semana).")
    L += ["", "## Temas em alta", "", "| # | Tema | Pontos | Por quê |", "|---|---|---|---|"]
    for i, r in enumerate(ranking[:15], 1):
        L.append(f"| {i} | {r['animal']} | {r['pontos']} | {'; '.join(r['motivos']) or 'interesse constante'} |")

    L += ["", "## Notícias da semana", "", "(links no arquivo .json de mesmo nome)", ""]
    if noticias:
        for n in noticias[:25]:
            marcados = f" · _{', '.join(n['animais'])}_" if n["animais"] else ""
            L.append(f"- {n['titulo']} — {n['fonte']}, {n['data']}{marcados}")
    else:
        L.append("- Nenhuma notícia encontrada.")

    L += ["", "## Vídeos da categoria que mais bombaram no YouTube esta semana", "",
          "Use para ver **formatos e títulos** que estão funcionando (não para copiar).", ""]
    for v in videos[:15]:
        L.append(f"- **{mil(v['views'])} views** · {v['titulo']} — {v['canal']} ({v['duracao']}, {v['publicado']})")

    L += ["", f"## Google Trends {IDIOMA['trends']} (hoje)", ""]
    if trends:
        for t in trends:
            L.append(f"- **{t['termo']}** ({t['trafego']} buscas) — {t['noticia']} · _{', '.join(t['animais'])}_")
    else:
        L.append("- Nenhum tema da lista entre os mais buscados de hoje. "
                 f"(Em alta: {', '.join(todos_trends[:8])}...)")

    L += ["", "---", "Para virar vídeo, peça no Claude Code: `/radar` (ele lê este arquivo e sugere temas e títulos)."]
    return "\n".join(L) + "\n"


NOME_CANAL = ""


def main():
    global BUSCAS_NOTICIAS, BUSCAS_YOUTUBE, PESO_GRUPO, NOME_CANAL, IDIOMA
    canal = canal_cfg.carregar()
    radar = canal.get("radar", {})
    NOME_CANAL = canal["nome"]
    IDIOMA = canal_cfg.idioma(canal)
    BUSCAS_NOTICIAS = radar.get("buscasNoticias") or [canal["categoria"]]
    BUSCAS_YOUTUBE = radar.get("buscasYoutube") or [canal["categoria"]]
    PESO_GRUPO = radar.get("pesoGrupo", {})
    arq_temas = RAIZ / radar.get("temas", "dados/temas/nenhum.json")
    animais = json.loads(arq_temas.read_text(encoding="utf-8")) if arq_temas.exists() else []
    if not animais:
        print(f"Aviso: sem lista de temas ({arq_temas.relative_to(RAIZ)}). "
              "O radar mostra notícias e vídeos, sem pontuar temas.")
    compilar_padroes(animais)
    hoje = date.today()

    wiki = coletar_wikipedia(animais)
    noticias = coletar_noticias(animais)
    trends, todos_trends = coletar_trends(animais)
    videos = coletar_youtube(animais)
    feitos = animais_ja_feitos(animais)

    ranking = pontuar(animais, wiki, noticias, trends, videos, feitos)

    PASTA_RADAR.mkdir(parents=True, exist_ok=True)
    md = PASTA_RADAR / f"{hoje:%Y-%m-%d}.md"
    md.write_text(escrever_md(hoje, ranking, noticias, trends, todos_trends, videos), encoding="utf-8")
    (PASTA_RADAR / f"{hoje:%Y-%m-%d}.json").write_text(
        json.dumps(
            {"data": hoje.isoformat(), "gerado": datetime.now().isoformat(timespec="minutes"),
             "ranking": ranking, "noticias": noticias, "trends": trends, "youtube": videos},
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
    print("\nTop 10:")
    for i, r in enumerate(ranking[:10], 1):
        print(f" {i:2}. {r['animal']:<20} {r['pontos']:>5}  {'; '.join(r['motivos'])}")
    print(f"\nRelatório: {md.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
