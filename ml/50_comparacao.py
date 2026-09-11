# -*- coding: utf-8 -*-
"""
TABELA DE COMPARACAO E DECISAO.

Le tudo o que os scripts anteriores mediram e monta a tabela unica que a
especificacao §21 pede: modelo, atributos, split, tamanho, metricas,
calibracao, tempo, custo, interpretabilidade e limitacoes.

A REGRA DE DESEMPATE ESTA ESCRITA AQUI, ANTES DE OLHAR OS NUMEROS
-----------------------------------------------------------------
1. O regime que decide e o teste POR_FARMACO, e dentro dele o FRIO_FRIO. E o
   unico que se parece com o uso real: o farmaceutico consulta o sistema sobre
   o que ele nao conhece.
2. Diferenca de AUC menor que 0,02 entre duas familias e considerada empate.
   Em empate ganha a mais simples — a que explica melhor, custa menos e e mais
   facil de validar (principio §1 da especificacao).
3. Modelo que dependa de atributo indisponivel em producao esta fora,
   independentemente da metrica.

Saida: ml/saida/50_comparacao.json + docs/ML_COMPARACAO.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import RAIZ, gravar, ler, secao, titulo

EMPATE = 0.02


def v(x, casas=4):
    return "—" if x is None else ("%.*f" % (casas, x)).replace(".", ",")


def main() -> int:
    res = ler("20_resultados.json")
    rob = ler("25_robustez.json")
    cal = ler("30_calibracao.json")
    ex = res["execucoes"]

    titulo("COMPARACAO DAS FAMILIAS — TABELA UNICA")

    # ------------------------------------------------------- tabela geral
    linhas_md = []
    cab = ("| Familia | Atributos | n | Split | AUC teste | PR-AUC (piso) | "
           "F1 | Recall | Espec. | AUC FRIO_FRIO | ECE | Treino (s) | "
           "Interpretabilidade |")
    sep = "|" + "---|" * 13
    linhas_md += [cab, sep]
    print("  %-26s %-17s %-12s %8s %8s %9s %7s" % (
        "familia", "configuracao", "split", "AUC", "PR-AUC", "FRIO_FRIO", "seg"))
    for e in ex:
        t = e["conjuntos"]["teste"]
        ff = e["conjuntos"].get("teste_FRIO_FRIO", {})
        f1 = t.get("ponto_f1") or {}
        print("  %-26s %-17s %-12s %8s %8s %9s %7.1f" % (
            e["familia"][:26], e["configuracao"], e["split"],
            v(t.get("roc_auc")), v(t.get("pr_auc")), v(ff.get("roc_auc")),
            e["segundos_treino"]))
        linhas_md.append("| %s | %s (%d) | %d | %s | %s | %s (%s) | %s | %s | %s | %s | %s | %.1f | %s |" % (
            e["familia"], e["configuracao"], e["n_atributos"], t["n"], e["split"],
            v(t.get("roc_auc")), v(t.get("pr_auc")), v(t.get("pr_auc_piso"), 3),
            v(f1.get("f1"), 3), v(f1.get("recall"), 3),
            v(f1.get("especificidade"), 3), v(ff.get("roc_auc")),
            v(t.get("ece"), 3), e["segundos_treino"], e["interpretabilidade"]))

    # --------------------------------------------- o que decide: FRIO_FRIO
    secao("O REGIME QUE DECIDE — teste FRIO_FRIO, split POR_FARMACO")
    cand = [e for e in ex if e["split"] == "POR_FARMACO"
            and "teste_FRIO_FRIO" in e["conjuntos"]
            and e["conjuntos"]["teste_FRIO_FRIO"].get("roc_auc") is not None]
    cand.sort(key=lambda e: -e["conjuntos"]["teste_FRIO_FRIO"]["roc_auc"])
    print("  %-26s %-17s %9s %9s %8s" % ("familia", "configuracao",
                                         "AUC ff", "PR-AUC ff", "seg"))
    for e in cand[:14]:
        ff = e["conjuntos"]["teste_FRIO_FRIO"]
        print("  %-26s %-17s %9s %9s %8.1f" % (
            e["familia"][:26], e["configuracao"], v(ff["roc_auc"]),
            v(ff["pr_auc"]), e["segundos_treino"]))

    melhor = cand[0]
    auc_melhor = melhor["conjuntos"]["teste_FRIO_FRIO"]["roc_auc"]
    empatados = [e for e in cand
                 if auc_melhor - e["conjuntos"]["teste_FRIO_FRIO"]["roc_auc"] <= EMPATE]
    ordem_simplicidade = ["TABELA_CLASSE_x_CLASSE", "REGRA_ATC_N2", "LOGISTICA",
                          "LOGISTICA_PESO_BALANCEADO", "ARVORE", "SVM_LINEAR",
                          "GRADIENT_BOOSTING", "FLORESTA", "GRAFO_ADAMIC_ADAR",
                          "PREVALENCIA"]
    empatados.sort(key=lambda e: ordem_simplicidade.index(e["familia"]))
    escolhido = empatados[0]

    secao("APLICACAO DA REGRA DE DESEMPATE")
    print("  melhor AUC FRIO_FRIO: %s / %s = %s"
          % (melhor["familia"], melhor["configuracao"], v(auc_melhor)))
    print("  dentro da faixa de empate (%.2f de AUC): %d configuracoes"
          % (EMPATE, len(empatados)))
    for e in empatados:
        print("    - %s / %s  (AUC ff %s)"
              % (e["familia"], e["configuracao"],
                 v(e["conjuntos"]["teste_FRIO_FRIO"]["roc_auc"])))
    print("  mais simples entre as empatadas: %s / %s"
          % (escolhido["familia"], escolhido["configuracao"]))

    # ------------------------------------------------------- ablacoes
    secao("ABLACOES — de onde vem o desempenho")
    def busca(fam, cfg, split="POR_FARMACO"):
        for e in ex:
            if e["familia"] == fam and e["configuracao"] == cfg and e["split"] == split:
                return e
        return None
    print("  %-20s %-19s %9s %9s" % ("familia", "configuracao", "AUC teste", "AUC ff"))
    for fam in ("LOGISTICA", "GRADIENT_BOOSTING"):
        for cfg in ("COMPLETO", "SEM_GRAFO", "SO_ATC", "SO_REG",
                    "SEM_POPULARIDADE", "SO_GRAFO"):
            e = busca(fam, cfg)
            if not e:
                continue
            ff = e["conjuntos"].get("teste_FRIO_FRIO", {})
            print("  %-20s %-19s %9s %9s" % (
                fam[:20], cfg, v(e["conjuntos"]["teste"]["roc_auc"]),
                v(ff.get("roc_auc"))))

    # -------------------------------------------------------- robustez
    secao("ROBUSTEZ")
    for p in rob.get("pareado_grau", []):
        print("  pareado por grau  %-20s %-10s AUC %s  PR-AUC %s"
              % (p["familia"], p["configuracao"], v(p["teste"]["roc_auc"]),
                 v(p["teste"]["pr_auc"])))
    cn = rob.get("controle_negativo", {})
    if cn:
        print("  controle ao acaso: media %.3f  (positivos do teste %.3f, "
              "negativos %.3f)" % (cn["media_controle"],
                                   cn["media_positivos_teste"],
                                   cn["media_negativos_teste"]))
    for p in rob.get("rotulo_duas_fontes", []):
        print("  rotulo de 2 fontes %-20s AUC %s  PR-AUC %s"
              % (p["familia"], v(p["teste"]["roc_auc"]), v(p["teste"]["pr_auc"])))

    # ------------------------------------------------------- calibracao
    secao("CALIBRACAO")
    for c in cal.get("candidatos", []):
        cru = c["variantes"]["CRU"]["teste"]
        iso = c["variantes"]["ISOTONICA"]["teste"]
        print("  %-24s ECE cru %s -> isotonica %s   Brier %s -> %s"
              % (c["familia"][:24], v(cru["ece"], 4), v(iso["ece"], 4),
                 v(cru["brier"], 4), v(iso["brier"], 4)))

    saida = dict(regra_desempate=dict(regime="POR_FARMACO/FRIO_FRIO",
                                      faixa_empate=EMPATE,
                                      ordem_simplicidade=ordem_simplicidade),
                 melhor_metrica=dict(familia=melhor["familia"],
                                     configuracao=melhor["configuracao"],
                                     auc_frio_frio=auc_melhor),
                 empatados=[dict(familia=e["familia"],
                                 configuracao=e["configuracao"],
                                 auc_frio_frio=e["conjuntos"]["teste_FRIO_FRIO"]["roc_auc"])
                            for e in empatados],
                 escolhido=dict(familia=escolhido["familia"],
                                configuracao=escolhido["configuracao"]),
                 tabela_markdown=linhas_md)
    gravar("50_comparacao.json", saida)

    doc = RAIZ / "docs" / "ML_COMPARACAO.md"
    doc.write_text(
        "# Comparação das famílias de modelo — Fase 7\n\n"
        "Gerado por `ml/50_comparacao.py`. Não editar à mão.\n\n"
        "Regra de desempate, fixada antes de olhar os números: decide o teste\n"
        "`POR_FARMACO/FRIO_FRIO`; diferença de AUC menor que %.2f é empate; em\n"
        "empate ganha a família mais simples.\n\n" % EMPATE
        + "\n".join(linhas_md) + "\n",
        encoding="utf-8")
    print("\nGravado: ml/saida/50_comparacao.json e docs/ML_COMPARACAO.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
