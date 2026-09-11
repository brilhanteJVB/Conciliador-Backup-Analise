# -*- coding: utf-8 -*-
"""
Classificacao das diretivas de administracao do DrugBank (food-interactions).

O campo 'food_interactions' nao e so interacao com alimento: e uma lista de
ORIENTACOES DE ADMINISTRACAO em ingles corrido. Este modulo transforma cada
frase em registro estruturado de um destes tipos:

  regra_administracao  jejum, com alimento, com agua, horario fixo...
  regra_separacao      separar de antiacido, calcio, ferro, laticinio...
  interacao_item       toranja, erva-de-sao-joao, alcacuz, sal, potassio...
  interacao_habito     alcool, cafeina

O TEXTO EM PORTUGUES NAO E TRADUZIDO FRASE A FRASE. Cada tipo tem uma
orientacao fixa, escrita em portugues, revisada uma vez. O ingles original
fica guardado como trecho de evidencia. Isso evita traducao automatica de
texto clinico, que e onde erro de traducao vira erro de conduta.

INTERVALO: extraido apenas quando a frase o declara ('at least 2 hours').
Frase que manda separar sem dizer quanto gera regra com intervalo NULL --
nunca um numero por analogia (DECISIONS.md D-013).

Autoteste: python pipeline/_diretivas.py
"""
from __future__ import annotations

import re

# ------------------------------------------------------- regra_administracao
# (tipo, padrao, orientacao em pt-BR)
ADMINISTRACAO = [
    # 'empty stomach' nao e a unica forma: captopril diz 'Take separate from
    # meals ... one hour prior to meals', que e a mesma instrucao. A ausencia
    # dessas variantes fazia o farmaco ficar sem regra nenhuma.
    ("JEJUM",
     r"take\s+on\s+an?\s+empty\s+stomach|on\s+an\s+empty\s+stomach|"
     r"take\s+separate\s+from\s+(?:meals?|food)|"
     r"separate\s+from\s+(?:meals?|food)|apart\s+from\s+(?:meals?|food)",
     "Tomar em jejum, com o estômago vazio."),
    ("COM_ALIMENTO",
     r"take\s+with\s+food|take\s+with\s+(?:a\s+)?meals?|with\s+or\s+immediately\s+after\s+food",
     "Tomar junto com alimento."),
    ("APOS_ALIMENTO",
     r"take\s+after\s+(?:a\s+)?meals?|immediately\s+after\s+eating",
     "Tomar logo após a refeição."),
    ("ANTES_ALIMENTO",
     r"take\s+before\s+(?:a\s+)?meals?|before\s+breakfast|"
     r"prior\s+to\s+(?:a\s+)?meals?",
     "Tomar antes da refeição."),
    ("INDIFERENTE_ALIMENTO",
     r"take\s+with\s+or\s+without\s+food|may\s+be\s+taken\s+with\s+or\s+without",
     "Pode ser tomado com ou sem alimento."),
    ("COM_AGUA_ABUNDANTE",
     r"full\s+glass\s+of\s+water|drink\s+plenty\s+of\s+(?:fluids|water)|"
     r"with\s+a\s+glass\s+of\s+water",
     "Tomar com um copo cheio de água."),
    ("PERMANECER_SENTADO",
     r"remain\s+upright|do\s+not\s+lie\s+down|stay\s+upright",
     "Permanecer sentado ou em pé após tomar; não deitar."),
    ("MATINAL",
     r"take\s+in\s+the\s+morning",
     "Tomar pela manhã."),
    ("NOTURNO",
     r"take\s+at\s+night|take\s+in\s+the\s+evening|at\s+bedtime",
     "Tomar à noite."),
    ("CONFORME_SINTOMA",
     r"take\s+at\s+the\s+same\s+time\s+every\s+day",
     "Tomar sempre no mesmo horário todos os dias."),
]

