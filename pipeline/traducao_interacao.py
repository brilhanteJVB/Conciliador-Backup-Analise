# -*- coding: utf-8 -*-
"""
Traducao das descricoes de interacao — por molde, nunca por adivinhacao.

PROCEDENCIA
-----------
Copiado de `C:\\Conteudos banco de dados tcc\\banco\\app\\_traducao.py` (acervo,
sistema anterior), pelo mesmo criterio de `pipeline/normalizacao.py`: e um
artefato de conhecimento ja medido e testado, nao arquitetura. O acervo
permanece intacto; esta e a copia de trabalho.

Adaptacoes feitas aqui:
  - `carregar_mapa_nomes` passou a ler o esquema NOVO (`substancia.nome_dcb`,
    `substancia_sinonimo` tipo INN) em vez de `substancia.dcb_nome`;
  - a desambiguacao de sal usa `pipeline/normalizacao.skeleton` em vez de
    `lib_norm`;
  - o autoteste mede cobertura sobre `interacao_substancia` deste projeto.

POR QUE ESTE MODULO EXISTE
--------------------------
As descricoes de `db_drug_interactions` chegam ao balcao em ingles:

    "The metabolism of Omeprazole can be decreased when combined with Ibuprofen."

O sistema inteiro fala portugues do Brasil (CLAUDE.md). O farmaceutico le isso
no meio de um atendimento.

POR QUE DA PARA TRADUZIR SEM RISCO
----------------------------------
Traduzir texto clinico livre por script seria irresponsavel. Mas estas
descricoes **nao sao texto livre**: sao geradas por molde, e os campos
variaveis sao fechados — algumas dezenas de adjetivos farmacologicos e seis
valores no slot de risco. Tudo cabe num glossario conferivel.

A REGRA DE OURO — TUDO OU NADA
------------------------------
`traduzir()` so devolve portugues quando o molde casa **e** todos os slots
resolvem no glossario. Qualquer termo desconhecido faz a funcao devolver o
**texto original intacto**. Nunca ha traducao parcial: um termo farmacologico
traduzido pela metade e pior que o ingles.

O original nunca e destruido — quem chama guarda os dois (o carregador poe o
ingles em `interacao_substancia.descricao_original`).
"""
from __future__ import annotations

import os
import re
import sys

# =====================================================================
# glossario de efeitos — o slot "the ___ activities of"
# 'adj' entra em "os efeitos ___ de B"
# 'np'  entra em "pode aumentar ___ associado a B"
# =====================================================================
EFEITOS = {
    "hypotensive":                 ("hipotensores", "adj"),
    "antihypertensive":            ("anti-hipertensivos", "adj"),
    "hypertensive":                ("hipertensores", "adj"),
    "orthostatic hypotensive":     ("hipotensores ortostáticos", "adj"),
    "anticoagulant":               ("anticoagulantes", "adj"),
    "antiplatelet":                ("antiplaquetários", "adj"),
    "thrombogenic":                ("trombogênicos", "adj"),
    "hypoglycemic":                ("hipoglicemiantes", "adj"),
    "bradycardic":                 ("bradicardizantes", "adj"),
    "tachycardic":                 ("taquicardizantes", "adj"),
    "arrhythmogenic":              ("arritmogênicos", "adj"),
    "cardiotoxic":                 ("cardiotóxicos", "adj"),
    "nephrotoxic":                 ("nefrotóxicos", "adj"),
    "hepatotoxic":                 ("hepatotóxicos", "adj"),
    "ototoxic":                    ("ototóxicos", "adj"),
    "neurotoxic":                  ("neurotóxicos", "adj"),
    "central neurotoxic":          ("neurotóxicos centrais", "adj"),
    "sedative":                    ("sedativos", "adj"),
    "immunosuppressive":           ("imunossupressores", "adj"),
    "myelosuppressive":            ("mielossupressores", "adj"),
    "serotonergic":                ("serotoninérgicos", "adj"),
    "neuroexcitatory":             ("neuroexcitatórios", "adj"),
    "anticholinergic":             ("anticolinérgicos", "adj"),
    "antipsychotic":               ("antipsicóticos", "adj"),
    "analgesic":                   ("analgésicos", "adj"),
    "stimulatory":                 ("estimulantes", "adj"),
    "diuretic":                    ("diuréticos", "adj"),
    "vasoconstricting":            ("vasoconstritores", "adj"),
    "vasodilatory":                ("vasodilatadores", "adj"),
    "vasopressor":                 ("vasopressores", "adj"),
    "bronchodilatory":             ("broncodilatadores", "adj"),
    "hypokalemic":                 ("hipocalemiantes", "adj"),
    "hyperkalemic":                ("hipercalemiantes", "adj"),
    "hyponatremic":                ("hiponatremiantes", "adj"),
    "hypocalcemic":                ("hipocalcemiantes", "adj"),
    "hypercalcemic":               ("hipercalcemiantes", "adj"),
    "respiratory depressant":      ("depressores respiratórios", "adj"),
    "adverse neuromuscular":       ("neuromusculares adversos", "adj"),
    "dermatologic adverse":        ("dermatológicos adversos", "adj"),
    "central nervous system depressant":
        ("depressores do sistema nervoso central", "adj"),
    # formas que so funcionam como sintagma nominal
    "QTc-prolonging":            ("o prolongamento do intervalo QTc", "np"),
    "neuromuscular blocking":    ("o bloqueio neuromuscular", "np"),
    "atrioventricular blocking": ("o bloqueio atrioventricular", "np"),
    "fluid retaining":           ("a retenção de líquidos", "np"),
    "myopathic rhabdomyolysis":  ("a miopatia com rabdomiólise", "np"),
    "constipating":              ("a constipação", "np"),
    "hypoglycemic (blood glucose lowering)":
        ("hipoglicemiantes", "adj"),
}

