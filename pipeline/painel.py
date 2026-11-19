"""Painel do gerador de vídeos: interface local no navegador.

Uso:
    python -I pipeline/painel.py        (ou dê dois cliques em "Abrir painel.bat")

Abre http://localhost:8765. Só funciona neste computador (não fica na internet).
"""
import importlib.util
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
PORTA = 8765
SAIDA = RAIZ / "saida"
ROTEIROS = RAIZ / "roteiros"
RADAR = RAIZ / "dados" / "radar"
PUBLICADOS = RAIZ / "dados" / "publicados.json"
PAGINA = RAIZ / "painel" / "index.html"
NOME_SEGURO = re.compile(r"^[A-Za-z0-9._-]+$")
EXTENSOES_VIDEO = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
LIMITE_ENVIO = 4 * 1024**3  # 4 GB


def slugificar(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


# ---------------------------------------------------------------- tarefa em andamento
RE_RENDER = re.compile(r"Rendered (\d+)/(\d+)")
RE_ENCODE = re.compile(r"Encoded (\d+)/(\d+)")
RE_BUNDLE = re.compile(r"Bundling (\d+)%")
RE_TRECHO = re.compile(r"trecho (\d+)/(\d+)")
RE_ETAPA = re.compile(r"\[etapa (\d+)/(\d+)\] (.+)")
CODIGO_REINICIAR = 3  # "Abrir painel.bat" reabre o painel quando ele sai com este código
ETAPAS_RADAR = [("Wikipedia", "Wikipedia"), ("Google Notícias", "Google Notícias"),
                ("Google Trends", "Google Trends"), ("YouTube", "YouTube")]


class Tarefa:
    """Só uma tarefa por vez (radar ou geração de vídeo), com progresso lido do registro."""

    def __init__(self):
        self.lock = threading.Lock()
        self.tipo = self.alvo = self.inicio = self.codigo = None
        self.linhas = []
        self.rodando = False
        self.total_videos = 1
        self.avisos = []

    def iniciar(self, tipo, alvo, comando, total_videos=1, entrada=None, ao_terminar=None, continuar=False):
        """entrada: texto enviado ao programa (pedido ao Claude).
        ao_terminar: função que recebe a resposta final do Claude e devolve o resultado; se o resultado
        trouxer "seguir" (argumentos de iniciar), essa segunda tarefa começa logo em seguida.
        continuar: usado só nesse encadeamento (a tarefa anterior ainda conta como rodando)."""
        with self.lock:
            if self.rodando and not continuar:
                return False
            if not continuar:
                self.avisos = []
            self.tipo, self.alvo, self.linhas = tipo, alvo, []
            self.rodando, self.codigo, self.inicio = True, None, datetime.now()
            self.total_videos = total_videos
            self.video, self.nome_video, self.etapa, self.pct = 0, alvo, "Começando", 0.0
            self.resposta, self.resultado, self.ao_terminar = "", None, ao_terminar
            self.ferramentas = 0
        threading.Thread(target=self._rodar, args=(comando, entrada), daemon=True).start()
        return True

    def _evento_claude(self, linha):
        """Lê um evento do Claude (stream-json) e traduz para etapa/registro."""
        try:
            ev = json.loads(linha)
        except ValueError:
            return linha
        if ev.get("type") == "result":
            self.resposta = ev.get("result") or ""
            if ev.get("is_error"):
                return "Erro do Claude: " + self.resposta[:300]
            self.pct = 0.98
            return None
        if ev.get("type") != "assistant":
            return None
        textos = []
        for parte in ev.get("message", {}).get("content", []):
            if parte.get("type") != "tool_use":
                continue
            nome, entrada = parte.get("name", ""), parte.get("input", {})
            self.ferramentas += 1
            self.pct = min(0.9, 0.08 + 0.07 * self.ferramentas)
            alvo = Path(str(entrada.get("file_path") or entrada.get("path") or entrada.get("pattern") or "")).name
            if nome in ("Write", "Edit"):
                self.etapa = "Criando a lista de temas" if self.tipo == "temas" else "Escrevendo o roteiro"
                textos.append(f"Escrevendo {alvo}")
            elif nome in ("WebSearch", "WebFetch"):
                self.etapa = "Conferindo os fatos"
                textos.append("Pesquisando: " + str(entrada.get("query") or entrada.get("url") or "")[:90])
            else:
                if self.etapa == "Começando":
                    self.etapa = "Lendo o que funciona no canal"
                textos.append(f"Lendo {alvo}" if nome == "Read" else f"Procurando arquivos ({alvo or 'projeto'})")
        return "\n".join(textos) or None

    def _analisar(self, linha):
        """Atualiza etapa e porcentagem. Devolve True se a linha deve ir para o registro."""
        m = RE_ETAPA.match(linha)  # formato genérico: "[etapa 2/3] Instalando..."
        if m:
            self.etapa = m.group(3)
            self.pct = (int(m.group(1)) - 1) / int(m.group(2)) if m.group(3) != "Pronto" else 1.0
            return True
        if self.tipo == "radar":
            for i, (chave, nome) in enumerate(ETAPAS_RADAR):
                if linha.startswith(chave):
                    self.etapa, self.pct = f"Consultando {nome}", i / len(ETAPAS_RADAR)
            if linha.startswith("Relatório:"):
                self.etapa, self.pct = "Relatório pronto", 1.0
            return True
        m = re.search(r"=== (\S+) \((\w+)\) ===", linha)
        if m:
            self.video += 1
            self.nome_video = m.group(1)
            self.etapa, self.pct = "Começando", 0.0
        elif "Preparando o seu vídeo" in linha:
            self.etapa, self.pct = "Preparando o seu vídeo", 0.01
        elif "Gerando narração" in linha:
            self.etapa, self.pct = "Gravando a narração", 0.15 if self.tipo == "dublar" else 0.02
        elif "Narração pronta" in linha:
            self.pct = 0.10
        elif "Buscando clipes" in linha:
            self.etapa = "Baixando clipes do Pexels"
        elif (m := RE_TRECHO.search(linha)):
            self.pct = 0.10 + 0.25 * int(m.group(1)) / int(m.group(2))
        elif "Renderizando" in linha:
            self.etapa, self.pct = "Preparando a montagem", 0.35
        elif (m := RE_BUNDLE.search(linha)):
            self.pct = 0.35 + 0.03 * int(m.group(1)) / 100
            return False
        elif (m := RE_RENDER.search(linha)):
            self.etapa = "Montando o vídeo"
            self.pct = 0.38 + 0.57 * int(m.group(1)) / max(1, int(m.group(2)))
            return False
        elif (m := RE_ENCODE.search(linha)):
            self.etapa = "Finalizando o arquivo"
            self.pct = 0.95 + 0.04 * int(m.group(1)) / max(1, int(m.group(2)))
            return False
        elif "Gerando thumbnail" in linha:
            self.etapa, self.pct = "Criando a thumbnail", 0.99
        elif "Pronto!" in linha or "publicacao.txt atualizado" in linha:
            self.etapa, self.pct = "Pronto", 1.0
        return True

    def _rodar(self, comando, entrada):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        env.pop("CLAUDECODE", None)
        claude = self.tipo in ("ideias", "roteiro", "temas", "pronto")
        try:
            proc = subprocess.Popen(
                comando, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if entrada else subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if entrada:
                proc.stdin.write(entrada)
                proc.stdin.close()
            for linha in proc.stdout:
                linha = linha.strip()
                if not linha:
                    continue
                with self.lock:
                    if claude:
                        texto = self._evento_claude(linha)
                        if texto:
                            self.linhas.append(texto)
                    elif self._analisar(linha):
                        self.linhas.append(linha)
                    del self.linhas[:-400]
            self.codigo = proc.wait()
        except OSError as e:
            self.linhas.append(f"Erro ao iniciar: {e}")
            self.codigo = -1
        if self.codigo == 0 and self.ao_terminar:
            try:
                self.resultado = self.ao_terminar(self.resposta)
                self.etapa, self.pct = "Pronto", 1.0
            except Exception as e:  # resposta fora do formato esperado
                self.linhas.append(f"Não consegui usar a resposta do Claude: {e}")
                self.linhas.append(self.resposta[:600])
                self.codigo = 1
        seguir = self.resultado.pop("seguir", None) if self.codigo == 0 and isinstance(self.resultado, dict) else None
        if seguir:
            self.avisos = self.resultado.get("avisos") or []
            self.iniciar(**seguir, continuar=True)
            return
        self.rodando = False
        if self.tipo == "atualizar" and self.codigo == 0:
            # Sai com o código 3: o "Abrir painel.bat" entende como "reabrir" e sobe a versão nova.
            threading.Timer(2.5, os._exit, args=(CODIGO_REINICIAR,)).start()

    def estado(self):
        with self.lock:
            if not self.tipo:
                return {"tipo": None, "rodando": False}
            video = max(1, min(self.video, self.total_videos))
            geral = (video - 1 + self.pct) / self.total_videos if self.tipo == "gerar" else self.pct
            if not self.rodando and self.codigo == 0:
                geral = 1.0
            return {
                "tipo": self.tipo, "alvo": self.alvo, "rodando": self.rodando, "codigo": self.codigo,
                "inicio": self.inicio.strftime("%H:%M"),
                "minutos": round((datetime.now() - self.inicio).total_seconds() / 60, 1),
                "etapa": self.etapa, "video": video, "totalVideos": self.total_videos,
                "nomeVideo": self.nome_video, "pctVideo": round(self.pct * 100),
                "pctGeral": round(geral * 100), "linhas": self.linhas[-80:],
                "resultado": self.resultado, "avisos": self.avisos,
            }


TAREFA = Tarefa()


# ---------------------------------------------------------------- versão nova no GitHub
INICIO_SERVIDOR = datetime.now().isoformat(timespec="seconds")
ATUALIZACAO = {"git": False, "novidades": [], "remoto": None, "alterados": False, "verificado": None}
VERIFICAR_A_CADA = 6 * 3600  # segundos


def _git(*args, timeout=30):
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.strip() if r.returncode == 0 else None


def verificar_atualizacao():
    """Confere no GitHub se há commits novos (git fetch). Sem git ou sem internet, não mostra nada."""
    try:
        if not (RAIZ / ".git").exists() or not shutil.which("git") or not _git("rev-parse", "@{u}"):
            ATUALIZACAO.update(git=False)
            return
        _git("fetch", "--quiet", timeout=60)
        log = _git("log", "HEAD..@{u}", "--format=%h|%cd|%s", "--date=format:%d/%m") or ""
        novidades = [dict(zip(("id", "data", "texto"), l.split("|", 2))) for l in log.splitlines() if l]
        ATUALIZACAO.update(
            git=True, novidades=novidades, remoto=_git("rev-parse", "@{u}"),
            alterados=bool(_git("status", "--porcelain", "--untracked-files=no")),
            verificado=datetime.now().strftime("%d/%m %H:%M"))
    except (OSError, subprocess.SubprocessError):
        ATUALIZACAO.update(git=False)


_spec_tc = importlib.util.spec_from_file_location("titulos_canal", RAIZ / "pipeline" / "titulos_canal.py")
titulos_canal = importlib.util.module_from_spec(_spec_tc)
_spec_tc.loader.exec_module(titulos_canal)
SINCRONIA = {}  # última sincronização dos títulos do canal


def radar_diario():
    """Roda o radar sozinho uma vez por dia (não usa o Claude). Desligue com
    "radarAutomatico": false em dados/canal.json."""
    time.sleep(15)
    while True:
        canal = canal_cfg.carregar(obrigatorio=False)
        # títulos já publicados no canal (para o Claude não repetir perguntas), 1x por dia
        hoje_txt = datetime.now().strftime("%Y-%m-%d")
        if canal and canal.get("youtube") and SINCRONIA.get("dia") != hoje_txt:
            try:
                entraram, total = titulos_canal.sincronizar(canal["youtube"])
                SINCRONIA.update(dia=hoje_txt, total=total, novos=entraram, erro=None)
            except Exception as e:  # sem internet ou link errado: tenta de novo depois
                SINCRONIA.update(erro=str(e)[:120])
        hoje = RADAR / f"{datetime.now():%Y-%m-%d}.md"
        if canal and canal.get("radarAutomatico", True) and not hoje.exists() and not TAREFA.rodando:
            TAREFA.iniciar("radar", "radar", [sys.executable, "-I", "-u", "pipeline/radar.py"])
        time.sleep(3600)


def lembrete_medir():
    """True quando já dá para medir: há vídeo publicado (marcado no painel) há 7+ dias
    e nenhuma medição nos últimos 14 dias."""
    datas = []
    for d in ler_json(PUBLICADOS, {}).values():
        try:
            datas.append(datetime.strptime(d, "%d/%m/%Y"))
        except (TypeError, ValueError):
            pass
    if not datas or (datetime.now() - min(datas)).days < 7:
        return False
    medicoes = list((RAIZ / "dados" / "medicoes").glob("*.md"))
    if medicoes and (datetime.now() - datetime.fromtimestamp(max(m.stat().st_mtime for m in medicoes))).days < 14:
        return False
    return True


def vigiar_atualizacoes():
    while True:
        verificar_atualizacao()
        time.sleep(VERIFICAR_A_CADA)


_spec_canal = importlib.util.spec_from_file_location("canal", RAIZ / "pipeline" / "canal.py")
canal_cfg = importlib.util.module_from_spec(_spec_canal)
_spec_canal.loader.exec_module(canal_cfg)


# ---------------------------------------------------------------- Claude (pedir tema pelo painel)
IDEIAS = RAIZ / "dados" / "ultimas-ideias.json"


_spec_cli = importlib.util.spec_from_file_location("claude_cli", RAIZ / "pipeline" / "claude_cli.py")
claude_cli = importlib.util.module_from_spec(_spec_cli)
_spec_cli.loader.exec_module(claude_cli)
ler_env = claude_cli.ler_env
achar_claude = claude_cli.achar_claude


def comando_claude(ferramentas):
    exe = achar_claude()
    if not exe:
        return None
    modelo = ler_env().get("CLAUDE_MODELO", "sonnet")
    return [exe, "-p", "--output-format", "stream-json", "--verbose", "--model", modelo,
            "--allowedTools", *ferramentas]


def descricao_canal():
    """Contexto do canal (dados/canal.json) que vai no começo de todo pedido ao Claude."""
    c = canal_cfg.carregar(obrigatorio=False) or {}
    sobre = f" ({c['descricao']})" if c.get("descricao") else ""
    return (f'Você trabalha para o canal de YouTube "{c.get("nome", "")}", categoria '
            f'"{c.get("categoria", "")}"{sobre}. Vídeos em {lingua_canal()}, narrados por voz '
            "sintética sobre clipes do Pexels. A pasta atual é o projeto que gera os vídeos. "
            "Todo tema precisa ser da categoria do canal.")


def lingua_canal():
    """Língua dos vídeos, por extenso (ex.: 'inglês (Estados Unidos)')."""
    return canal_cfg.idioma(canal_cfg.carregar(obrigatorio=False))["lingua"]


APRENDIZADOS = ("Se existir, leia dados/aprendizados.md (o que funciona no canal) e siga a seção "
                "\"Regras do canal\", tirada dos números reais do canal. Leia também dados/videos-do-canal.json "
                "(todos os vídeos já publicados, com views) e historico.json, se existirem.")

PROMPT_IDEIAS = """{canal}

{aprendizados}

Pedido: {pedido}
{sinais}Formato desejado: {formato}

Sugira 3 ângulos diferentes para esse vídeo. Regras:
- Só temas da categoria do canal.
- Nunca repita uma pergunta que já está em dados/videos-do-canal.json ou historico.json (o vídeo repetido
  rende bem menos). O mesmo animal pode voltar, desde que com um fato ou pergunta diferente.
- Os 3 ângulos com formatos de título DIFERENTES entre si (ex.: afirmação surpreendente, comparação,
  verdade ou mito, pergunta). No máximo 1 deles começando com "Por que". 1 ou 2 palavras em MAIÚSCULA,
  até 70 caracteres. Respeite o que as Regras do canal disserem sobre formatos que rendem pouco.
- Duração: siga as Regras do canal; na dúvida, Short de até 60 s ("curto" ou "padrao").
- O gancho é a primeira frase da narração: abre a curiosidade sem entregar a resposta.
- Só fatos verdadeiros e conhecidos (serão conferidos depois).
- Escreva titulo, gancho e resumo em {lingua} (a língua dos vídeos); "porque" pode ser em português.
- Short: duracao "curto" (30-45 s, um fato), "padrao" (50-65 s) ou "longo" (75-120 s).
  Vídeo longo (horizontal, lista/contagem com capítulos que viram Shorts): duracao "video".

Responda SOMENTE com JSON válido, sem nenhum texto antes ou depois, neste formato:
{{"angulos": [{{"titulo": "...", "formato": "short ou longo", "duracao": "...", "gancho": "...", "resumo": "o que o vídeo conta, em 1-2 frases", "porque": "por que deve funcionar no canal"}}]}}
"""

PROMPT_ROTEIRO = """{canal}

Escreva o roteiro deste vídeo:
{angulo}
{obs}
Passos:
0. Confira em dados/videos-do-canal.json (se existir) que essa pergunta ainda não foi publicada no canal;
   se já foi, mude o ângulo (outro fato do mesmo animal) e ajuste o título.
1. Leia COMO-USAR.md, dados/canal.json, dados/aprendizados.md (se existir; siga as "Regras do canal",
   inclusive a duração) e o modelo de roteiro:
   {modelo}. Use exatamente a mesma estrutura de campos do modelo.
2. Confira os fatos principais com WebSearch. Se um fato não se confirmar, troque por outro verdadeiro.
   Coloque as fontes em publicacao.fontes.
3. "animal" (o assunto principal do vídeo, mesmo que não seja um animal), "busca" e "exigir"/"evitar"
   em inglês: são usados para achar clipes no Pexels, e a palavra precisa aparecer nos endereços dos
   vídeos. Em "exigir", use só palavras que não pertencem a outro assunto (ex.: camarão-louva-a-deus =
   ["shrimp"], nunca "mantis", que traria o inseto). Escolha assuntos que existam em vídeo de banco de
   imagens (nada de jogos, filmes, marcas ou pessoas famosas). Todo o resto (narração, tituloTela,
   título, descrição, hashtags, títulos dos capítulos) em {lingua}.
   Números e medidas: use o valor exato da fonte; na dúvida, deixe o número de fora.
4. Siga as regras de dados/aprendizados.md, se existir: não entregue a resposta nos primeiros 10 s,
   guarde o fato mais forte para o fim, frases curtas e faladas.
4b. {animacoes}
4c. Número simples (sem escala nem comparação) que merece destaque: em vez de "manim", pode usar o campo
   "grafico" (aparece por cima dos clipes; no máximo 2 por vídeo):
   número contando: {{"tipo": "numero", "valor": 80, "sufixo": " km/h", "rotulo": "velocidade do soco"}}
   comparação: {{"tipo": "comparacao", "rotulo": "comprimento", "unidade": "m",
                "itens": [{{"nome": "Humano", "valor": 1.7}}, {{"nome": "Baleia-azul", "valor": 30}}]}}
   (rótulos e nomes na língua do vídeo; números exatos da fonte; o último item da comparação fica destacado).
5. Salve em roteiros/<slug>.json. Slug curto, minúsculas, sem acento, com hífens, e que ainda não exista
   na pasta roteiros/.
6. Não rode o gerador de vídeo nem nenhum outro comando.

No final, responda SOMENTE com JSON: {{"slug": "..."}}
"""


ANIMACOES_MANIM = """Animações Manim (você decide se ajudam): uma cena animada ocupa a tela inteira no lugar
   dos clipes daquele trecho. Use SÓ onde um desenho explica melhor do que a filmagem: comparação de
   tamanho/peso/velocidade entre coisas, um número marcante que pede escala (velocidade, força,
   temperatura), uma linha do tempo, ou uma proporção/porcentagem. Se o texto não tiver nada disso, não use.
   No máximo 2 por Short (até 4 no vídeo longo); nunca no primeiro trecho (o gancho precisa da imagem do
   animal) nem em dois trechos seguidos. Números exatos do texto/da fonte; textos curtos, na língua do vídeo.
   No trecho escolhido, acrescente o campo "manim" em um destes formatos:
   comparacao (2 a 4 itens, do menor para o destaque, que fica por último):
     {"tipo": "comparacao", "rotulo": "Comprimento", "unidade": "m",
      "itens": [{"nome": "Pessoa", "valor": 1.7}, {"nome": "Ônibus", "valor": 12}, {"nome": "T-rex", "valor": 12.3}]}
   numero ("maximo" = fim da escala e "marca" = referência; os dois são opcionais):
     {"tipo": "numero", "valor": 20, "sufixo": " km/h", "rotulo": "Velocidade máxima do T-rex",
      "maximo": 40, "marca": {"nome": "Pessoa correndo", "valor": 25}}
   linha_do_tempo ("anos" = quanto tempo atrás):
     {"tipo": "linha_do_tempo", "unidade": "milhões de anos", "conclusao": "frase curta de fechamento",
      "eventos": [{"rotulo": "Estegossauro", "anos": 150}, {"rotulo": "T-rex", "anos": 66}, {"rotulo": "Hoje", "anos": 0}]}
   proporcao (valor em %):
     {"tipo": "proporcao", "valor": 66, "rotulo": "dos neurônios ficam nos braços"}
   Num trecho com "manim", não use "grafico". O trecho continua com "busca"/"exigir" (servem de reserva)."""

SEM_ANIMACOES = 'Animações: a pessoa pediu para não usar. Não acrescente "manim" nem "grafico"; ponha "animacoes": false no topo do JSON.'


PROMPT_PRONTO = """{canal}

A pessoa JÁ ESCREVEU o roteiro e quer que ele vire vídeo do jeito que está.
Roteiro da pessoa (entre as linhas ====):
====
{texto}
====
Formato: {formato}

Passos:
1. Leia o modelo de roteiro {modelo} e use exatamente a mesma estrutura de campos.
2. Narração ("texto" de cada trecho): use EXATAMENTE as palavras da pessoa, na mesma ordem. Não corrija,
   não resuma, não troque palavras e não acrescente nada (nem chamada para seguir o canal). Só divida em
   trechos de 1 a 3 frases (cada trecho vira uma cena). Pode tirar apenas o que claramente não é para
   ser falado: marcações como "[cena: ...]", "(pausa)", "Narrador:", emojis soltos.
   {regra_formato}
3. "animal" (o assunto principal, mesmo que não seja um animal), "busca" e "exigir"/"evitar" em inglês:
   servem para achar clipes no Pexels/Pixabay, e a palavra precisa aparecer nos endereços dos vídeos.
   Em "exigir", só palavras que não pertencem a outro assunto. Se o assunto costuma vir como brinquedo,
   desenho ou estátua (ex.: dinossauro), ponha "toy", "cartoon", "child" em "evitar".
4. Crie "tituloTela", "duracao" (pelo tamanho do texto: "curto" até ~45 s, "padrao" até ~65 s, "longo"
   acima disso; vídeo longo = "video") e "publicacao" (titulo, descricao, hashtags) na língua do roteiro,
   seguindo as "Regras do canal" de dados/aprendizados.md, se existir, para o título.
   "fontes": as que a pessoa citou no texto; senão, lista vazia.
5. No topo do JSON: "voz": "{voz}" e "formato": "{formato_json}".
5b. {animacoes}
6. Se algum fato do texto parecer errado ou muito duvidoso, NÃO mude o texto: anote em "avisos"
   (frases curtas, em português, dizendo qual trecho e por quê). Sem pesquisar na internet.
7. Salve em roteiros/<slug>.json. Slug curto, minúsculas, sem acento, com hífens, e que ainda não
   exista na pasta roteiros/.
8. Não rode o gerador de vídeo nem nenhum outro comando.

No final, responda SOMENTE com JSON: {{"slug": "...", "avisos": ["..."]}}
"""


PROMPT_TEMAS = """{canal}

Crie a lista de temas que o radar de tendências vai acompanhar para este canal.
Salve em {arquivo} uma lista JSON com 80 a 120 itens, neste formato (veja dados/temas/animais.json):
{{"pt": "nome em {lingua}, minúsculo (o campo se chama pt mesmo se a língua for outra)",
"en": "nome em inglês", "wiki_{wiki}": "título exato do artigo na Wikipedia em {lingua}",
"wiki_en": "título exato na Wikipedia em inglês", "grupo": "subgrupo curto",
"busca": ["termos em {lingua} para achar o tema em manchetes, com plural; nada de palavras com outro
sentido comum (ex.: em português, 'leão' também é a Receita Federal)"]}}
Temas concretos e populares, que têm artigo na Wikipedia e aparecem em notícias, variados dentro da categoria.
Não rode nenhum comando.

No final responda SOMENTE com JSON:
{{"buscasNoticias": ["5 ou 6 buscas curtas em {lingua} para o Google Notícias trazer novidades da categoria"],
 "buscasYoutube": ["5 buscas em {lingua} que achem vídeos da categoria no YouTube"]}}
"""


def ao_terminar_temas(arquivo):
    def tratar(resposta):
        temas = json.loads((RAIZ / arquivo).read_text(encoding="utf-8"))
        if not isinstance(temas, list) or len(temas) < 10 or not all("pt" in t and "busca" in t for t in temas):
            raise ValueError("a lista de temas veio incompleta")
        buscas = extrair_json(resposta)
        cfg = canal_cfg.carregar()
        for chave in ("buscasNoticias", "buscasYoutube"):
            if isinstance(buscas.get(chave), list) and buscas[chave]:
                cfg["radar"][chave] = [str(b) for b in buscas[chave]][:8]
        cfg["radar"]["temas"] = arquivo
        canal_cfg.salvar(cfg)
        return {"temas": len(temas)}
    return tratar


def extrair_json(texto):
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini < 0 or fim < ini:
        raise ValueError("a resposta não trouxe JSON")
    return json.loads(texto[ini : fim + 1])


def ao_terminar_ideias(pedido, formato):
    def tratar(resposta):
        dados = extrair_json(resposta)
        angulos = [a for a in dados.get("angulos", []) if a.get("titulo")]
        if not angulos:
            raise ValueError("nenhum ângulo na resposta")
        salvo = {"pedido": pedido, "formato": formato, "data": datetime.now().strftime("%d/%m %H:%M"),
                 "angulos": angulos}
        IDEIAS.write_text(json.dumps(salvo, ensure_ascii=False, indent=1), encoding="utf-8")
        return salvo
    return tratar


def ao_terminar_roteiro(resposta):
    slug = str(extrair_json(resposta).get("slug", ""))
    arq = ROTEIROS / f"{slug}.json"
    if not NOME_SEGURO.match(slug) or not arq.exists():
        raise ValueError(f"o roteiro '{slug}' não foi salvo")
    r = json.loads(arq.read_text(encoding="utf-8"))
    if not r.get("publicacao", {}).get("titulo") or not (r.get("segmentos") or r.get("capitulos")):
        raise ValueError("o roteiro salvo está incompleto")
    return {"slug": slug}


def ao_terminar_pronto(voz, formato, animacoes=True):
    """Confere o roteiro que o Claude montou e já encadeia a geração do vídeo."""
    def tratar(resposta):
        dados = extrair_json(resposta)
        slug = str(dados.get("slug", ""))
        arq = ROTEIROS / f"{slug}.json"
        if not NOME_SEGURO.match(slug) or not arq.exists():
            raise ValueError(f"o roteiro '{slug}' não foi salvo")
        r = json.loads(arq.read_text(encoding="utf-8"))
        if not r.get("publicacao", {}).get("titulo") or not (r.get("segmentos") or r.get("capitulos")):
            raise ValueError("o roteiro salvo está incompleto")
        r["voz"], r["formato"] = voz, formato  # garante o que a pessoa escolheu
        if not animacoes:
            r["animacoes"] = False
        if formato == "longo":
            for c in r.get("capitulos", []):
                c.pop("short", None)  # o texto é da pessoa: nada de Shorts extras
        avisos = [str(a)[:300] for a in (dados.get("avisos") or []) if str(a).strip()][:6]
        r["avisos"] = avisos
        arq.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cmd = [sys.executable, "-I", "-u", "pipeline/gerar_video.py", f"roteiros/{slug}.json"]
        return {"slug": slug, "avisos": avisos, "seguir": {"tipo": "gerar", "alvo": slug, "comando": cmd}}
    return tratar


def vozes_do_canal():
    lng = canal_cfg.idioma(canal_cfg.carregar(obrigatorio=False))
    return lng["vozes"], lng["amostra"]


AMOSTRAS = RAIZ / "trabalho" / "vozes"


def amostra_de_voz(voz):
    """mp3 curto com a voz, para a pessoa ouvir antes de escolher (fica guardado em trabalho/vozes)."""
    vozes, frase = vozes_do_canal()
    if voz not in {v["id"] for v in vozes}:
        return None
    arq = AMOSTRAS / f"{voz}.mp3"
    if arq.exists() and arq.stat().st_size > 1500:
        return arq
    AMOSTRAS.mkdir(parents=True, exist_ok=True)
    for _ in range(3):  # o serviço de voz às vezes falha; tenta de novo
        subprocess.run([sys.executable, "-I", "-m", "edge_tts", "--voice", voz, "--text", frase,
                        "--write-media", str(arq)], capture_output=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if arq.exists() and arq.stat().st_size > 1500:
            return arq
        time.sleep(1.5)
    return None


def texto_roteiro(r):
    """Narração em texto corrido, para revisar antes de gerar o vídeo."""
    if r.get("capitulos"):
        partes = []
        for c in r["capitulos"]:
            partes.append("## " + c.get("titulo", ""))
            partes += [s.get("texto", "") for s in c.get("segmentos", [])]
        return "\n".join(partes)
    return "\n".join(s.get("texto", "") for s in r.get("segmentos", []))


# ---------------------------------------------------------------- dados
def ler_json(caminho, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def ler_publicacao(pasta):
    """Separa o publicacao.txt nos blocos que a pessoa copia para o YouTube Studio."""
    arq = pasta / "publicacao.txt"
    if not arq.exists():
        return None
    t = arq.read_text(encoding="utf-8")

    def entre(inicio, fim):
        m = re.search(inicio + r"\n(.*?)(?:\n" + fim + r")", t, re.S)
        return m.group(1).strip() if m else ""

    duracao = (re.search(r"DURAÇÃO: (\S+)", t) or [None, ""])[1]
    if re.fullmatch(r"\d+(\.\d+)?", duracao):  # arquivos antigos: segundos ("36.9")
        s = round(float(duracao))
        duracao = f"{s // 60:02d}:{s % 60:02d}"
    return {
        "titulo": entre(r"^TÍTULO", r"\n"),
        "descricao": entre(r"=+ DESCRIÇÃO[^\n]*", r"={10,}"),
        "hashtags": entre(r"HASHTAGS COM #", r"\n"),
        "tags": entre(r"HASHTAGS SEM #[^\n]*", r"\n"),
        "duracao": duracao,
        "completo": t,
    }


def listar_videos():
    publicados = ler_json(PUBLICADOS, {})
    videos = []
    if SAIDA.exists():
        for pasta in sorted(SAIDA.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not pasta.is_dir() or not (pasta / "video.mp4").exists():
                continue
            roteiro = ler_json(ROTEIROS / f"{pasta.name}.json", {}) or ler_json(pasta / "info.json", {})
            pub = ler_publicacao(pasta) or {}
            videos.append({
                "pasta": pasta.name,
                "formato": roteiro.get("formato", "short"),
                "dublagem": roteiro.get("origem") == "dublagem",
                "titulo": pub.get("titulo") or pasta.name,
                "duracao": pub.get("duracao", ""),
                "thumbnail": (pasta / "thumbnail.png").exists(),
                "gerado": datetime.fromtimestamp((pasta / "video.mp4").stat().st_mtime).strftime("%d/%m %H:%M"),
                "publicado": publicados.get(pasta.name),
            })
    return videos


def listar_roteiros():
    lista = []
    for arq in sorted(ROTEIROS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        r = ler_json(arq, {})
        lista.append({
            "slug": arq.stem,
            "titulo": r.get("publicacao", {}).get("titulo", arq.stem),
            "formato": r.get("formato", "short"),
            "duracao": r.get("duracao", ""),
            "derivado": bool(r.get("origem")),
            "temShorts": any("short" in c for c in r.get("capitulos", [])),
            "pronto": (SAIDA / arq.stem / "video.mp4").exists(),
        })
    return lista


def listar_radar():
    return sorted((p.stem for p in RADAR.glob("*.md")), reverse=True) if RADAR.exists() else []


# ---------------------------------------------------------------- servidor
class Painel(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, dados, codigo=200, tipo="application/json; charset=utf-8"):
        corpo = dados if isinstance(dados, bytes) else json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def erro(self, msg, codigo=400):
        self.responder({"erro": msg}, codigo)

    def corpo_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def enviar_arquivo(self, arq):
        """Envia arquivo com suporte a Range (para o vídeo poder avançar/voltar)."""
        tamanho = arq.stat().st_size
        tipo = mimetypes.guess_type(arq.name)[0] or "application/octet-stream"
        ini, fim = 0, tamanho - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        parcial = bool(m)
        if m:
            if m.group(1):
                ini = int(m.group(1))
                fim = int(m.group(2)) if m.group(2) else fim
            elif m.group(2):
                ini = max(0, tamanho - int(m.group(2)))
            fim = min(fim, tamanho - 1)
            if ini > fim:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{tamanho}")
                self.end_headers()
                return
        self.send_response(206 if parcial else 200)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fim - ini + 1))
        if parcial:
            self.send_header("Content-Range", f"bytes {ini}-{fim}/{tamanho}")
        self.end_headers()
        try:
            with open(arq, "rb") as f:
                f.seek(ini)
                falta = fim - ini + 1
                while falta > 0:
                    bloco = f.read(min(1024 * 512, falta))
                    if not bloco:
                        break
                    self.wfile.write(bloco)
                    falta -= len(bloco)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass

    def do_GET(self):
        caminho = unquote(urlparse(self.path).path)
        partes = [p for p in caminho.split("/") if p]

        if caminho == "/":
            return self.responder(PAGINA.read_bytes(), tipo="text/html; charset=utf-8")
        if caminho == "/api/estado":
            return self.responder({
                "videos": listar_videos(), "roteiros": listar_roteiros(),
                "radar": listar_radar(), "tarefa": TAREFA.estado(), "claude": bool(achar_claude()),
                "canal": canal_cfg.carregar(obrigatorio=False), "categorias": canal_cfg.CATEGORIAS,
                "idiomas": {k: v["nome"] for k, v in canal_cfg.IDIOMAS.items()},
                "lembreteMedir": lembrete_medir(),
                "titulosGuardados": len(titulos_canal.ler()),
                "vozes": vozes_do_canal()[0],
                "medicoes": sorted((p.stem for p in (RAIZ / "dados" / "medicoes").glob("*.md")), reverse=True),
            })
        if len(partes) == 3 and partes[:2] == ["api", "medicao"] and NOME_SEGURO.match(partes[2]):
            arq = RAIZ / "dados" / "medicoes" / f"{partes[2]}.md"
            if arq.exists():
                return self.responder({"md": arq.read_text(encoding="utf-8")})
            return self.erro("relatório não encontrado", 404)
        if caminho == "/api/atualizacao":
            return self.responder({**ATUALIZACAO, "inicioServidor": INICIO_SERVIDOR})
        if caminho == "/api/voz-amostra":
            voz = parse_qs(urlparse(self.path).query).get("voz", [""])[0]
            arq = amostra_de_voz(voz)
            if not arq:
                return self.erro("não consegui gerar a amostra agora; tente de novo", 503)
            return self.enviar_arquivo(arq)
        if caminho == "/api/tarefa":
            return self.responder(TAREFA.estado())
        if caminho == "/api/ideias":
            return self.responder(ler_json(IDEIAS, {}))
        if len(partes) == 3 and partes[:2] == ["api", "roteiro"] and NOME_SEGURO.match(partes[2]):
            r = ler_json(ROTEIROS / f"{partes[2]}.json", None)
            if r is None:
                return self.erro("roteiro não encontrado", 404)
            return self.responder({"slug": partes[2], "titulo": r.get("publicacao", {}).get("titulo", ""),
                                   "formato": r.get("formato"), "duracao": r.get("duracao"),
                                   "texto": texto_roteiro(r),
                                   "fontes": r.get("publicacao", {}).get("fontes", [])})
        if len(partes) == 3 and partes[:2] == ["api", "publicacao"] and NOME_SEGURO.match(partes[2]):
            pasta = SAIDA / partes[2]
            pub = ler_publicacao(pasta)
            if not pub:
                return self.erro("sem publicacao.txt", 404)
            pub["traducoes"] = ler_json(pasta / "traducoes.json", {})
            pub["legendas"] = sorted(p.name for p in pasta.glob("legenda.*.srt"))
            pub["temNarracao"] = (RAIZ / "public" / "projetos" / partes[2] / "props.json").exists() and \
                bool(ler_json(RAIZ / "public" / "projetos" / partes[2] / "props.json", {}).get("palavras"))
            return self.responder(pub)
        if len(partes) == 3 and partes[:2] == ["api", "radar"] and NOME_SEGURO.match(partes[2]):
            arq = RADAR / f"{partes[2]}.md"
            if arq.exists():
                dados_radar = ler_json(arq.with_suffix(".json"), {})
                return self.responder({"md": arq.read_text(encoding="utf-8"),
                                       "ranking": dados_radar.get("ranking", [])[:12]})
            return self.erro("relatório não encontrado", 404)
        if len(partes) == 3 and partes[0] == "arquivo" and all(NOME_SEGURO.match(p) for p in partes[1:]):
            arq = SAIDA / partes[1] / partes[2]
            if arq.is_file():
                return self.enviar_arquivo(arq)
        self.erro("não encontrado", 404)

    def receber_medicao(self, query):
        """Recebe a exportação do YouTube Studio (.zip ou .csv) e roda a análise."""
        if TAREFA.rodando:
            return self.erro("já tem uma tarefa rodando; espere terminar", 409)
        ext = Path(query.get("nome", ["x.zip"])[0]).suffix.lower()
        if ext not in (".zip", ".csv"):
            return self.erro("envie o arquivo .zip (ou .csv) exportado do YouTube Studio")
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not 0 < tamanho <= 50 * 1024 * 1024:
            return self.erro("arquivo vazio ou grande demais (máximo 50 MB)")
        pasta = RAIZ / "dados" / "medicoes"
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"exportacao-{datetime.now():%Y%m%d-%H%M%S}{ext}"
        destino.write_bytes(self.rfile.read(tamanho))
        ok = TAREFA.iniciar("medir", "resultados", [sys.executable, "-I", "-u", "pipeline/medir.py", str(destino)])
        return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando", 409)

    def receber_video(self, query):
        """Recebe o vídeo enviado pela página (corpo = o próprio arquivo) e devolve o slug."""
        if TAREFA.rodando:
            return self.erro("já tem uma tarefa rodando; espere terminar", 409)
        ext = (query.get("ext", [".mp4"])[0] or ".mp4").lower()
        if ext not in EXTENSOES_VIDEO:
            return self.erro("formato de vídeo não aceito (use mp4, mov, webm, mkv, avi ou m4v)")
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not 0 < tamanho <= LIMITE_ENVIO:
            return self.erro("o vídeo precisa ter até 4 GB")
        base = slugificar(query.get("titulo", [""])[0]) or "meu-video"
        slug = f"{base[:40]}-{datetime.now():%Y%m%d-%H%M%S}"
        pasta = RAIZ / "public" / "projetos" / slug
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"original{ext}"
        falta = tamanho
        try:
            with open(destino, "wb") as f:
                while falta > 0:
                    bloco = self.rfile.read(min(1024 * 1024, falta))
                    if not bloco:
                        break
                    f.write(bloco)
                    falta -= len(bloco)
        except (ConnectionResetError, ConnectionAbortedError):
            falta = 1
        if falta > 0:
            shutil.rmtree(pasta, ignore_errors=True)
            return self.erro("o envio foi interrompido; tente de novo")
        return self.responder({"slug": slug})

    def do_POST(self):
        if self.headers.get("Origin") not in (None, f"http://localhost:{PORTA}", f"http://127.0.0.1:{PORTA}"):
            return self.erro("origem não permitida", 403)
        url = urlparse(self.path)
        caminho = url.path
        py = [sys.executable, "-I", "-u"]

        if caminho == "/api/enviar-video":
            return self.receber_video(parse_qs(url.query))
        if caminho == "/api/medicao":
            return self.receber_medicao(parse_qs(url.query))

        dados = self.corpo_json()

        if caminho == "/api/dublar":
            slug = str(dados.get("slug", ""))
            pasta = RAIZ / "public" / "projetos" / slug
            if not NOME_SEGURO.match(slug) or not any(pasta.glob("original.*")):
                return self.erro("envie o vídeo primeiro", 400)
            texto = str(dados.get("texto", "")).strip()
            if not texto:
                return self.erro("cole o roteiro da narração", 400)
            cfg = {
                "texto": texto[:20000],
                "titulo": str(dados.get("titulo", "")).strip()[:100],
                "descricao": str(dados.get("descricao", "")).strip()[:4000],
                "somOriginal": dados.get("somOriginal") if dados.get("somOriginal") in ("sem", "baixo", "normal") else "baixo",
                "legendas": bool(dados.get("legendas", True)),
                "musica": bool(dados.get("musica", False)),
                "ate": "narracao" if dados.get("ate") == "narracao" else "video",
            }
            (pasta / "dublagem.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
            ok = TAREFA.iniciar("dublar", slug, py + ["pipeline/dublar.py", slug])
            return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando", 409)

        if caminho == "/api/traduzir":
            pasta = str(dados.get("pasta", ""))
            if not NOME_SEGURO.match(pasta) or not (SAIDA / pasta / "video.mp4").exists():
                return self.erro("vídeo não encontrado", 404)
            ok = TAREFA.iniciar("traduzir", pasta, py + ["pipeline/traduzir.py", pasta])
            return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando", 409)

        if caminho == "/api/atualizar":
            if not ATUALIZACAO["git"]:
                return self.erro("este app não foi baixado com git; baixe de novo pelo GitHub")
            if ATUALIZACAO["alterados"]:
                return self.erro("você mudou arquivos do app; peça ao Claude Code para atualizar "
                                 "mantendo suas mudanças (git pull)")
            ok = TAREFA.iniciar("atualizar", "app", py + ["pipeline/atualizar.py"])
            return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando; espere terminar", 409)

        if caminho == "/api/radar":
            ok = TAREFA.iniciar("radar", "radar", py + ["pipeline/radar.py"])
            return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando", 409)

        if caminho == "/api/gerar":
            slug = str(dados.get("slug", ""))
            if not NOME_SEGURO.match(slug) or not (ROTEIROS / f"{slug}.json").exists():
                return self.erro("roteiro não encontrado", 404)
            cmd = py + ["pipeline/gerar_video.py", f"roteiros/{slug}.json"]
            if dados.get("semShorts"):
                cmd.append("--sem-shorts")
            if dados.get("soPublicacao"):
                cmd.append("--so-publicacao")
            total = 1
            roteiro = ler_json(ROTEIROS / f"{slug}.json", {})
            if roteiro.get("formato") == "longo" and not dados.get("semShorts") and not dados.get("soPublicacao"):
                total += sum("short" in c for c in roteiro.get("capitulos", []))
            ok = TAREFA.iniciar("gerar", slug, cmd, total_videos=total)
            return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando", 409)

        if caminho == "/api/configurar":
            nome = str(dados.get("nome", "")).strip()[:80]
            categoria = str(dados.get("categoria", "")).strip()[:80]
            if not nome or not categoria:
                return self.erro("informe o nome do canal e a categoria")
            atual = canal_cfg.carregar(obrigatorio=False) or {}
            lingua = dados.get("idioma") if dados.get("idioma") in canal_cfg.IDIOMAS else canal_cfg.IDIOMA_PADRAO
            cfg = canal_cfg.montar(nome, categoria, str(dados.get("descricao", ""))[:200], lingua)
            youtube = str(dados.get("youtube", "")).strip()[:200]
            if youtube:
                cfg["youtube"] = youtube
                SINCRONIA.clear()  # link novo: sincroniza os títulos na próxima volta
                threading.Thread(target=lambda: SINCRONIA.update(
                    zip(("novos", "total"), titulos_canal.sincronizar(youtube)), dia=datetime.now().strftime("%Y-%m-%d")),
                    daemon=True).start()
            elif atual.get("youtube"):
                cfg["youtube"] = atual["youtube"]
            if atual.get("categoria") == categoria and atual.get("idioma", canal_cfg.IDIOMA_PADRAO) == lingua:
                # mesma categoria e língua: mantém o radar, os horários e as voz/hashtags já ajustados
                manter = ["radar", "horarios", "voz", "hashtagsFim"]
                if atual.get("nome") == nome:  # mesmo nome: mantém também as chamadas personalizadas
                    manter += ["chamada", "chamadaFinal", "pergunta", "avisoIA", "hashtagsInicio"]
                for chave in manter:
                    if chave in atual:
                        cfg[chave] = atual[chave]
            canal_cfg.salvar(cfg)
            arquivo = cfg["radar"]["temas"]
            criar = not (RAIZ / arquivo).exists() and achar_claude() is not None and not TAREFA.rodando
            if criar:
                (RAIZ / arquivo).parent.mkdir(parents=True, exist_ok=True)
                cmd = comando_claude(["Read", "Glob", f"Write({arquivo})"])
                prompt = PROMPT_TEMAS.format(canal=descricao_canal(), arquivo=arquivo, lingua=lingua_canal(),
                                             wiki=canal_cfg.idioma(cfg)["wiki"])
                TAREFA.iniciar("temas", categoria, cmd, entrada=prompt, ao_terminar=ao_terminar_temas(arquivo))
            return self.responder({"ok": True, "criandoTemas": criar})

        if caminho == "/api/ideias":
            pedido = str(dados.get("pedido", "")).strip()[:600]
            formato = {"short": "Short (vertical)", "longo": "vídeo longo horizontal + Shorts"}.get(
                dados.get("formato"), "escolha o melhor (Short ou vídeo longo)")
            if not pedido:
                return self.erro("escreva sobre o que é o vídeo")
            cmd = comando_claude(["Read", "Glob", "Grep"])
            if not cmd:
                return self.erro("não achei o Claude Code neste computador", 500)
            sinais = str(dados.get("sinais", "")).strip()[:600]
            prompt = PROMPT_IDEIAS.format(canal=descricao_canal(), aprendizados=APRENDIZADOS, lingua=lingua_canal(), pedido=pedido, formato=formato,
                                          sinais=f"Sinais do radar: {sinais}\n" if sinais else "")
            ok = TAREFA.iniciar("ideias", pedido, cmd, entrada=prompt,
                                ao_terminar=ao_terminar_ideias(pedido, dados.get("formato")))
            return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando", 409)

        if caminho == "/api/escrever":
            angulo = dados.get("angulo")
            if not isinstance(angulo, dict) or not angulo.get("titulo"):
                return self.erro("escolha um ângulo")
            cmd = comando_claude(["Read", "Glob", "Grep", "WebSearch", "WebFetch",
                                  "Write(roteiros/**)", "Edit(roteiros/**)"])
            if not cmd:
                return self.erro("não achei o Claude Code neste computador", 500)
            longo = angulo.get("formato") == "longo"
            modelo = ("exemplos/longo-exemplo.json (vídeo longo com capítulos e blocos short)"
                      if longo else "exemplos/short-exemplo.json (Short)")
            obs = str(dados.get("obs", "")).strip()[:600]
            prompt = PROMPT_ROTEIRO.format(
                canal=descricao_canal(), modelo=modelo, lingua=lingua_canal(), animacoes=ANIMACOES_MANIM,
                angulo=json.dumps({k: angulo.get(k) for k in ("titulo", "formato", "duracao", "gancho", "resumo")},
                                  ensure_ascii=False, indent=1),
                obs=f"Observações do usuário: {obs}\n" if obs else "")
            ok = TAREFA.iniciar("roteiro", angulo["titulo"], cmd, entrada=prompt, ao_terminar=ao_terminar_roteiro)
            return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando", 409)

        if caminho == "/api/roteiro-pronto":
            texto = str(dados.get("texto", "")).strip()
            if len(texto.split()) < 15:
                return self.erro("cole o roteiro inteiro (pelo menos algumas frases)")
            formato = "longo" if dados.get("formato") == "longo" else "short"
            vozes = vozes_do_canal()[0]
            voz = dados.get("voz") if dados.get("voz") in {v["id"] for v in vozes} else vozes[0]["id"]
            cmd = comando_claude(["Read", "Glob", "Grep", "Write(roteiros/**)", "Edit(roteiros/**)"])
            if not cmd:
                return self.erro("não achei o Claude Code neste computador", 500)
            longo = formato == "longo"
            prompt = PROMPT_PRONTO.format(
                canal=descricao_canal(), texto=texto[:30000], voz=voz, formato_json=formato,
                animacoes=ANIMACOES_MANIM if dados.get("animacoes", True) else SEM_ANIMACOES,
                formato=("vídeo longo horizontal (16:9)" if longo else "Short vertical (9:16)"),
                modelo=("exemplos/longo-exemplo.json (vídeo longo com capítulos)" if longo
                        else "exemplos/short-exemplo.json (Short)"),
                regra_formato=('Vídeo longo: organize em "capitulos". Se o texto tiver títulos de partes, '
                               "eles viram os títulos dos capítulos (e não são falados); senão, crie capítulos "
                               'curtos pelo assunto. NÃO crie blocos "short".' if longo else
                               'Short: tudo em "segmentos", sem capítulos.'))
            primeira = re.sub(r"\s+", " ", texto)[:60]
            ok = TAREFA.iniciar("pronto", primeira, cmd, entrada=prompt,
                                ao_terminar=ao_terminar_pronto(voz, formato, bool(dados.get("animacoes", True))))
            return self.responder({"ok": ok}) if ok else self.erro("já tem uma tarefa rodando", 409)

        if caminho == "/api/publicado":
            pasta = str(dados.get("pasta", ""))
            if not NOME_SEGURO.match(pasta):
                return self.erro("pasta inválida")
            pubs = ler_json(PUBLICADOS, {})
            if dados.get("publicado"):
                pubs[pasta] = datetime.now().strftime("%d/%m/%Y")
            else:
                pubs.pop(pasta, None)
            PUBLICADOS.write_text(json.dumps(pubs, ensure_ascii=False, indent=1), encoding="utf-8")
            return self.responder({"ok": True})

        if caminho == "/api/abrir-pasta":
            pasta = str(dados.get("pasta", ""))
            alvo = SAIDA / pasta if pasta and NOME_SEGURO.match(pasta) else SAIDA
            if alvo.is_dir() and hasattr(os, "startfile"):
                os.startfile(alvo)
                return self.responder({"ok": True})
            return self.erro("pasta não encontrada", 404)

        self.erro("não encontrado", 404)


def main():
    global PORTA
    for arg in sys.argv[1:]:
        if arg.startswith("--porta="):
            PORTA = int(arg.split("=", 1)[1])
    abrir = "--sem-navegador" not in sys.argv
    url = f"http://localhost:{PORTA}"
    # Se o painel já está aberto em outra janela, só abre o navegador.
    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", PORTA)) == 0:
            print(f"O painel já está rodando em {url}")
            if abrir:
                webbrowser.open(url)
            return
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Painel)
    print(f"Painel aberto em {url}  (feche esta janela para desligar)", flush=True)
    threading.Thread(target=vigiar_atualizacoes, daemon=True).start()
    threading.Thread(target=radar_diario, daemon=True).start()
    if abrir:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
