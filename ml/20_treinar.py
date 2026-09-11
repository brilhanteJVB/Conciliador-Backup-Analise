# -*- coding: utf-8 -*-
"""
COMPARACAO DAS FAMILIAS DE MODELO — o experimento principal.

O QUE ESTE SCRIPT NAO FAZ
-------------------------
Nao escolhe o modelo. Ele mede. A escolha e feita em 50_comparacao.py, com a
tabela inteira na frente, considerando tambem custo e interpretabilidade.

DISCIPLINA DO EXPERIMENTO
-------------------------
* O limiar de decisao e escolhido SEMPRE na validacao e aplicado ao teste.
  Escolher limiar no teste e a forma mais comum de inflar F1 sem perceber.
* O grafo dos atributos e montado SO com as arestas positivas do treino
  daquele split. Isso e recalculado por split, e a origem vai gravada.
* Peso de classe, quando usado, entra so no treino (familia
  LOGISTICA_PESO_BALANCEADO). Validacao e teste nunca sao reamostrados,
  reponderados ou balanceados.
* Toda familia ve exatamente as mesmas linhas.

GRADE
-----
    splits          POR_PAR (otimista) e POR_FARMACO (duro)
    configuracoes   COMPLETO, SEM_GRAFO  (+ SO_ATC e SO_GRAFO em ablacao)
    familias        as 10 de _modelos.py

Saida: ml/saida/20_resultados.json
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _avaliacao import (avaliar, escolher_limiar_f1, escolher_limiar_recall,
                        formatar)
from _comum import SEMENTE, TREINO, conectar, gravar, linha, secao, titulo, versao_dados
from _features import carregar_contexto, construir, espaco
from _modelos import TODAS, Dados

CONFIGS = {
    "COMPLETO": ("ATC", "REG", "ADM", "PK", "GRAFO"),
    "SEM_GRAFO": ("ATC", "REG", "ADM", "PK"),
    # Ablacoes. Existem para separar tres coisas que a metrica agregada
    # confunde: classe farmacologica, popularidade do farmaco e estrutura do
    # grafo de rotulos.
    "SO_ATC": ("ATC",),                       # so classe farmacologica
    "SO_GRAFO": ("GRAFO",),                   # so estrutura de rotulo
    "SO_REG": ("REG",),                       # so popularidade/regulacao
    "SEM_POPULARIDADE": ("ATC", "ADM", "PK"),  # farmacologia sem popularidade
}
# Ablacoes rodam so com as duas familias que interessam comparar.
FAMILIAS_ABLACAO = ("LOGISTICA", "GRADIENT_BOOSTING")
SO_ABLACAO = ("SO_ATC", "SO_GRAFO", "SO_REG", "SEM_POPULARIDADE")


def montar_split(d, qual):
    """Devolve (mascaras, descricao). Mascara: treino, validacao, teste."""
    if qual == "POR_PAR":
        s = d["split_par"]
        return dict(treino=s == 0, validacao=s == 1, teste=s == 2), {}
    if qual == "POR_FARMACO":
        s = d["regime_farmaco"]
        fr = d["frieza"]
        return (dict(treino=s == 0, validacao=s == 1, teste=s == 2),
                dict(teste_QUENTE_FRIO=(s == 2) & (fr == 1),
                     teste_FRIO_FRIO=(s == 2) & (fr == 2)))
    raise ValueError(qual)


def main() -> int:
    con = conectar()
    d = np.load(TREINO / "dataset_m1.npz")
    a_id, b_id, y = d["a_id"], d["b_id"], d["y"].astype(np.int8)
    atc = {sid: c for sid, c in con.execute(
        "SELECT id, atc_codigo FROM substancia WHERE atc_codigo IS NOT NULL")}
    resultado = {"versao_dados": versao_dados(con), "semente": SEMENTE,
                 "execucoes": []}

    titulo("COMPARACAO DAS FAMILIAS — ALVO A (existe interacao documentada?)")
    print("Pares: %s   positivos: %s   prevalencia: %.3f"
          % ("{:,}".format(len(y)).replace(",", "."),
             "{:,}".format(int(y.sum())).replace(",", "."), y.mean()))

    for nome_split in ("POR_PAR", "POR_FARMACO"):
        masc, extras = montar_split(d, nome_split)
        secao("SPLIT %s" % nome_split)
        for k, m in masc.items():
            linha("  %s" % k, int(m.sum()), "positivos %d" % int(y[m].sum()))

        # grafo SO das arestas positivas de treino
        mt = masc["treino"]
        arestas_treino = list(zip(a_id[mt & (y == 1)].tolist(),
                                  b_id[mt & (y == 1)].tolist()))
        ctx = carregar_contexto(con, arestas_treino,
                               origem_grafo="TREINO_%s" % nome_split)
        linha("  arestas no grafo de atributos", len(arestas_treino),
              "(so positivas de treino)")
        linha("  substancias com grau>0 nesse grafo", len(ctx.grau))

        pares = list(zip(a_id.tolist(), b_id.tolist()))
        conjuntos = dict(masc)
        conjuntos.update(extras)

        for nome_cfg, blocos in CONFIGS.items():
            if nome_cfg in SO_ABLACAO and nome_split != "POR_FARMACO":
                continue
            nomes_attr = espaco(ctx, blocos)
            print("\n  configuracao %s — %d atributos"
                  % (nome_cfg, len(nomes_attr)))
            t0 = time.time()
            X = construir(ctx, pares, blocos)
            print("    matriz %s construida em %.1fs"
                  % (str(X.shape), time.time() - t0))

            dados = {}
            for k, m in conjuntos.items():
                dados[k] = Dados(X[m], y[m], [pares[i] for i in np.flatnonzero(m)],
                                 ctx, atc)

            for Fam in TODAS:
                if nome_cfg != "COMPLETO" and not Fam.usa_matriz:
                    continue        # familia sem matriz: uma vez por split
                if nome_cfg in SO_ABLACAO and Fam.nome not in FAMILIAS_ABLACAO:
                    continue
                f = Fam()
                t0 = time.time()
                f.treinar(dados["treino"])
                t_treino = time.time() - t0
                t0 = time.time()
                p_val = f.prever(dados["validacao"])
                t_prever = time.time() - t0
                lim_f1 = escolher_limiar_f1(dados["validacao"].y, p_val)
                lim_rec = escolher_limiar_recall(dados["validacao"].y, p_val)

                reg = dict(split=nome_split, configuracao=nome_cfg,
                           familia=f.nome, usa_matriz=Fam.usa_matriz,
                           n_atributos=len(nomes_attr) if Fam.usa_matriz else 0,
                           interpretabilidade=Fam.interpretabilidade,
                           custo=Fam.custo,
                           segundos_treino=t_treino,
                           segundos_previsao_por_1000=1000 * t_prever / max(1, len(p_val)),
                           limiar_f1=lim_f1, limiar_recall_alto=lim_rec,
                           conjuntos={})
                reg["conjuntos"]["validacao"] = avaliar(
                    dados["validacao"].y, p_val, lim_f1, lim_rec)
                for k in [c for c in conjuntos if c.startswith("teste")]:
                    p = f.prever(dados[k])
                    reg["conjuntos"][k] = avaliar(dados[k].y, p, lim_f1, lim_rec)
                resultado["execucoes"].append(reg)
                print(formatar("%s / teste" % f.nome, reg["conjuntos"]["teste"])
                      + "  (%.1fs)" % t_treino)
                if "teste_FRIO_FRIO" in reg["conjuntos"]:
                    print(formatar("   `-> FRIO_FRIO",
                                   reg["conjuntos"]["teste_FRIO_FRIO"]))
            del X, dados

    gravar("20_resultados.json", resultado)
    print("\n%d execucoes gravadas em ml/saida/20_resultados.json"
          % len(resultado["execucoes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
