"""Cenas animadas com Manim, prontas para entrar no lugar de um clipe (campo "manim" de um trecho).

O gerador (pipeline/gerar_video.py) grava os dados da cena num JSON e roda:
    python -I -m manim render -qh --fps 30 -r 1080,1920 pipeline/cenas_manim.py CenaRoteiro
com a variável CENA_MANIM apontando para esse JSON. A cena dura exatamente "duracao" segundos.

Tipos (os textos vêm na língua do vídeo):
  comparacao     {"rotulo": "Comprimento", "unidade": "m", "itens": [{"nome": "Ônibus", "valor": 12}, ...]}
  numero         {"valor": 20, "sufixo": " km/h", "rotulo": "Velocidade máxima", "maximo": 40,
                  "marca": {"nome": "Pessoa correndo", "valor": 25}}            (maximo e marca: opcionais)
  linha_do_tempo {"unidade": "milhões de anos", "conclusao": "...",
                  "eventos": [{"rotulo": "Estegossauro", "anos": 150}, {"rotulo": "T-rex", "anos": 66},
                              {"rotulo": "Hoje", "anos": 0}]}
  proporcao      {"valor": 66, "rotulo": "dos neurônios ficam nos braços"}       (valor em %)
No Short, o meio da tela fica livre para a legenda; no vídeo longo, a parte de baixo.
"""
import json
import os
import textwrap

import numpy as np

from manim import (BOLD, DOWN, LEFT, RIGHT, UP, Arc, Brace, Circumscribe, Create, Dot, FadeIn,
                   LaggedStart, Line, RoundedRectangle, Scene, Square, Text, ValueTracker,
                   VGroup, Write, always_redraw, config, smooth)

DADOS = json.loads(open(os.environ["CENA_MANIM"], encoding="utf-8").read())
CURTO = DADOS.get("formato", "short") == "short"
IDIOMA = DADOS.get("idioma", "pt-BR")

if CURTO:
    config.pixel_width, config.pixel_height = 1080, 1920
    config.frame_width, config.frame_height = 9, 16
else:
    config.pixel_width, config.pixel_height = 1920, 1080
    config.frame_width, config.frame_height = 16, 9
config.background_color = "#0B2233"

FONTE = "Segoe UI"
CREME, AMARELO, AZUL, AZUL_CLARO, APAGADO = "#F4E9D8", "#FFC94D", "#4A90C2", "#A9D3EE", "#284459"
# Áreas livres (fora da legenda): no Short, em cima (A) e embaixo (B) do meio; no longo, tudo acima do rodapé.
TOPO = 5.9 if CURTO else 3.55
A = 3.6 if CURTO else 1.3
B = -4.1 if CURTO else -2.45
LARGURA = 7.6 if CURTO else 12.0
ESCALA = 1.0 if CURTO else 0.85


def num(v, casas=None):
    """Número no jeito da língua: 1.234,5 (pt/es) ou 1,234.5 (en)."""
    if casas is None:
        casas = 0 if abs(v - round(v)) < 1e-9 or abs(v) >= 100 else 1
    s = f"{v:,.{casas}f}"
    return s if IDIOMA.startswith("en") else s.replace(",", "§").replace(".", ",").replace("§", ".")


def texto(t, tam, cor=CREME, largura=None):
    linhas = textwrap.wrap(str(t), largura) if largura else [str(t)]
    return Text("\n".join(linhas) or " ", font=FONTE, weight=BOLD, color=cor,
                font_size=tam * ESCALA, line_spacing=0.9)


