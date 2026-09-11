# -*- coding: utf-8 -*-
"""
LACUNAS DO ACERVO PARA OS REQUISITOS NOVOS
==========================================
O sistema novo exige o que o anterior nao tinha: posologia estruturada,
horarios, regras de administracao (jejum / com alimento / intervalo) e
reacao adversa. Este script mede, com numero, o que o acervo sustenta.

Le a origem SOMENTE LEITURA. Saida: auditoria/saida/lacunas.json
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ORIGEM = Path(r"C:\Conteudos banco de dados tcc")
SAIDA = Path(r"C:\Sistema Conciliador projeto") / "auditoria" / "saida"
SAIDA.mkdir(parents=True, exist_ok=True)
csv.field_size_limit(10 * 1024 * 1024)

sys.path.insert(0, str(ORIGEM / "analise_dados" / "scripts"))
from lib_norm import skeleton  # noqa: E402

# ---------------------------------------------------------------- padroes
# Diretivas de administracao em ingles (DrugBank food-interactions)
DIRETIVA_EN = {
    "com_alimento": r"take with food|take with meal|administer with food|with meals",
    "jejum": r"empty stomach|before (?:a )?meal|1 hour before|two hours after|"
             r"take on an empty",
    "evitar_alcool": r"avoid alcohol",
    "evitar_laticinio": r"avoid (?:milk|dairy)|dairy product",
    "evitar_toranja": r"grapefruit",
    "separar_cations": r"antacid|calcium|iron|magnesium|aluminum|zinc|"
                       r"polyvalent cation",
    "com_agua": r"full glass of water|with water",
    "evitar_vitamina_k": r"vitamin k|leafy green",
    "sem_restricao": r"take with or without food|may be taken with or without",
}
# Diretivas em portugues (bulas ANVISA)
DIRETIVA_PT = {
    "jejum": r"\bem jejum\b|estomago vazio|est[oô]mago vazio",
    "com_alimento": r"(?:junto|juntamente)? ?com (?:as refei[cç][oõ]es|alimento"
                    r"|comida)|ap[oó]s as refei[cç][oõ]es|durante as refei[cç][oõ]es",
    "antes_refeicao": r"antes das refei[cç][oõ]es|antes da refei[cç][aã]o",
    "intervalo_horas": r"(?:intervalo|aguardar|esperar|separad\w+)[^.]{0,40}"
                       r"\b(\d{1,2})\s*(?:a\s*\d{1,2}\s*)?horas?",
    "nao_partir": r"n[aã]o (?:deve ser )?(?:partid|mastigad|triturad)",
    "sublingual": r"sublingual",
}
# Intervalo explicito de separacao entre farmacos (ingles)
RE_SEPARACAO = re.compile(
    r"(?:separat\w+|administer\w*|tak\w+|space\w*|apart)[^.]{0,60}?"
    r"\b(\d{1,2})\s*(?:to\s*\d{1,2}\s*)?h(?:ou)?rs?\b", re.I)
RE_HORAS_PT = re.compile(r"\b(\d{1,2})\s*horas?\b", re.I)


def conta_padroes(textos, padroes):
    r = Counter()
    for t in textos:
        for nome, pad in padroes.items():
            if re.search(pad, t, re.I):
                r[nome] += 1
    return r


def main() -> int:
    res = {}

    # ------------------------------------------------ 1) DrugBank food
    caminho = ORIGEM / "Drug to Food interactions Dataset.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    textos, por_farmaco = [], {}
    for reg in dados:
        t = " ".join(reg.get("food_interactions") or [])
        textos.append(t)
        por_farmaco[reg.get("name", "")] = t
    achados = conta_padroes(textos, DIRETIVA_EN)
    res["drugbank_food"] = {
        "farmacos": len(dados),
        "com_texto": sum(1 for t in textos if t.strip()),
        "diretivas_detectadas": dict(achados.most_common()),
        "cobertura_alguma_diretiva": sum(
            1 for t in textos if any(re.search(p, t, re.I) for p in DIRETIVA_EN.values())),
    }

    # ------------------------------------------------ 2) bulas ANVISA
    pasta = ORIGEM / "fontes_novas" / "01_anvisa_bulario" / "texto"
    arquivos = sorted(pasta.glob("*.txt"))
    txt_bulas, com_posologia = [], 0
    trechos_posologia = {}
    for a in arquivos:
        t = a.read_text(encoding="utf-8", errors="replace")
        txt_bulas.append(t)
        m = re.search(r"POSOLOGIA[^\n]{0,80}(.{0,4000})", t, re.S | re.I)
        if m:
            com_posologia += 1
            trechos_posologia[a.stem] = m.group(1)
    achados_pt = conta_padroes(txt_bulas, DIRETIVA_PT)
    achados_posol = conta_padroes(list(trechos_posologia.values()), DIRETIVA_PT)
    res["bulas_anvisa"] = {
        "bulas": len(arquivos),
        "com_secao_posologia": com_posologia,
        "diretivas_na_bula_inteira": dict(achados_pt.most_common()),
        "diretivas_dentro_da_posologia": dict(achados_posol.most_common()),
    }

    # ------------------------------------------------ 3) intervalo de separacao
    sep = Counter()
    exemplos = []
    n = 0
    with open(ORIGEM / "db_drug_interactions.csv", encoding="utf-8-sig", newline="") as fh:
        for linha in csv.DictReader(fh):
            n += 1
            d = linha.get("Interaction Description") or ""
            m = RE_SEPARACAO.search(d)
            if m:
                sep[m.group(1)] += 1
                if len(exemplos) < 5:
                    exemplos.append(d[:160])
    res["intervalo_separacao"] = {
        "registros_analisados": n,
        "com_intervalo_explicito": sum(sep.values()),
        "pct": round(100 * sum(sep.values()) / n, 3) if n else 0,
        "horas_citadas": dict(sep.most_common(8)),
        "exemplos": exemplos,
    }

    # ------------------------------------------------ 4) posologia estruturada?
    # existe alguma fonte com dose/frequencia em campo proprio?
    fontes_dose = {}
    p = ORIGEM / "Drug finder db w_o brands - deepseek_csv_20250915_dff2b8.csv"
    with open(p, encoding="utf-8-sig", newline="") as fh:
        r = list(csv.DictReader(fh))
    fontes_dose["drug_finder"] = {
        "linhas": len(r),
        "tem_Strength": sum(1 for x in r if (x.get("Strength") or "").strip()),
        "tem_Dosage_Form": sum(1 for x in r if (x.get("Dosage Form") or "").strip()),
        "tem_Route": sum(1 for x in r if (x.get("Route of Administration") or "").strip()),
        "tem_frequencia": 0,   # coluna inexistente
        "observacao": "traz concentracao e via, NAO traz frequencia nem horario",
    }
    res["posologia_estruturada"] = fontes_dose

    # ------------------------------------------------ 5) reacao adversa
    res["reacao_adversa"] = {
        "vigimed_reacoes": 1093739,
        "vinculo_verificado_pct": 94,
        "terminologia": "MedDRA em portugues (LLT/PT/HLT/HLGT/SOC)",
        "observacao": "notificacao espontanea: exige desproporcionalidade, nao contagem",
    }

    destino = SAIDA / "lacunas.json"
    destino.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    for k, v in res.items():
        print("=" * 70)
        print(k)
        print(json.dumps(v, ensure_ascii=False, indent=1)[:1400])
    print("\nOK ->", destino)
    return 0


if __name__ == "__main__":
    sys.exit(main())