# 'JEJUM' e 'INDIFERENTE_ALIMENTO' sao mutuamente exclusivos; se os dois
# casarem, a frase mais especifica (jejum) vence.
EXCLUSIVOS = ["JEJUM", "COM_ALIMENTO", "APOS_ALIMENTO", "ANTES_ALIMENTO",
              "INDIFERENTE_ALIMENTO"]

# ----------------------------------------------------------- regra_separacao
# (nome do item em pt-BR, tipo do item, padrao, motivo em pt-BR)
SEPARACAO = [
    ("antiácidos", "CLASSE_ATC", r"antacids?",
     "O antiácido altera o pH gástrico e reduz a absorção."),
    ("cálcio", "MINERAL", r"calcium(?:\s+supplements?)?",
     "O cálcio forma complexo com o medicamento e reduz a absorção (quelação)."),
    ("ferro", "MINERAL", r"\biron\b(?:\s+supplements?)?",
     "O ferro forma complexo com o medicamento e reduz a absorção (quelação)."),
    ("magnésio", "MINERAL", r"magnesium",
     "O magnésio forma complexo com o medicamento e reduz a absorção."),
    ("zinco", "MINERAL", r"\bzinc\b",
     "O zinco forma complexo com o medicamento e reduz a absorção."),
    ("alumínio", "MINERAL", r"aluminum|aluminium",
     "O alumínio forma complexo com o medicamento e reduz a absorção."),
    ("leite e derivados", "ALIMENTO", r"milk\s+and\s+dairy|dairy\s+products?",
     "O cálcio do leite forma complexo com o medicamento e reduz a absorção."),
    ("alimentos ricos em fibras", "ALIMENTO", r"high[- ]fib(?:er|re)\s+foods?",
     "A fibra reduz a absorção do medicamento."),
]
# Nem toda instrucao de separar usa a palavra "separate": alendronato diz
# "Avoid multivalent ions. Calcium, antacids ... may interfere with the
# absorption". E a mesma orientacao, sem intervalo declarado -- exatamente
# o caso que a regra com intervalo NULL existe para representar.
RE_SEPARAR = re.compile(
    r"separate|take\s+at\s+least\s+[\d.]+\s*(?:hour|minute)s?\s*(?:before|after)"
    r"|avoid\s+multivalent\s+ions|interfere\s+with\s+the\s+absorption",
    re.I)

# --------------------------------------------------------- interacao_item
# (nome pt-BR, tipo, padrao, efeito em pt-BR, gravidade)
ITENS = [
    ("toranja", "ALIMENTO", r"grapefruit",
     "A toranja inibe a CYP3A4 intestinal e aumenta a exposição ao medicamento.",
     "MODERADA"),
    ("erva-de-são-joão", "PLANTA_MEDICINAL", r"st\.?\s*john'?s?\s*wort",
     "A erva-de-são-joão induz a CYP3A4 e reduz o efeito do medicamento.",
     "MAIOR"),
    ("alcaçuz", "PLANTA_MEDICINAL", r"licorice|liquorice",
     "O alcaçuz pode causar retenção de sódio, perda de potássio e "
     "elevação da pressão arterial.",
     "MODERADA"),
    ("potássio", "MINERAL", r"potassium[- ]containing|potassium\s+supplements?|"
     r"salt\s+substitutes?",
     "Produtos com potássio aumentam o risco de hipercalemia.", "MAIOR"),
    ("sal de cozinha", "ALIMENTO", r"limit\s+salt\s+intake|salt\s+intake",
     "O excesso de sal reduz o efeito anti-hipertensivo.", "MODERADA"),
    ("folhosos verdes (vitamina K)", "ALIMENTO",
     r"vitamin\s*k|leafy\s+green",
     "Alimentos ricos em vitamina K reduzem o efeito do anticoagulante.",
     "MAIOR"),
    ("ervas com ação anticoagulante", "PLANTA_MEDICINAL",
     r"anticoagulant/antiplatelet\s+activity",
     "Ervas com ação anticoagulante ou antiplaquetária somam-se ao "
     "medicamento e aumentam o risco de sangramento.", "MAIOR"),
]