# slot de "The risk or severity of ___ can be increased"
RISCOS = {
    "adverse effects":   "de efeitos adversos",
    "QTc prolongation":  "de prolongamento do intervalo QTc",
    "heart failure":     "de insuficiência cardíaca",
    "hypotension":       "de hipotensão",
    "hyperkalemia":      "de hipercalemia",
    "hypertension":      "de hipertensão",
    "hypoglycemia":      "de hipoglicemia",
    "bleeding":          "de sangramento",
    "sedation":          "de sedação",
    "methemoglobinemia": "de metemoglobinemia",
    "hyperthermia and oligohydramnios":
                         "de hipertermia e oligoidrâmnio",
    "nephrotoxicity":    "de nefrotoxicidade",
    "hepatotoxicity":    "de hepatotoxicidade",
    "serotonin syndrome": "de síndrome serotoninérgica",
}

_N = r"(.+?)"          # nome de farmaco: texto livre, nao-guloso


def _efeito(bruto):
    """Resolve o slot de efeito. Devolve None se nao estiver no glossario."""
    limpo = re.sub(r"\s*\([^)]*\)\s*$", "", (bruto or "").strip())
    return EFEITOS.get(limpo)


def _moldes():
    """(regex, montador). O montador recebe os grupos ja com os nomes de
    farmaco traduzidos e devolve o portugues — ou None se um slot nao
    resolver, e nesse caso a traducao inteira e descartada."""
    M = []

    def add(pad, fn):
        M.append((re.compile(pad + r"\s*$", re.IGNORECASE), fn))

    # --- metabolismo ---
    add(r"The metabolism of %s can be decreased when combined with %s\." % (_N, _N),
        lambda g: "O metabolismo de %s pode ser reduzido quando combinado com %s." % g)
    add(r"The metabolism of %s can be increased when combined with %s\." % (_N, _N),
        lambda g: "O metabolismo de %s pode ser aumentado quando combinado com %s." % g)

    # --- risco / gravidade ---
    def _risco(g):
        alvo = RISCOS.get(g[0].strip())
        return None if not alvo else (
            "O risco ou a gravidade %s pode aumentar quando %s é associado a %s."
            % (alvo, g[1], g[2]))
    add(r"The risk or severity of %s can be increased when %s is combined with %s\."
        % (_N, _N, _N), _risco)

    # --- concentracao serica ---
    add(r"The serum concentration of %s can be increased when it is combined with %s\."
        % (_N, _N),
        lambda g: "A concentração sérica de %s pode aumentar quando associado a %s." % g)
    add(r"The serum concentration of %s can be decreased when it is combined with %s\."
        % (_N, _N),
        lambda g: "A concentração sérica de %s pode diminuir quando associado a %s." % g)
    add(r"The serum concentration of the active metabolites of %s can be increased "
        r"when %s is used in combination with %s\." % (_N, _N, _N),
        lambda g: ("A concentração sérica dos metabólitos ativos de %s pode aumentar "
                   "quando %s é usado em combinação com %s." % g))
    add(r"The serum concentration of the active metabolites of %s can be reduced "
        r"when %s is used in combination with %s resulting in a loss in efficacy\."
        % (_N, _N, _N),
        lambda g: ("A concentração sérica dos metabólitos ativos de %s pode ser "
                   "reduzida quando %s é usado em combinação com %s, com perda de "
                   "eficácia." % g))

    # --- eficacia terapeutica ---
    add(r"The therapeutic efficacy of %s can be decreased when used in combination "
        r"with %s\." % (_N, _N),
        lambda g: ("A eficácia terapêutica de %s pode ser reduzida quando usado em "
                   "combinação com %s." % g))
    add(r"The therapeutic efficacy of %s can be increased when used in combination "
        r"with %s\." % (_N, _N),
        lambda g: ("A eficácia terapêutica de %s pode ser aumentada quando usado em "
                   "combinação com %s." % g))

    # --- "may increase/decrease the ___ activities of" ---
    def _ativ(verbo_adj, verbo_np):
        def fn(g):
            ef = _efeito(g[1])
            if not ef:
                return None
            texto, tipo = ef
            if tipo == "adj":
                return "%s pode %s os efeitos %s de %s." % (g[0], verbo_adj, texto, g[2])
            return "%s pode %s %s associado a %s." % (g[0], verbo_np, texto, g[2])
        return fn
    add(r"%s may increase the %s activities of %s\." % (_N, r"(.+?)", _N),
        _ativ("aumentar", "aumentar"))
    add(r"%s may decrease the %s activities of %s\." % (_N, r"(.+?)", _N),
        _ativ("reduzir", "reduzir"))

    # --- excrecao ---
    add(r"%s may decrease the excretion rate of %s which could result in a higher "
        r"serum level\." % (_N, _N),
        lambda g: ("%s pode reduzir a taxa de excreção de %s, o que pode elevar o "
                   "nível sérico." % g))
    add(r"%s may increase the excretion rate of %s which could result in a lower "
        r"serum level and potentially a reduction in efficacy\." % (_N, _N),
        lambda g: ("%s pode aumentar a taxa de excreção de %s, o que pode reduzir o "
                   "nível sérico e a eficácia." % g))

    # --- biodisponibilidade (antiacidos e quelantes, sobretudo) ---
    add(r"The bioavailability of %s can be decreased when combined with %s\." % (_N, _N),
        lambda g: ("A biodisponibilidade de %s pode ser reduzida quando combinada "
                   "com %s." % g))
    add(r"The bioavailability of %s can be increased when combined with %s\." % (_N, _N),
        lambda g: ("A biodisponibilidade de %s pode ser aumentada quando combinada "
                   "com %s." % g))

    # --- absorcao ---
    add(r"The absorption of %s can be decreased when combined with %s\." % (_N, _N),
        lambda g: "A absorção de %s pode ser reduzida quando combinada com %s." % g)
    add(r"The absorption of %s can be increased when combined with %s\." % (_N, _N),
        lambda g: "A absorção de %s pode ser aumentada quando combinada com %s." % g)
    add(r"%s can cause a decrease in the absorption of %s resulting in a reduced "
        r"serum concentration and potentially a decrease in efficacy\." % (_N, _N),
        lambda g: ("%s pode reduzir a absorção de %s, diminuindo a concentração "
                   "sérica e possivelmente a eficácia." % g))
    add(r"%s can cause an increase in the absorption of %s resulting in an increased "
        r"serum concentration and potentially a worsening of adverse effects\."
        % (_N, _N),
        lambda g: ("%s pode aumentar a absorção de %s, elevando a concentração "
                   "sérica e possivelmente agravando os efeitos adversos." % g))

    # --- protein binding ---
    add(r"%s may decrease the protein binding of %s\." % (_N, _N),
        lambda g: "%s pode reduzir a ligação de %s às proteínas plasmáticas." % g)

    return M


