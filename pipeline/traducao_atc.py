# -*- coding: utf-8 -*-
"""
Traducao dos nomes de classe ATC (ingles -> portugues do Brasil).

METODO: MOLDE, nao palavra a palavra.

Traduzir termo a termo produz portugues errado, porque a ordem muda:
'Calcium channel blockers' vira 'Calcio canal bloqueadores' em vez de
'Bloqueadores dos canais de calcio'. Por isso o nome inteiro e casado
contra um molde ('{X} channel blockers') e so entao remontado.

REGRA TUDO-OU-NADA: molde que casa mas com termo fora do glossario devolve
o ORIGINAL INTACTO, marcado como nao traduzido. Meia traducao
('Inibidores da bone resorption') e pior que o ingles inteiro.

Nome proprio cientifico nao e traduzido: HMG CoA, ACE, COX, 99mTc.

Autoteste: python pipeline/traducao_atc.py
"""
from __future__ import annotations

import re

# ------------------------------------------------------- glossario de termos
# Substantivos e adjetivos que aparecem dentro dos moldes.
TERMOS = {
    # grupos anatomicos (nivel 1) e de sistema
    "alimentary tract and metabolism": "Trato alimentar e metabolismo",
    "blood and blood forming organs": "Sangue e órgãos hematopoiéticos",
    "cardiovascular system": "Sistema cardiovascular",
    "dermatologicals": "Dermatológicos",
    "genito urinary system and sex hormones":
        "Sistema geniturinário e hormônios sexuais",
    "systemic hormonal preparations, excl. sex hormones and insulins":
        "Preparações hormonais sistêmicas, exceto hormônios sexuais e insulinas",
    "antiinfectives for systemic use": "Anti-infecciosos para uso sistêmico",
    "antineoplastic and immunomodulating agents":
        "Agentes antineoplásicos e imunomoduladores",
    "musculo-skeletal system": "Sistema musculoesquelético",
    "nervous system": "Sistema nervoso",
    "antiparasitic products, insecticides and repellents":
        "Antiparasitários, inseticidas e repelentes",
    "respiratory system": "Sistema respiratório",
    "sensory organs": "Órgãos dos sentidos",
    "various": "Diversos",

    # termos frequentes dentro dos moldes
    "antacids": "Antiácidos", "diuretics": "Diuréticos",
    "calcium": "cálcio", "potassium": "potássio", "sodium": "sódio",
    "beta": "beta", "alpha": "alfa",
    "corticosteroids": "Corticosteroides", "antibiotics": "Antibióticos",
    "antibacterials": "Antibacterianos", "antivirals": "Antivirais",
    "antimycotics": "Antifúngicos", "antihistamines": "Anti-histamínicos",
    "analgesics": "Analgésicos", "anesthetics": "Anestésicos",
    "vaccines": "Vacinas", "insulins": "Insulinas",
    "vitamins": "Vitaminas", "minerals": "Minerais",
    "laxatives": "Laxantes", "antidiarrheals": "Antidiarreicos",
    "antiemetics": "Antieméticos", "antiepileptics": "Antiepilépticos",
    "antidepressants": "Antidepressivos", "antipsychotics": "Antipsicóticos",
    "anxiolytics": "Ansiolíticos", "hypnotics and sedatives":
        "Hipnóticos e sedativos", "psycholeptics": "Psicolépticos",
    "psychoanaleptics": "Psicoanalépticos", "muscle relaxants":
        "Relaxantes musculares", "antithrombotic agents":
        "Antitrombóticos", "antianemic preparations":
        "Preparações antianêmicas", "cardiac therapy": "Terapia cardíaca",
    "antihypertensives": "Anti-hipertensivos", "vasodilators": "Vasodilatadores",
    "lipid modifying agents": "Agentes modificadores de lipídeos",
    "thyroid therapy": "Terapia tireoidiana",
    "immunosuppressants": "Imunossupressores",
    "immunostimulants": "Imunoestimulantes",
    "antiinflammatory": "anti-inflamatórios",
    "antiinflammatory and antirheumatic products":
        "Anti-inflamatórios e antirreumáticos",
    "stomatological preparations": "Preparações estomatológicas",
    "radiopharmaceuticals": "Radiofármacos",
    "contrast media": "Meios de contraste",
    "drugs for acid related disorders":
        "Medicamentos para distúrbios ácido-relacionados",
    "drugs used in diabetes": "Medicamentos usados no diabetes",
    "hmg coa reductase": "HMG CoA redutase",
    "ace": "ECA", "cox-2": "COX-2", "proton pump": "bomba de prótons",
    "angiotensin ii receptor": "receptor da angiotensina II",
    "selective serotonin reuptake": "recaptação seletiva de serotonina",
    "bone resorption": "reabsorção óssea",
    "channel": "canal", "channels": "canais",
    "local oral treatment": "tratamento oral local",
    "systemic use": "uso sistêmico", "topical use": "uso tópico",
    "b-complex": "complexo B",

    # --- nivel 2 completo (grupos terapeuticos), curado a mao ---
    "drugs for functional gastrointestinal disorders":
        "Medicamentos para distúrbios gastrointestinais funcionais",
    "antiemetics and antinauseants": "Antieméticos e antinauseantes",
    "bile and liver therapy": "Terapia biliar e hepática",
    "drugs for constipation": "Medicamentos para constipação",
    "antidiarrheals, intestinal antiinflammatory/antiinfective agents":
        "Antidiarreicos e anti-inflamatórios/anti-infecciosos intestinais",
    "antiobesity preparations, excl. diet products":
        "Preparações antiobesidade, exceto produtos dietéticos",
    "digestives, incl. enzymes": "Digestivos, incluindo enzimas",
    "mineral supplements": "Suplementos minerais",
    "tonics": "Tônicos",
    "anabolic agents for systemic use": "Anabolizantes para uso sistêmico",
    "appetite stimulants": "Estimulantes do apetite",
    "antihemorrhagics": "Anti-hemorrágicos",
    "blood substitutes and perfusion solutions":
        "Substitutos do sangue e soluções de perfusão",
    "other hematological agents": "Outros agentes hematológicos",
    "peripheral vasodilators": "Vasodilatadores periféricos",
    "vasoprotectives": "Vasoprotetores",
    "agents acting on the renin-angiotensin system":
        "Agentes que atuam no sistema renina-angiotensina",
    "antifungals for dermatological use":
        "Antifúngicos para uso dermatológico",
    "emollients and protectives": "Emolientes e protetores",
    "preparations for treatment of wounds and ulcers":
        "Preparações para tratamento de feridas e úlceras",
    "antipruritics, incl. antihistamines, anesthetics, etc.":
        "Antipruriginosos, incluindo anti-histamínicos e anestésicos",
    "antipsoriatics": "Antipsoriáticos",
    "antibiotics and chemotherapeutics for dermatological use":
        "Antibióticos e quimioterápicos para uso dermatológico",
    "corticosteroids, dermatological preparations":
        "Corticosteroides, preparações dermatológicas",
    "antiseptics and disinfectants": "Antissépticos e desinfetantes",
    "medicated dressings": "Curativos medicamentosos",
    "anti-acne preparations": "Preparações antiacne",
    "other dermatological preparations": "Outras preparações dermatológicas",
    "gynecological antiinfectives and antiseptics":
        "Anti-infecciosos e antissépticos ginecológicos",
    "other gynecologicals": "Outros ginecológicos",
    "sex hormones and modulators of the genital system":
        "Hormônios sexuais e moduladores do sistema genital",
    "urologicals": "Urológicos",
    "pituitary and hypothalamic hormones and analogues":
        "Hormônios hipofisários e hipotalâmicos e análogos",
    "pancreatic hormones": "Hormônios pancreáticos",
    "calcium homeostasis": "Homeostase do cálcio",
    "antimycobacterials": "Antimicobacterianos",
    "immune sera and immunoglobulins": "Soros imunes e imunoglobulinas",
    "antineoplastic agents": "Agentes antineoplásicos",
    "endocrine therapy": "Terapia endócrina",
    "topical products for joint and muscular pain":
        "Produtos tópicos para dor articular e muscular",
    "antigout preparations": "Preparações para gota",
    "drugs for treatment of bone diseases":
        "Medicamentos para tratamento de doenças ósseas",
    "other drugs for disorders of the musculo-skeletal system":
        "Outros medicamentos para distúrbios do sistema musculoesquelético",
    "anti-parkinson drugs": "Antiparkinsonianos",
    "other nervous system drugs": "Outros medicamentos do sistema nervoso",
    "antiprotozoals": "Antiprotozoários",
    "anthelmintics": "Anti-helmínticos",
    "ectoparasiticides, incl. scabicides, insecticides and repellents":
        "Ectoparasiticidas, incluindo escabicidas, inseticidas e repelentes",
    "drugs for obstructive airway diseases":
        "Medicamentos para doenças obstrutivas das vias aéreas",
    "ophthalmologicals": "Oftalmológicos",
    "otologicals": "Otológicos",
    "ophthalmological and otological preparations":
        "Preparações oftalmológicas e otológicas",
    "allergens": "Alérgenos",
    "all other therapeutic products": "Todos os outros produtos terapêuticos",
    "diagnostic agents": "Agentes diagnósticos",
    "general nutrients": "Nutrientes gerais",
    "all other non-therapeutic products":
        "Todos os outros produtos não terapêuticos",
    "diagnostic radiopharmaceuticals": "Radiofármacos diagnósticos",
    "therapeutic radiopharmaceuticals": "Radiofármacos terapêuticos",
    "surgical dressings": "Curativos cirúrgicos",

    # --- termos frequentes nos niveis 3 e 4 ---
    "antispasmodics": "Antispasmódicos", "anticholinergics": "Anticolinérgicos",
    "propulsives": "Propulsivos", "bile therapy": "Terapia biliar",
    "liver therapy": "Terapia hepática", "lipotropics": "Lipotrópicos",
    "intestinal antiinfectives": "Anti-infecciosos intestinais",
    "belladonna": "beladona", "psycholeptics": "psicolépticos",
    "analgesics": "analgésicos", "other drugs": "outros medicamentos",
    "sulfonamides": "Sulfonamidas", "penicillins": "Penicilinas",
    "cephalosporins": "Cefalosporinas", "macrolides": "Macrolídeos",
    "tetracyclines": "Tetraciclinas", "quinolones": "Quinolonas",
    "aminoglycosides": "Aminoglicosídeos", "barbiturates": "Barbitúricos",
    "benzodiazepines": "Benzodiazepínicos", "opioids": "Opioides",
    "salicylates": "Salicilatos", "xanthines": "Xantinas",
    "thiazides": "Tiazídicos", "sulfonylureas": "Sulfonilureias",
    "biguanides": "Biguanidas", "statins": "Estatinas",
    "fibrates": "Fibratos", "nitrates": "Nitratos",
    "glycosides": "Glicosídeos", "alkaloids": "Alcaloides",
    "prostaglandins": "Prostaglandinas", "heparins": "Heparinas",
    "estrogens": "Estrogênios", "progestogens": "Progestogênios",
    "androgens": "Androgênios", "gonadotropins": "Gonadotrofinas",
    "antithyroid preparations": "Preparações antitireoidianas",
    "thyroid preparations": "Preparações tireoidianas",
    "corticosteroids for systemic use":
        "Corticosteroides para uso sistêmico",
    "beta blocking agents": "Betabloqueadores",
    "calcium channel blockers": "Bloqueadores dos canais de cálcio",
    "ace inhibitors": "Inibidores da ECA",
    "angiotensin ii receptor blockers (arbs)":
        "Bloqueadores do receptor da angiotensina II",
    "proton pump inhibitors": "Inibidores da bomba de prótons",
    "expectorants": "Expectorantes", "mucolytics": "Mucolíticos",
    "antitussives": "Antitussígenos", "decongestants": "Descongestionantes",
    "bronchodilators": "Broncodilatadores",
    "antiglaucoma preparations": "Preparações antiglaucoma",
    "antiinfectives": "Anti-infecciosos", "antiseptics": "Antissépticos",
    "immunoglobulins": "Imunoglobulinas",
    "blood glucose lowering drugs, excl. insulins":
        "Hipoglicemiantes, exceto insulinas",
}