# ------------------------------------------------------- interacao_habito
HABITOS = [
    ("ALCOOL", r"avoid\s+alcohol|limit\s+alcohol",
     "O álcool soma-se ao efeito do medicamento e aumenta o risco de "
     "sedação, lesão gástrica ou hepática, conforme o fármaco.", "MODERADA"),
    ("CAFEINA", r"limit\s+caffeine|avoid\s+caffeine",
     "A cafeína pode somar-se ao efeito estimulante ou competir pelo "
     "mesmo metabolismo.", "MENOR"),
]

# ------------------------------------------------------------------ tempo
# A fonte escreve tanto '1 hour' quanto 'one hour'. Sem os numeros por
# extenso, 'take one hour prior to meals' perdia o intervalo.
NUMERO_EXTENSO = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "half": 0.5, "an": 1, "a": 1,
}


def _numeros_para_digito(texto: str) -> str:
    for palavra, valor in NUMERO_EXTENSO.items():
        # a fronteira de palavra e obrigatoria: sem ela o "a" de
        # NUMERO_EXTENSO casaria dentro de qualquer palavra.
        texto = re.sub(r"\b%s\s+(hour|minute)" % palavra,
                       lambda m, v=valor: "%g %s" % (v, m.group(1)),
                       texto, flags=re.I)
    return texto


RE_HORAS = re.compile(r"(?:at\s+least\s+|take\s+)?(\d+(?:\.\d+)?)\s*hours?", re.I)
RE_MIN = re.compile(r"at\s+least\s+(\d+(?:\.\d+)?)\s*minutes?", re.I)
RE_MIN_FAIXA = re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*minutes?", re.I)


def intervalo_horas(frase: str):
    """Horas explicitamente declaradas na frase; None quando nao ha."""
    frase = _numeros_para_digito(frase)
    m = RE_HORAS.search(frase)
    if m:
        try:
            v = float(m.group(1))
            return v if 0.25 <= v <= 24 else None
        except ValueError:
            return None
    return None


def intervalo_refeicao_min(frase: str):
    """Minutos entre medicamento e refeicao, quando a frase declara."""
    frase = _numeros_para_digito(frase)
    m = RE_HORAS.search(frase)
    if m and re.search(r"(?:before|after|prior\s+to)\s+(?:a\s+)?"
                       r"(?:meals?|eating|breakfast)", frase, re.I):
        try:
            return int(float(m.group(1)) * 60)
        except ValueError:
            return None
    m = RE_MIN_FAIXA.search(frase)
    if m and re.search(r"before\s+(?:a\s+)?(?:meals?|breakfast|eating)",
                       frase, re.I):
        return int(m.group(1))       # extremo conservador da faixa
    m = RE_MIN.search(frase)
    if m and re.search(r"(?:before|after)\s+(?:a\s+)?(?:meals?|eating|breakfast)",
                       frase, re.I):
        try:
            return int(float(m.group(1)))
        except ValueError:
            return None
    return None