class CenaRoteiro(Scene):
    def construct(self):
        self.total = float(DADOS["duracao"])
        self.gasto = 0.0
        getattr(self, "cena_" + DADOS["tipo"])()
        if self.total - self.gasto > 0.05:
            self.wait(self.total - self.gasto)

    def tocar(self, *anims, t):
        self.play(*anims, run_time=t)
        self.gasto += t

    def tempos(self, *partes):
        """Divide a duração da cena (deixa ~30% parado no fim para a pessoa ler)."""
        util = self.total * 0.7
        soma = sum(partes)
        return [max(0.25, p / soma * util) for p in partes]

    def titulo(self, t):
        return texto(t, 46, AZUL_CLARO, 26 if CURTO else 50).move_to(UP * TOPO)

    # ------------------------------------------------------------ comparação de tamanhos
    def cena_comparacao(self):
        itens = DADOS["itens"][:4]
        unidade = DADOS.get("unidade", "")
        maior = max(i["valor"] for i in itens) or 1
        n = len(itens)
        passo = 1.05 if CURTO else 0.95
        y0 = A + (n - 1) * passo / 2 + 0.2
        x0 = -LARGURA / 2
        t_tit, *t_barras, t_fim = self.tempos(0.5, *[1.0] * n, 0.6)

        self.tocar(Write(self.titulo(DADOS.get("rotulo", ""))), t=t_tit)
        for k, (item, t) in enumerate(zip(itens, t_barras)):
            y = y0 - k * passo
            destaque = k == n - 1
            cor = AMARELO if destaque else AZUL
            nome = texto(item["nome"], 30, CREME).move_to([x0, y + 0.42, 0], aligned_edge=LEFT)
            alvo = max(0.08, item["valor"] / maior * LARGURA)
            larg = ValueTracker(0.001)
            barra = always_redraw(lambda larg=larg, y=y, cor=cor: RoundedRectangle(
                width=max(0.02, larg.get_value()), height=0.42, corner_radius=0.1, fill_color=cor,
                fill_opacity=1, stroke_width=0).move_to([x0, y, 0], aligned_edge=LEFT))
            dentro = alvo > LARGURA * 0.72  # barra comprida: o número vai dentro dela, no fim

            def rotulo_valor(larg=larg, y=y, item=item, alvo=alvo, dentro=dentro):
                atual = larg.get_value()
                t = texto(f"{num(item['valor'] * atual / alvo)} {unidade}".strip(), 28,
                          "#0B2233" if dentro and atual > 1.6 else CREME)
                if dentro and atual > t.width + 0.3:
                    return t.move_to([x0 + atual - 0.15, y, 0], aligned_edge=RIGHT)
                return t.next_to([x0 + atual, y, 0], RIGHT, buff=0.15)
            valor = always_redraw(rotulo_valor)
            self.add(barra, valor)
            self.tocar(FadeIn(nome, shift=RIGHT * 0.2), larg.animate(rate_func=smooth).set_value(alvo), t=t)
            barra.clear_updaters()
            valor.clear_updaters()

        # frase final: o destaque (último item) comparado com o item anterior (ou "frase" do roteiro)
        top, ref = itens[-1], itens[-2] if n > 1 else itens[-1]
        a, b = sorted((top, ref), key=lambda i: -i["valor"])
        razao = a["valor"] / max(b["valor"], 1e-9)
        if DADOS.get("frase"):
            frase = DADOS["frase"]
        elif razao < 1.15:
            frase = f"{a['nome']} ≈ {b['nome']}"
        else:
            frase = f"{a['nome']} = {num(razao, 0 if razao >= 10 else 1)}× {b['nome']}"
        fim = texto(frase, 58, AMARELO, 18 if CURTO else 40).move_to(UP * B)
        self.tocar(FadeIn(fim, scale=0.8), t=t_fim)
        self.tocar(Circumscribe(fim, color=AMARELO, time_width=0.6), t=min(1.0, max(0.3, self.total - self.gasto - 0.3)))

    # ------------------------------------------------------------ número com medidor
    def cena_numero(self):
        valor = float(DADOS["valor"])
        sufixo = DADOS.get("sufixo", "")
        maximo = float(DADOS.get("maximo") or valor * 1.3 or 1)
        marca = DADOS.get("marca")
        raio = 2.3 if CURTO else 1.9
        centro = [0, A - 0.6 if CURTO else A - 0.3, 0]
        inicio_ang, abertura = 210 * 3.14159 / 180, -240 * 3.14159 / 180
        t_ent, t_conta, t_fim = self.tempos(0.5, 1.6, 0.6)

        fundo = Arc(radius=raio, start_angle=inicio_ang, angle=abertura, stroke_width=26, color=APAGADO).move_arc_center_to(centro)
        v = ValueTracker(0)
        cheio = always_redraw(lambda: Arc(radius=raio, start_angle=inicio_ang,
                                          angle=abertura * max(0.001, v.get_value()) / maximo,
                                          stroke_width=26, color=AMARELO).move_arc_center_to(centro))
        numero = always_redraw(lambda: texto(num(v.get_value(), 0 if valor >= 10 else 1), 96, CREME).move_to(
            [centro[0], centro[1] + 0.15, 0]))
        suf = texto(sufixo.strip(), 40, AZUL_CLARO).move_to([centro[0], centro[1] - 0.85, 0])
        self.tocar(Create(fundo), FadeIn(suf), t=t_ent)
        self.add(cheio, numero)
        extras = []
        if marca:
            ang = inicio_ang + abertura * min(1, marca["valor"] / maximo)
            p = np.array(centro) + raio * np.array([np.cos(ang), np.sin(ang), 0])
            ponto = Dot(p, radius=0.13, color=AZUL_CLARO)
            rot = texto(f"{marca['nome']}: {num(marca['valor'])}{sufixo}", 26, AZUL_CLARO)
            lado = 1 if p[0] >= centro[0] else -1
            rot.next_to(ponto, UP, buff=0.3)
            if rot.width > config.frame_width - 0.6:
                rot.scale_to_fit_width(config.frame_width - 0.6)
            rot.shift(RIGHT * min(0, config.frame_width / 2 - 0.3 - rot.get_right()[0]) if lado > 0
                      else RIGHT * max(0, -config.frame_width / 2 + 0.3 - rot.get_left()[0]))
            extras = [FadeIn(ponto), FadeIn(rot)]
        self.tocar(v.animate(rate_func=smooth).set_value(valor), *extras, t=t_conta)
        cheio.clear_updaters()
        numero.clear_updaters()
        rot = texto(DADOS.get("rotulo", ""), 50, AMARELO, 20 if CURTO else 40).move_to(UP * B)
        self.tocar(FadeIn(rot, shift=UP * 0.2), t=t_fim)

    # ------------------------------------------------------------ linha do tempo
    def cena_linha_do_tempo(self):
        eventos = sorted(DADOS["eventos"][:5], key=lambda e: -float(e["anos"]))
        unidade = DADOS.get("unidade", "")
        mais, menos = float(eventos[0]["anos"]), float(eventos[-1]["anos"])
        xs = [-LARGURA / 2 + (mais - float(e["anos"])) / max(1e-9, mais - menos) * LARGURA for e in eventos]
        y = A + 0.7 if CURTO else A + 0.4
        t_linha, t_pontos, t_chaves, t_fim = self.tempos(0.5, 1.2, 1.2, 0.6)

        linha = Line([-LARGURA / 2 - 0.2, y, 0], [LARGURA / 2 + 0.2, y, 0], color=CREME, stroke_width=5)
        self.tocar(Create(linha), t=t_linha)
        pontos = []
        for k, (e, x) in enumerate(zip(eventos, xs)):
            d = Dot([x, y, 0], radius=0.16, color=AMARELO)
            r = texto(e["rotulo"], 28, CREME, 12 if CURTO else 18)
            r.next_to(d, UP, buff=0.25)
            if k % 2 and CURTO and len(eventos) > 3:
                r.next_to(d, UP, buff=0.9)
            borda = config.frame_width / 2 - 0.25
            if r.get_left()[0] < -borda:
                r.shift(RIGHT * (-borda - r.get_left()[0]))
            if r.get_right()[0] > borda:
                r.shift(LEFT * (r.get_right()[0] - borda))
            pontos.append(VGroup(d, r))
        self.tocar(LaggedStart(*[FadeIn(p, shift=DOWN * 0.2) for p in pontos], lag_ratio=0.5), t=t_pontos)

        gaps = [float(eventos[k]["anos"]) - float(eventos[k + 1]["anos"]) for k in range(len(eventos) - 1)]
        maior = max(range(len(gaps)), key=lambda k: gaps[k])
        chaves = []
        for k, g in enumerate(gaps):
            seg = Line([xs[k], y, 0], [xs[k + 1], y, 0])
            cor = AMARELO if k == maior else AZUL_CLARO
            br = Brace(seg, DOWN, buff=0.3, color=cor)
            lab = texto(f"{num(g)}", 34, cor).next_to(br, DOWN, buff=0.12)
            chaves.append(VGroup(br, lab))
        uni = texto(unidade, 24, AZUL_CLARO).next_to(VGroup(*chaves), DOWN, buff=0.2)
        self.tocar(LaggedStart(*[FadeIn(c, shift=UP * 0.15) for c in chaves], lag_ratio=0.6), FadeIn(uni), t=t_chaves)
        if DADOS.get("conclusao"):
            fim = texto(DADOS["conclusao"], 50, AMARELO, 20 if CURTO else 44).move_to(UP * B)
            self.tocar(FadeIn(fim, scale=0.85), t=t_fim)

    # ------------------------------------------------------------ proporção (quadradinhos)
    def cena_proporcao(self):
        valor = max(0.0, min(100.0, float(DADOS["valor"])))
        lado, vao = (0.34, 0.06) if CURTO else (0.24, 0.05)
        grade = VGroup(*[Square(side_length=lado, fill_color=APAGADO, fill_opacity=1, stroke_width=0)
                         for _ in range(100)]).arrange_in_grid(10, 10, buff=vao)
        grade.move_to(UP * (A + 0.3) if CURTO else [-3.2, A - 0.5, 0])
        t_ent, t_encher, t_fim = self.tempos(0.4, 1.6, 0.6)
        self.tocar(FadeIn(grade), t=t_ent)
        acesos = [q.copy().set_fill(AMARELO) for q in list(grade)[:round(valor)]]
        v = ValueTracker(0)
        pct = always_redraw(lambda: texto(f"{num(v.get_value(), 0)}%", 120, AMARELO).move_to(
            UP * (B + 0.5) if CURTO else [3.6, A, 0]))
        self.add(pct)
        self.tocar(LaggedStart(*[FadeIn(q) for q in acesos], lag_ratio=0.02),
                   v.animate(rate_func=smooth).set_value(valor), t=t_encher)
        pct.clear_updaters()
        rot = texto(DADOS.get("rotulo", ""), 40, CREME, 24 if CURTO else 26)
        rot.next_to(pct, DOWN, buff=0.3)
        self.tocar(FadeIn(rot, shift=UP * 0.2), t=t_fim)