# --------------------------------------------------------------------- moldes
# ({0} e o termo capturado). Ordem importa: o mais especifico vem antes.
MOLDES = [
    (re.compile(r"^other (.+)$", re.I), "Outros {0}"),
    (re.compile(r"^(.+) inhibitors$", re.I), "Inibidores da {0}"),
    (re.compile(r"^(.+) inhibitor$", re.I), "Inibidor da {0}"),
    (re.compile(r"^(.+) antagonists$", re.I), "Antagonistas de {0}"),
    (re.compile(r"^(.+) agonists$", re.I), "Agonistas de {0}"),
    (re.compile(r"^(.+) channel blockers$", re.I), "Bloqueadores dos canais de {0}"),
    (re.compile(r"^(.+) blocking agents$", re.I), "Bloqueadores de {0}"),
    (re.compile(r"^(.+) blockers$", re.I), "Bloqueadores de {0}"),
    (re.compile(r"^(.+) derivatives$", re.I), "Derivados de {0}"),
    (re.compile(r"^(.+) analogues$", re.I), "Análogos de {0}"),
    (re.compile(r"^(.+) preparations$", re.I), "Preparações de {0}"),
    (re.compile(r"^(.+) products$", re.I), "Produtos de {0}"),
    (re.compile(r"^(.+) combinations$", re.I), "Associações de {0}"),
    (re.compile(r"^(.+), combinations$", re.I), "{0}, associações"),
    (re.compile(r"^(.+), plain$", re.I), "{0}, simples"),
    (re.compile(r"^(.+) for (.+)$", re.I), "{0} para {1}"),
    (re.compile(r"^(.+) and (.+)$", re.I), "{0} e {1}"),
]