def classificar(texto: str) -> dict:
    """Devolve as diretivas encontradas numa lista de food_interactions."""
    t = " ".join((texto or "").split())
    r = {"administracao": [], "separacao": [], "itens": [], "habitos": []}
    if not t:
        return r

    # --- regras de administracao
    achados = []
    for tipo, padrao, orientacao in ADMINISTRACAO:
        if re.search(padrao, t, re.I):
            achados.append((tipo, orientacao))
    # entre os exclusivos, o mais especifico vence
    exclusivos_achados = [a for a in achados if a[0] in EXCLUSIVOS]
    if len(exclusivos_achados) > 1:
        ordem = {k: i for i, k in enumerate(EXCLUSIVOS)}
        vencedor = min(exclusivos_achados, key=lambda a: ordem[a[0]])
        achados = [a for a in achados if a[0] not in EXCLUSIVOS] + [vencedor]
    for tipo, orientacao in achados:
        minutos = intervalo_refeicao_min(t) if tipo in EXCLUSIVOS else None
        r["administracao"].append({
            "tipo": tipo,
            "intervalo_refeicao_min": minutos,
            "texto_orientacao": orientacao + (
                " Respeitar %d minutos em relação à refeição." % minutos
                if minutos else ""),
        })

    # --- separacao (so quando a frase manda separar)
    if RE_SEPARAR.search(t):
        horas = intervalo_horas(t)
        for nome, tipo, padrao, motivo in SEPARACAO:
            if re.search(padrao, t, re.I):
                r["separacao"].append({
                    "item": nome, "tipo_item": tipo,
                    "intervalo_horas": horas, "motivo": motivo,
                })

    # --- itens (alimento, planta, mineral)
    for nome, tipo, padrao, efeito, gravidade in ITENS:
        if re.search(padrao, t, re.I):
            r["itens"].append({"item": nome, "tipo_item": tipo,
                               "efeito": efeito, "gravidade": gravidade})

    # --- habitos
    for habito, padrao, efeito, gravidade in HABITOS:
        if re.search(padrao, t, re.I):
            r["habitos"].append({"habito": habito, "efeito": efeito,
                                 "gravidade": gravidade})
    return r


def _autoteste() -> int:
    falhas = 0
    casos = [
        ("Take with or without food.",
         {"administracao": ["INDIFERENTE_ALIMENTO"]}),
        ("Take with food. Food reduces irritation.",
         {"administracao": ["COM_ALIMENTO"]}),
        ("Take on an empty stomach. Take at least 1 hour before or 2 hours "
         "after meals.",
         {"administracao": ["JEJUM"], "minutos": 60}),
        ("Take with a full glass of water.",
         {"administracao": ["COM_AGUA_ABUNDANTE"]}),
        ("Avoid alcohol.", {"habitos": ["ALCOOL"]}),
        ("Avoid grapefruit products.", {"itens": ["toranja"]}),
        ("Avoid milk and dairy products. Separate the use of zinc from these "
         "products by at least 2 hours before administration.",
         {"separacao": ["leite e derivados", "zinco"], "horas": 2.0}),
        ("Take at least 2 hours before or after antacids.",
         {"separacao": ["antiácidos"], "horas": 2.0}),
        ("Avoid St. John's Wort.", {"itens": ["erva-de-são-joão"]}),
        ("Limit caffeine intake.", {"habitos": ["CAFEINA"]}),
        ("Take separate from meals. The presence of food decreases "
         "absorption. Take one hour prior to meals.",
         {"administracao": ["JEJUM"], "minutos": 60}),
        ("", {}),
    ]
    print("AUTOTESTE — classificação de diretivas")
    for texto, esperado in casos:
        r = classificar(texto)
        ok = True
        if "administracao" in esperado:
            ok &= sorted(a["tipo"] for a in r["administracao"]) == \
                sorted(esperado["administracao"])
        if "separacao" in esperado:
            ok &= sorted(s["item"] for s in r["separacao"]) == \
                sorted(esperado["separacao"])
        if "itens" in esperado:
            ok &= [i["item"] for i in r["itens"]] == esperado["itens"]
        if "habitos" in esperado:
            ok &= [h["habito"] for h in r["habitos"]] == esperado["habitos"]
        if "horas" in esperado:
            ok &= any(s["intervalo_horas"] == esperado["horas"]
                      for s in r["separacao"])
        if "minutos" in esperado:
            ok &= any(a["intervalo_refeicao_min"] == esperado["minutos"]
                      for a in r["administracao"])
        if not esperado:
            ok &= not any(r.values())
        if not ok:
            falhas += 1
        print("  [%s] %-58s %s" % ("OK " if ok else "FALHA", (texto or "(vazio)")[:58],
                                   {k: v for k, v in r.items() if v}))
    print("\nfalhas: %d" % falhas)
    return 1 if falhas else 0


if __name__ == "__main__":
    import sys
    sys.exit(_autoteste())
