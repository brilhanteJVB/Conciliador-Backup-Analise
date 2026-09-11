# -*- coding: utf-8 -*-
# =====================================================================
# NORMALIZACAO DE NOMES DE FARMACOS
# =====================================================================
# PROCEDENCIA: copiado sem alteracao de
#   acervo: analise_dados/scripts/lib_norm.py
#   sha256[:16] = 429b0585d56ee0cc
#   copiado em 09/09/2026
#
# Incorporado como CONHECIMENTO (tabela de sais + regras foneticas
# deterministicas), nao como arquitetura -- ver docs/DECISIONS.md D-011.
# O acervo permanece intacto; esta e a copia de trabalho do projeto e o
# sistema em producao nao depende do diretorio de origem.
#
# Nao e modelo de ML: e transliteracao PT<->EN + remocao de sais, para
# reduzir os dois idiomas a um mesmo esqueleto e permitir join exato.
# Teste independente: tests/teste_normalizacao.py
# =====================================================================
"""
Normalizador ortografico EN <-> PT para nomes de farmacos (DCB/DCI/INN).

NAO e um modelo de ML. E um conjunto de regras deterministicas de
transliteracao + tabela de sais/esteres. Reproduzivel e auditavel.

O objetivo NAO e traduzir: e reduzir os dois idiomas a um mesmo
"esqueleto" canonico para permitir join exato.
"""
import re
import unicodedata

# ---------------------------------------------------------------
# 1) Sais, esteres e qualificadores que NAO fazem parte do principio
#    ativo para fins de deteccao de interacao.
#    (cloridrato de fluoxetina == fluoxetina, para efeito de interacao)
# ---------------------------------------------------------------
SAIS = [
    # portugues (aparecem como "X de Y" ou "Y X")
    "cloridrato", "dicloridrato", "bromidrato", "hidrobrometo", "sulfato",
    "bissulfato", "hemisulfato", "maleato", "tartarato", "bitartarato",
    "besilato", "mesilato", "metanossulfonato", "succinato", "hemisuccinato",
    "fumarato", "acetato", "citrato", "dicitrato", "fosfato", "difosfato",
    "nitrato", "brometo", "cloreto", "iodeto", "lactato", "malato",
    "mucato", "napsilato", "oxalato", "pamoato", "embonato", "palmitato",
    "pivalato", "propionato", "valerato", "dipropionato", "salicilato",
    "estearato", "gluconato", "glicerato", "carbonato", "bicarbonato",
    "borato", "benzoato", "butirato", "caproato", "decanoato", "enantato",
    "furoato", "hemifumarato", "hemitartarato", "sodico", "sodio",
    "potassico", "potassio", "calcico", "calcio", "magnesio", "monoidratado",
    "diidratado", "trihidratado", "hidratado", "anidro", "micronizado",
    "monoidrato", "dihidrato", "trometamol", "trometamina", "arginina",
    "lisinato", "meglumina", "colina", "dietilamina", "etilenodiamina",
    "hemihidratado", "sesquihidratado", "monossodico", "dissodico",
    "monopotassico", "dipotassico", "racemico", "hemi", "base",
    # ACRESCENTADO 09/09/2026 (projeto novo): hidratos superiores que a
    # tabela original nao cobria. Sem eles 'sulfato de morfina
    # pentaidratado' virava esqueleto 'morfin pentaidratad' e nao casava
    # com 'sulfato de morfina' -> morfina ficava fora do vinculo CMED.
    "pentaidratado", "pentahidratado", "hexaidratado", "hexahidratado",
    "heptaidratado", "heptahidratado", "octaidratado", "octahidratado",
    "pentahydrate", "hexahydrate", "heptahydrate",
    # ingles
    "hydrochloride", "dihydrochloride", "hydrobromide", "sulfate", "sulphate",
    "bisulfate", "maleate", "tartrate", "bitartrate", "besylate", "besilate",
    "mesylate", "mesilate", "methanesulfonate", "succinate", "fumarate",
    "acetate", "citrate", "phosphate", "diphosphate", "nitrate", "bromide",
    "chloride", "iodide", "lactate", "malate", "mucate", "napsylate",
    "oxalate", "pamoate", "embonate", "palmitate", "pivalate", "propionate",
    "valerate", "dipropionate", "salicylate", "stearate", "gluconate",
    "carbonate", "bicarbonate", "borate", "benzoate", "butyrate", "caproate",
    "decanoate", "enanthate", "furoate", "sodium", "potassium", "calcium",
    "magnesium", "monohydrate", "dihydrate", "trihydrate", "hydrate",
    "anhydrous", "micronized", "tromethamine", "arginine", "meglumine",
    "choline", "diethylamine", "ethylenediamine", "disodium", "monosodium",
    "dipotassium", "racemic", "free", "anhydrate",
]
SAIS_SET = set(SAIS)