_SO_SIGLA = re.compile(r"^[A-Z0-9][A-Z0-9\-]{0,6}$")


def _minuscula_inicial(s: str) -> str:
    """Minusculiza a inicial dentro do molde, exceto em sigla.

    'HMG CoA redutase' nao pode virar 'hMG CoA redutase': quando as duas
    primeiras letras sao maiusculas, o termo e sigla e fica como esta.
    """
    if len(s) >= 2 and s[0].isupper() and s[1].isupper():
        return s
    return s[0].lower() + s[1:] if s else s


def _termo(t: str):
    """Traduz um termo do glossario; None quando nao coberto."""
    b = re.sub(r"\s+", " ", t.strip().strip(",")).lower()
    if not b:
        return None
    if b in TERMOS:
        return TERMOS[b]
    # sigla cientifica fica como esta
    if _SO_SIGLA.match(t.strip()):
        return t.strip()
    return None


def traduzir(nome: str):
    """(texto_pt, True) quando 100% coberto; (original, False) caso contrario."""
    if not nome or not nome.strip():
        return nome, False
    base = re.sub(r"\s+", " ", nome.strip())

    # 1) o nome inteiro esta no glossario?
    t = _termo(base)
    if t:
        return t, True

    # 2) algum molde casa E todos os termos capturados sao conhecidos?
    for padrao, molde in MOLDES:
        m = padrao.match(base)
        if not m:
            continue
        traduzidos = []
        for g in m.groups():
            # recursao: o capturado pode ele mesmo casar um molde
            sub, ok = traduzir(g)
            if not ok:
                traduzidos = None
                break
            traduzidos.append(_minuscula_inicial(sub))
        if traduzidos is None:
            continue
        texto = molde.format(*traduzidos)
        return texto[0].upper() + texto[1:], True

    # 3) nao coberto: devolve intacto, declarado como nao traduzido
    return nome, False


