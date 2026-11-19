"""Configuração do canal de quem usa o sistema (nome, categoria e o que o radar acompanha).

Fica em dados/canal.json (não vai para o GitHub: cada pessoa tem o seu).
Na primeira vez, o painel pede o nome e a categoria; ou rode:
    python -I pipeline/canal.py
"""
import json
import sys
import unicodedata
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "dados" / "canal.json"

# Categorias com radar pronto. As outras usam termos gerais e, se o Claude Code estiver
# instalado, ele cria a lista de temas da categoria (dados/temas/<categoria>.json).
PREDEFINIDAS = {
    "Animais e natureza": {
        "temas": "dados/temas/animais.json",
        "hashtagsFim": ["curiosidadessobreanimais", "curiosidadesanimais", "mundoanimal",
                        "biologia", "animais", "vocesabia"],
        "buscasNoticias": ['"nova espécie"', "animal cientistas", "animais descoberta",
                           "biólogos animal", "zoológico filhote", "comportamento animal estudo"],
        "buscasYoutube": ["curiosidades animais", "animais incríveis", "mundo animal",
                          "você sabia animais", "animais selvagens"],
        # retenção por grupo de animal (ajuste com os dados do seu canal)
        "pesoGrupo": {"savana": 1.15, "marinho": 1.15, "ave": 1.1, "inseto": 0.95,
                      "pet": 0.85, "fazenda": 0.8},
    },
}
# Língua dos vídeos: voz da narração, textos que vão na descrição e região do radar.
# (O painel continua em português.)
IDIOMAS = {
    "pt-BR": {
        "nome": "Português (Brasil)", "lingua": "português do Brasil",
        "voz": "pt-BR-FranciscaNeural", "wiki": "pt",
        "vozes": [{"id": "pt-BR-FranciscaNeural", "nome": "Francisca", "tipo": "feminina"},
                  {"id": "pt-BR-AntonioNeural", "nome": "Antônio", "tipo": "masculina"},
                  {"id": "pt-BR-ThalitaMultilingualNeural", "nome": "Thalita", "tipo": "feminina, mais jovem"}],
        "amostra": "Oi! Eu posso narrar os seus vídeos. Você sabia que o polvo tem três corações?",
        "noticias": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"}, "trends": "BR",
        "youtube": {"hl": "pt", "gl": "BR"},
        "textos": {
            "capitulos": "⏱️ Capítulos:", "fontes": "📚 Fontes:",
            "videoCompleto": "▶️ Vídeo completo no canal: {titulo}",
            "avisoIA": "Narração com voz sintética. Imagens: Pexels (uso gratuito).",
            "avisoDublagem": "Narração com voz sintética.",
            "chamada": "🔔 Inscreva-se no {nome} para mais vídeos sobre {sobre}.",
            "chamadaFinal": "Segue o {nome} para mais vídeos como este.",
            "pergunta": "💬 Você já sabia disso? Conta aqui nos comentários!",
            "relaxPergunta": "💬 Qual som você mais gosta para dormir? Conta aqui nos comentários!",
            "relaxAviso": "Sons de natureza gerados por computador. Imagens: Pexels (uso gratuito).",
        },
    },
    "en-US": {
        "nome": "English", "lingua": "inglês (Estados Unidos)",
        "voz": "en-US-JennyNeural", "wiki": "en",
        "vozes": [{"id": "en-US-JennyNeural", "nome": "Jenny", "tipo": "feminina"},
                  {"id": "en-US-AriaNeural", "nome": "Aria", "tipo": "feminina"},
                  {"id": "en-US-GuyNeural", "nome": "Guy", "tipo": "masculina"},
                  {"id": "en-US-AndrewNeural", "nome": "Andrew", "tipo": "masculina"}],
        "amostra": "Hi! I can narrate your videos. Did you know an octopus has three hearts?",
        "noticias": {"hl": "en-US", "gl": "US", "ceid": "US:en"}, "trends": "US",
        "youtube": {"hl": "en", "gl": "US"},
        "textos": {
            "capitulos": "⏱️ Chapters:", "fontes": "📚 Sources:",
            "videoCompleto": "▶️ Full video on the channel: {titulo}",
            "avisoIA": "Synthetic voice narration. Footage: Pexels (free to use).",
            "avisoDublagem": "Synthetic voice narration.",
            "chamada": "🔔 Subscribe to {nome} for more videos about {sobre}.",
            "chamadaFinal": "Follow {nome} for more videos like this.",
            "pergunta": "💬 Did you know that? Tell us in the comments!",
            "relaxPergunta": "💬 Which sound helps you sleep best? Tell us in the comments!",
            "relaxAviso": "Computer-generated nature sounds. Footage: Pexels (free to use).",
        },
    },
    "es-MX": {
        "nome": "Español", "lingua": "espanhol (América Latina)",
        "voz": "es-MX-DaliaNeural", "wiki": "es",
        "vozes": [{"id": "es-MX-DaliaNeural", "nome": "Dalia", "tipo": "feminina"},
                  {"id": "es-MX-JorgeNeural", "nome": "Jorge", "tipo": "masculina"}],
        "amostra": "¡Hola! Puedo narrar tus videos. ¿Sabías que el pulpo tiene tres corazones?",
        "noticias": {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}, "trends": "MX",
        "youtube": {"hl": "es", "gl": "MX"},
        "textos": {
            "capitulos": "⏱️ Capítulos:", "fontes": "📚 Fuentes:",
            "videoCompleto": "▶️ Video completo en el canal: {titulo}",
            "avisoIA": "Narración con voz sintética. Imágenes: Pexels (uso gratuito).",
            "avisoDublagem": "Narración con voz sintética.",
            "chamada": "🔔 Suscríbete a {nome} para más videos sobre {sobre}.",
            "chamadaFinal": "Sigue a {nome} para más videos como este.",
            "pergunta": "💬 ¿Ya lo sabías? ¡Cuéntanos en los comentarios!",
            "relaxPergunta": "💬 ¿Qué sonido te ayuda más a dormir? ¡Cuéntanos en los comentarios!",
            "relaxAviso": "Sonidos de naturaleza generados por computadora. Imágenes: Pexels (uso gratuito).",
        },
    },
}
IDIOMA_PADRAO = "pt-BR"