_LIGACAO = {"de", "do", "da", "dos", "das", "e", "of", "and"}

# formas adjetivas de sal e hidratos, capturadas por padrao
_RE_SAL_ADJ = re.compile(
    r"^(sodi[ck][ao]|potassi[ck][ao]|calci[ck][ao]|magnesi[ck][ao]|"
    r"cal[ck]i[ck][ao]|"
    r"(di|mono|tri|tetra|hemi|sesqui)?h?idrat[ao]d[ao]|"
    r"(di|mono|tri|tetra|hemi|sesqui)?h?idrat[oae]?|"
    r"anidr[ao]|micronizad[ao]|purificad[ao]|racemic[ao]|"
    r"di|mono|tri|hemi|sesqui)$")

# ---------------------------------------------------------------
# 1b) SINONIMOS VERDADEIROS (nomes diferentes, nao variacao grafica).
#     Curadoria manual - cada entrada e uma decisao humana, nao
#     resultado de algoritmo. Mapeia para o termo em ingles.
# ---------------------------------------------------------------
SINONIMOS = {
    "alcool etilico": "ethanol", "alcool": "ethanol", "etanol": "ethanol",
    "dipirona": "metamizole", "dipirona sodica": "metamizole",
    "dipyrone": "metamizole",
    "metamizol": "metamizole", "novalgina": "metamizole",
    "acetaminophen": "paracetamol", "acetaminofeno": "paracetamol",
    "epinephrine": "adrenaline", "epinefrina": "adrenaline",
    "adrenalina": "adrenaline",
    "norepinephrine": "noradrenaline", "norepinefrina": "noradrenaline",
    "noradrenalina": "noradrenaline",
    "albuterol": "salbutamol",
    "acetylsalicylic acid": "aspirin", "acido acetilsalicilico": "aspirin",
    "aas": "aspirin",
    "vitamin k": "phytomenadione", "vitamina k": "phytomenadione",
    "phytonadione": "phytomenadione", "fitomenadiona": "phytomenadione",
    "vitamin c": "ascorbic acid", "vitamina c": "ascorbic acid",
    "acido ascorbico": "ascorbic acid",
    "vitamin b6": "pyridoxine", "vitamina b6": "pyridoxine",
    "piridoxina": "pyridoxine",
    "vitamin b12": "cyanocobalamin", "vitamina b12": "cyanocobalamin",
    "cianocobalamina": "cyanocobalamin",
    "vitamin d": "cholecalciferol", "vitamina d": "cholecalciferol",
    "colecalciferol": "cholecalciferol",
    "vitamin e": "tocopherol", "vitamina e": "tocopherol",
    "vitamin a": "retinol", "vitamina a": "retinol",
    "acido folico": "folic acid",
    "hidroxido de aluminio": "aluminum hydroxide",
    "carvao ativado": "activated charcoal",
    "sais de reidratacao oral": "oral rehydration salts",
    "escopolamina": "hyoscine", "hioscina": "hyoscine",
    "butilescopolamina": "butylscopolamine",
    "brometo de n-butilescopolamina": "butylscopolamine",
    "meperidina": "pethidine", "petidina": "pethidine",
    "dolantina": "pethidine",
    "levotiroxina": "levothyroxine",
    "sinvastatina": "simvastatin",
    "anlodipino": "amlodipine",
    "nimesulida": "nimesulide",
    "glibenclamida": "glyburide", "glyburide": "glibenclamide",
    "trimetoprima": "trimethoprim",
    "sulfametoxazol": "sulfamethoxazole",
    "cetoprofeno": "ketoprofen",
    "cetorolaco": "ketorolac",
    "cetamina": "ketamine",
    "cetoconazol": "ketoconazole",
    "clonidina": "clonidine",
    "prometazina": "promethazine",
}


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def limpa(s):
    """minusculas, sem acento, so letras/espaco/hifen."""
    if s is None:
        return ""
    s = strip_accents(str(s)).lower()
    s = s.replace("&#225;", "a").replace("&#233;", "e")
    s = re.sub(r"\(.*?\)", " ", s)          # remove parenteses
    s = re.sub(r"[^a-z0-9 \-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _eh_sal(t):
    return t in SAIS_SET or bool(_RE_SAL_ADJ.match(t))


def remove_sais(s):
    """Remove tokens de sal/ester/hidrato. Preserva o resto da ordem."""
    toks = [t for t in limpa(s).replace("-", " ").split() if t]
    out = []
    for i, t in enumerate(toks):
        if _eh_sal(t) or t in _LIGACAO:
            continue
        # ACRESCENTADO 09/09/2026: 'acido' qualificando um sal ja removido
        # nao e o principio ativo. 'maleato acido de timolol' -> 'timolol'.
        # So descarta quando vem LOGO APOS um sal: em 'acido
        # acetilsalicilico' o 'acido' e o inicio do nome e fica.
        if t in ("acido", "acida") and i > 0 and _eh_sal(toks[i - 1]):
            continue
        out.append(t)
    if not out:                              # era so sal -> devolve original
        out = [t for t in toks if t not in _LIGACAO]
    return " ".join(out)


# ---------------------------------------------------------------
# 2) Transliteracao para "esqueleto" comum EN/PT
#    Aplicada token a token, na ordem.
# ---------------------------------------------------------------
_VOGAIS = "aeiou"


def _token_skel(t):
    if not t:
        return ""
    # protese do 'e' em portugues: espironolactona <-> spironolactone
    t = re.sub(r"^e(?=s[bcdfgklmnpqrstvz])", "", t)
    # digrafos e equivalencias graficas EN/PT
    t = t.replace("ph", "f")
    t = t.replace("th", "t")
    t = t.replace("rh", "r").replace("gh", "g")
    t = t.replace("qu", "k").replace("ch", "k").replace("cc", "k")
    t = t.replace("c", "k")                  # c e k unificados (cetoconazol/keto-)
    t = t.replace("y", "i").replace("w", "v").replace("z", "s")
    t = t.replace("h", "")
    t = t.replace("x", "ks")
    t = t.replace("ae", "e").replace("oe", "e")
    # m -> n antes de consoante (exceto p/b): simvastatin <-> sinvastatina
    t = re.sub(r"m(?=[^aeioupb])", "n", t)
    # -ium / -io  ->  -i   (lithium <-> litio)
    t = re.sub(r"i(um|o)$", "i", t)
    # queda da vogal final atona: ibuprofeno/ibuprofen, acido/acid
    if len(t) > 4 and t[-1] in _VOGAIS:
        t = t[:-1]
    t = re.sub(r"(.)\1+", r"\1", t)          # colapsa letras duplicadas
    return t


def skeleton(s):
    """Chave canonica para join EN<->PT. Ordena tokens (a ordem difere:
    'acido folico' vs 'folic acid')."""
    base = remove_sais(s)
    base = SINONIMOS.get(base, base)         # sinonimo apos remocao de sal
    base = SINONIMOS.get(limpa(s), base)     # ou sobre a string limpa inteira
    toks = [_token_skel(t) for t in base.split() if t]
    toks = [t for t in toks if t]
    if not toks:
        return ""
    if len(toks) > 1:
        toks = sorted(toks)
    return " ".join(toks)


if __name__ == "__main__":
    # ------- validacao contra pares EN/PT que sao verdade conhecida -------
    PARES = [
        ("Warfarin", "varfarina"), ("Ibuprofen", "ibuprofeno"),
        ("Simvastatin", "sinvastatina"), ("Clarithromycin", "claritromicina"),
        ("Fluoxetine", "cloridrato de fluoxetina"),
        ("Methotrexate", "metotrexato"), ("Phenytoin", "fenitoina sodica"),
        ("Digoxin", "digoxina"), ("Amiodarone", "cloridrato de amiodarona"),
        ("Metformin", "cloridrato de metformina"),
        ("Omeprazole", "omeprazol"), ("Captopril", "captopril"),
        ("Losartan", "losartana potassica"), ("Enalapril", "maleato de enalapril"),
        ("Spironolactone", "espironolactona"),
        ("Acetylsalicylic acid", "acido acetilsalicilico"),
        ("Folic acid", "acido folico"), ("Valproic acid", "acido valproico"),
        ("Carbamazepine", "carbamazepina"), ("Lithium", "carbonato de litio"),
        ("Ciprofloxacin", "cloridrato de ciprofloxacino"),
        ("Azithromycin", "azitromicina di-hidratada"),
        ("Prednisone", "prednisona"), ("Dexamethasone", "dexametasona"),
        ("Levothyroxine", "levotiroxina sodica"),
        ("Hydrochlorothiazide", "hidroclorotiazida"),
        ("Furosemide", "furosemida"), ("Allopurinol", "alopurinol"),
        ("Ranitidine", "cloridrato de ranitidina"),
        ("Diazepam", "diazepam"), ("Clonazepam", "clonazepam"),
        ("Haloperidol", "haloperidol"), ("Risperidone", "risperidona"),
        ("Sertraline", "cloridrato de sertralina"),
        ("Amitriptyline", "cloridrato de amitriptilina"),
        ("Tramadol", "cloridrato de tramadol"),
        ("Morphine", "sulfato de morfina"), ("Codeine", "fosfato de codeina"),
        ("Paracetamol", "paracetamol"), ("Dipyrone", "dipirona sodica"),
        ("Atenolol", "atenolol"), ("Propranolol", "cloridrato de propranolol"),
        ("Nifedipine", "nifedipino"), ("Amlodipine", "besilato de anlodipino"),
        ("Ethanol", "alcool etilico"),
        ("Theophylline", "teofilina"), ("Ceftriaxone", "ceftriaxona sodica"),
        ("Insulin glargine", "insulina glargina"),
        ("Acyclovir", "aciclovir"), ("Fluconazole", "fluconazol"),
        ("Ketoconazole", "cetoconazol"), ("Rifampicin", "rifampicina"),
        ("Isoniazid", "isoniazida"), ("Cyclosporine", "ciclosporina"),
    ]
    ok = bad = 0
    falhas = []
    for en, pt in PARES:
        a, b = skeleton(en), skeleton(pt)
        if a == b:
            ok += 1
        else:
            bad += 1
            falhas.append((en, pt, a, b))
    print("VALIDACAO DO NORMALIZADOR")
    print("  acertos: %d / %d  (%.1f%%)" % (ok, len(PARES), 100.0 * ok / len(PARES)))
    print("  FALHAS (%d):" % bad)
    for en, pt, a, b in falhas:
        print("    %-26s %-32s  '%s'  !=  '%s'" % (en, pt, a, b))

    # ---- teste de FALSO POSITIVO: farmacos distintos NAO podem colidir ----
    DISTINTOS = [
        ("Nifedipine", "Nimodipine"), ("Nifedipine", "Nicardipine"),
        ("Amlodipine", "Amiodarone"), ("Prednisone", "Prednisolone"),
        ("Cefazolin", "Cefalexin"), ("Cefotaxime", "Cefoxitin"),
        ("Diazepam", "Lorazepam"), ("Clonazepam", "Clobazam"),
        ("Fluoxetine", "Paroxetine"), ("Sertraline", "Sertindole"),
        ("Metformin", "Metronidazole"), ("Ranitidine", "Rifampicin"),
        ("Vincristine", "Vinblastine"), ("Doxorubicin", "Daunorubicin"),
        ("Hydralazine", "Hydroxyzine"), ("Glipizide", "Glyburide"),
        ("Chlorpromazine", "Chlorpropamide"), ("Tramadol", "Trazodone"),
        ("Carbamazepine", "Oxcarbazepine"), ("Insulin lispro", "Insulin aspart"),
        ("Atenolol", "Acebutolol"), ("Codeine", "Colchicine"),
        ("Morphine", "Methadone"), ("Digoxin", "Digitoxin"),
        ("Warfarin", "Ibuprofen"), ("Lithium", "Lidocaine"),
        ("Tamoxifen", "Tamsulosin"), ("Quinine", "Quinidine"),
        ("Nortriptyline", "Amitriptyline"), ("Cimetidine", "Cinnarizine"),
    ]
    col = 0
    print()
    print("TESTE DE FALSO POSITIVO (farmacos distintos devem ter chaves distintas)")
    for a, b in DISTINTOS:
        if skeleton(a) == skeleton(b):
            col += 1
            print("    COLISAO: %s == %s -> '%s'" % (a, b, skeleton(a)))
    print("  colisoes: %d / %d pares" % (col, len(DISTINTOS)))