MOLDES = _moldes()


def carregar_mapa_nomes(con):
    """nome em ingles (minusculo) -> nome DCB brasileiro.

    Faz o farmaceutico ler "omeprazol" em vez de "Omeprazole".

    **O cadastro brasileiro e ambiguo de proposito**: o Brasil registra os
    sais separadamente, entao `ibuprofen` casa com "ibuprofeno" e tambem com
    "levolisinato de ibuprofeno". Pegar qualquer um faz o texto **nomear o
    sal errado**, que e pior do que deixar em ingles.

    A regra, em tres degraus:
      1. nome sem ambiguidade -> usa;
      2. ambiguo, mas exatamente uma forma tem a mesma chave normalizada do
         nome em ingles -> usa essa;
      3. ainda ambiguo -> **nao mapeia**; o ingles fica e continua legivel.

    Le de `substancia.nome_en` e dos sinonimos tipo INN, que o carregador de
    interacoes grava quando o casamento e 1:1.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from normalizacao import skeleton as _sk
    except ImportError:                      # sem normalizador, so o degrau 1
        def _sk(x):
            return (x or "").strip().lower()

    por_en = {}
    linhas = list(con.execute(
        "SELECT nome_en, nome_dcb FROM substancia "
        "WHERE nome_en IS NOT NULL AND nome_en <> ''"))
    linhas += list(con.execute(
        "SELECT sn.nome, s.nome_dcb FROM substancia_sinonimo sn "
        "JOIN substancia s ON s.id = sn.substancia_id WHERE sn.tipo = 'INN'"))
    for en, br in linhas:
        if en and br:
            por_en.setdefault(en.strip().lower(), set()).add(br)

    mapa = {}
    for en, formas in por_en.items():
        formas = sorted(formas)
        if len(formas) == 1:
            mapa[en] = formas[0]
            continue
        exatos = [f for f in formas if _sk(f) == _sk(en)]
        if len(exatos) == 1:
            mapa[en] = exatos[0]
        # senao: fica de fora. O ingles e mais honesto que o sal errado.
    return mapa


def traduzir(texto, mapa_nomes=None):
    """Devolve (texto_pt, True) quando um molde casa e todos os slots
    resolvem; (texto_original, False) em qualquer outro caso."""
    if not texto or not isinstance(texto, str):
        return texto, False
    limpo = re.sub(r"\s+", " ", texto).strip()

    for rx, montar in MOLDES:
        m = rx.match(limpo)
        if not m:
            continue
        grupos = list(m.groups())
        if mapa_nomes:
            grupos = [mapa_nomes.get(g.strip().lower(), g) if g else g
                      for g in grupos]
        saida = montar(tuple(grupos))
        if saida:
            # o nome DCB e minusculo ("varfarina sodica"); quando abre a
            # frase, a maiuscula tem de voltar
            return saida[:1].upper() + saida[1:], True
        return texto, False          # molde casou, glossario nao cobriu
    return texto, False


# =====================================================================
# autoteste + relatorio de cobertura sobre o banco real
# =====================================================================
if __name__ == "__main__":
    import sqlite3
    from collections import Counter
    from pathlib import Path

    falhas = 0

    def checa(entrada, esperado):
        global falhas
        obtido, ok = traduzir(entrada)
        bate = obtido == esperado
        print("   %s %s" % ("OK  " if bate else "ERRO", obtido[:96]))
        if not bate:
            print("        esperado: %s" % esperado[:96])
            falhas += 1

    print("autoteste de traducao_interacao.py\n")
    checa("The metabolism of Omeprazole can be decreased when combined with Ibuprofen.",
          "O metabolismo de Omeprazole pode ser reduzido quando combinado com Ibuprofen.")
    checa("The risk or severity of adverse effects can be increased when Clonazepam "
          "is combined with Clozapine.",
          "O risco ou a gravidade de efeitos adversos pode aumentar quando Clonazepam "
          "é associado a Clozapine.")
    checa("The serum concentration of Nimesulide can be increased when it is "
          "combined with Digoxin.",
          "A concentração sérica de Nimesulide pode aumentar quando associado a Digoxin.")
    checa("Metformin may increase the hypoglycemic activities of Acetylsalicylic acid.",
          "Metformin pode aumentar os efeitos hipoglicemiantes de Acetylsalicylic acid.")
    checa("Nimesulide may decrease the diuretic activities of Furosemide.",
          "Nimesulide pode reduzir os efeitos diuréticos de Furosemide.")
    checa("Amiodarone may increase the QTc-prolonging activities of Citalopram.",
          "Amiodarone pode aumentar o prolongamento do intervalo QTc associado a "
          "Citalopram.")
    checa("Diazepam may increase the central nervous system depressant (CNS "
          "depressant) activities of Morphine.",
          "Diazepam pode aumentar os efeitos depressores do sistema nervoso central "
          "de Morphine.")
    checa("Verapamil may increase the atrioventricular blocking (AV block) "
          "activities of Digoxin.",
          "Verapamil pode aumentar o bloqueio atrioventricular associado a Digoxin.")

    print("\n   -- a regra de ouro: termo fora do glossario nao traduz --")
    orig = "Foo may increase the flurbiprofenoid activities of Bar."
    obtido, ok = traduzir(orig)
    print("   %s devolveu o original intacto"
          % ("OK  " if (obtido == orig and not ok) else "ERRO"))
    falhas += 0 if (obtido == orig and not ok) else 1

    orig2 = ("The risk or severity of tenosynovitis can be increased when A is "
             "combined with B.")
    obtido, ok = traduzir(orig2)
    print("   %s risco fora do glossario nao traduz"
          % ("OK  " if (obtido == orig2 and not ok) else "ERRO"))
    falhas += 0 if (obtido == orig2 and not ok) else 1

    print("\n   -- nomes em DCB brasileiro --")
    mapa = {"omeprazole": "omeprazol", "ibuprofen": "ibuprofeno"}
    obtido, _ = traduzir("The metabolism of Omeprazole can be decreased when "
                         "combined with Ibuprofen.", mapa)
    esp = "O metabolismo de omeprazol pode ser reduzido quando combinado com ibuprofeno."
    print("   %s %s" % ("OK  " if obtido == esp else "ERRO", obtido))
    falhas += 0 if obtido == esp else 1

    # ---- cobertura sobre o banco deste projeto ----
    DB = Path(__file__).resolve().parent.parent / "database" / "conciliador.db"
    if DB.exists():
        con = sqlite3.connect(DB)
        try:
            rs = [d for (d,) in con.execute(
                "SELECT descricao_original FROM interacao_substancia "
                "WHERE descricao_original IS NOT NULL AND descricao_original <> ''")]
        except sqlite3.OperationalError:
            rs = []
        if rs:
            print("\n=== COBERTURA SOBRE O BANCO REAL ===")
            mapa = carregar_mapa_nomes(con)
            print("   nomes en->DCB carregados: %d" % len(mapa))
            n_ok, nao = 0, Counter()
            for d in rs:
                _, ok = traduzir(d, mapa)
                if ok:
                    n_ok += 1
                else:
                    nao[re.sub(r"\s+", " ", d)[:70]] += 1
            print("   descrições em inglês: %d" % len(rs))
            print("   traduzíveis:          %d  (%.1f%%)"
                  % (n_ok, 100.0 * n_ok / len(rs)))
            print("   intactas:             %d" % (len(rs) - n_ok))
            if nao:
                print("\n   moldes ainda não cobertos (10 maiores):")
                for k, v in nao.most_common(10):
                    print("   %6d  %s" % (v, k))
        con.close()

    print("\n%s" % ("FALHOU — %d" % falhas if falhas else "todos os testes passaram"))
    sys.exit(1 if falhas else 0)