# Orientação de horário para quem ainda não colocou os dados do próprio público.
HORARIOS_PADRAO = [
    "Publique cerca de 1 a 2 horas antes do horário em que o seu público mais assiste.",
    'Veja em YouTube Studio > Estatísticas > Público > "Quando seus espectadores estão no YouTube".',
    "Sem dados ainda? Teste o fim da tarde (17h–19h) em dias de semana e as 10h no fim de semana,",
    "no fuso horário do seu público. Depois, troque estas linhas em dados/canal.json (\"horarios\").",
]


def idioma(cfg):
    """Dados da língua do canal (padrão: português do Brasil)."""
    return IDIOMAS.get((cfg or {}).get("idioma"), IDIOMAS[IDIOMA_PADRAO])


def texto(cfg, chave, **valores):
    """Texto da descrição na língua do canal (ex.: texto(cfg, 'fontes'))."""
    return idioma(cfg)["textos"][chave].format(**valores)


CATEGORIAS = ["Animais e natureza", "Ciência e espaço", "História", "Curiosidades gerais",
              "Culinária", "Viagem e lugares", "Tecnologia", "Esportes", "Saúde e bem-estar",
              "Sons relaxantes"]


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def montar(nome, categoria, descricao="", lingua=IDIOMA_PADRAO):
    """Cria a configuração completa a partir de nome + categoria + língua dos vídeos."""
    nome, categoria, descricao = nome.strip(), categoria.strip(), descricao.strip()
    lingua = lingua if lingua in IDIOMAS else IDIOMA_PADRAO
    lng = IDIOMAS[lingua]
    # As listas prontas (ex.: 133 animais) estão em português: só valem para pt-BR.
    pre = PREDEFINIDAS.get(categoria, {}) if lingua == IDIOMA_PADRAO else {}
    tag_cat = re.sub(r"[^a-z0-9]", "", slug(categoria))
    sobre = descricao or categoria.lower()
    sufixo = "" if lingua == IDIOMA_PADRAO else f"-{lingua.lower()}"
    t = lng["textos"]
    return {
        "nome": nome,
        "categoria": categoria,
        "descricao": descricao,
        "idioma": lingua,
        "voz": lng["voz"],
        "hashtagsInicio": [re.sub(r"[^a-z0-9]", "", slug(nome))],
        "hashtagsFim": pre.get("hashtagsFim", [tag_cat]),
        "chamada": t["chamada"].format(nome=nome, sobre=sobre),
        "chamadaFinal": t["chamadaFinal"].format(nome=nome),
        "pergunta": t["pergunta"],
        "avisoIA": t["avisoIA"],
        "horarios": HORARIOS_PADRAO,
        "radar": {
            "temas": pre.get("temas", f"dados/temas/{slug(categoria)}{sufixo}.json"),
            "buscasNoticias": pre.get("buscasNoticias", [categoria, f"{categoria} descoberta",
                                                         f"{categoria} estudo", f"{categoria} curiosidade"]),
            "buscasYoutube": pre.get("buscasYoutube", [f"curiosidades {categoria}", categoria,
                                                       f"você sabia {categoria}"]),
            "pesoGrupo": pre.get("pesoGrupo", {}),
        },
    }


def carregar(obrigatorio=True):
    """Lê dados/canal.json. Sem ele, explica como configurar e encerra."""
    if ARQUIVO.exists():
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    if obrigatorio:
        sys.exit("Canal ainda não configurado. Abra o painel (Abrir painel.bat) ou rode: "
                 "python -I pipeline/canal.py")
    return None


def salvar(cfg):
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("Configurar o canal\n")
    nome = input("Nome do canal no YouTube: ").strip()
    print("\nCategorias:")
    for i, c in enumerate(CATEGORIAS, 1):
        print(f"  {i}. {c}")
    escolha = input("Número da categoria (ou escreva outra): ").strip()
    categoria = CATEGORIAS[int(escolha) - 1] if escolha.isdigit() and 0 < int(escolha) <= len(CATEGORIAS) else escolha
    descricao = input("Em uma frase, sobre o que é o canal? (opcional): ").strip()
    print("\nLíngua dos vídeos:")
    codigos = list(IDIOMAS)
    for i, c in enumerate(codigos, 1):
        print(f"  {i}. {IDIOMAS[c]['nome']}")
    escolha = input("Número da língua [1]: ").strip() or "1"
    lingua = codigos[int(escolha) - 1] if escolha.isdigit() and 0 < int(escolha) <= len(codigos) else IDIOMA_PADRAO
    if not nome or not categoria:
        sys.exit("Nome e categoria são obrigatórios.")
    salvar(montar(nome, categoria, descricao, lingua))
    print(f"\nPronto! Configuração salva em {ARQUIVO.relative_to(RAIZ)}.")