def _autoteste() -> int:
    casos = [
        ("CARDIOVASCULAR SYSTEM", "Sistema cardiovascular", True),
        ("ANTACIDS", "Antiácidos", True),
        ("DIURETICS", "Diuréticos", True),
        ("Calcium channel blockers", "Bloqueadores dos canais de cálcio", True),
        ("HMG CoA reductase inhibitors", "Inibidores da HMG CoA redutase", True),
        ("Other antiinflammatory agents", None, False),
        ("Proton pump inhibitors", "Inibidores da bomba de prótons", True),
        ("Antibiotics and corticosteroids",
         "Antibióticos e corticosteroides", True),
        ("Corticosteroids for local oral treatment",
         "Corticosteroides para tratamento oral local", True),
        ("Bone resorption inhibitors", "Inibidores da reabsorção óssea", True),
        ("Blahblah xyzzy widgets", "Blahblah xyzzy widgets", False),
        ("", "", False),
    ]
    falhas = 0
    print("AUTOTESTE — tradução de classes ATC (por molde)")
    for entrada, esperado, esperado_ok in casos:
        texto, ok = traduzir(entrada)
        acerto = (ok == esperado_ok) and (esperado is None or texto == esperado)
        if not acerto:
            falhas += 1
        print("  [%s] %-42s -> %-42s %s"
              % ("OK " if acerto else "FALHA", (entrada or "(vazio)")[:42],
                 texto[:42], "traduzido" if ok else "EM INGLÊS (não coberto)"))
        if not acerto and esperado:
            print("        esperado: %s" % esperado)
    print("\nTudo-ou-nada: nome não coberto volta intacto, nunca pela metade.")
    print("falhas: %d" % falhas)
    return 1 if falhas else 0


if __name__ == "__main__":
    import sys
    sys.exit(_autoteste())
