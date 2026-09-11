# -*- coding: utf-8 -*-
"""
EXPLICABILIDADE — por que o modelo disse isso, em portugues.

TRES NIVEIS, PORQUE RESPONDEM A PERGUNTAS DIFERENTES
----------------------------------------------------
 1. GLOBAL, do modelo    quais atributos o modelo usa, no conjunto todo.
                         Metodo: importancia por permutacao (embaralha uma
                         coluna e mede quanto a AUC cai). Vale para qualquer
                         familia, inclusive as que nao tem coeficiente.
 2. GLOBAL, linear       coeficiente da regressao logistica: direcao e
                         tamanho, com sinal. E o que permite dizer "pertencer
                         ao mesmo subgrupo ATC aumenta a chance estimada".
 3. LOCAL, por previsao  contribuicao de cada atributo NAQUELE par.
                         Metodo: ocultacao uma-a-uma — recalcula a previsao
                         com o atributo no valor de referencia e mede a
                         diferenca. E uma APROXIMACAO de SHAP, nao SHAP: o
                         SHAP exato media todas as ordens de entrada, e a
                         biblioteca `shap` nao esta instalada nesta maquina.
                         O relatorio diz "contribuicao aproximada", nunca
                         "valor SHAP".

O LIMITE QUE NAO SE ATRAVESSA
-----------------------------
Contribuicao estatistica NAO e mecanismo farmacologico. O modelo pode pesar
"os dois sao do subgrupo C09" — isso e um padrao na base, nao uma explicacao
de como as moleculas interagem. Por isso o texto gerado aqui descreve o que o
modelo VIU, nunca o que acontece no corpo. Mecanismo continua vindo da fonte,
pelo caminho deterministico.

Saida: ml/saida/40_explicabilidade.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.inspection import permutation_importance

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import TREINO, conectar, gravar, linha, rng, secao, titulo, versao_dados
from _features import carregar_contexto, construir, espaco
from _modelos import Dados, GradientBoosting, Logistica

BLOCOS = ("ATC", "REG", "ADM", "PK")
N_AMOSTRA_PERM = 30000


def frase(nome_attr: str, valor: float, nomes_atc: dict) -> str:
    """Traduz um nome de atributo para portugues de balcao."""
    if nome_attr.startswith("atc_grupo2_"):
        cod = nome_attr.split("_")[-1]
        rot = nomes_atc.get(cod, cod)
        n = int(valor)
        if n == 2:
            return "os dois farmacos sao do subgrupo %s (%s)" % (cod, rot)
        if n == 1:
            return "um dos farmacos e do subgrupo %s (%s)" % (cod, rot)
        return "nenhum dos farmacos e do subgrupo %s" % cod
    if nome_attr.startswith("atc_grupo1_"):
        letra = nome_attr.split("_")[-1]
        rot = nomes_atc.get(letra, letra)
        return "%d dos farmacos e(sao) do grupo anatomico %s (%s)" % (
            int(valor), letra, rot)
    mapa = {
        "atc_n1_igual": "mesmo grupo anatomico",
        "atc_n2_igual": "mesmo subgrupo terapeutico",
        "atc_n3_igual": "mesmo subgrupo farmacologico",
        "atc_n4_igual": "mesmo subgrupo quimico",
        "atc_lados_com_codigo": "quantos lados tem classificacao ATC",
        "produtos_log_soma": "quantidade de apresentacoes no mercado (soma)",
        "produtos_log_max": "quantidade de apresentacoes do mais comercializado",
        "produtos_log_min": "quantidade de apresentacoes do menos comercializado",
        "lados_com_cas": "quantos lados tem registro CAS",
        "lados_com_dcb": "quantos lados tem numero DCB",
        "tarja_desconhecida_lados": "quantos lados estao sem tarja no cadastro",
        "adm_lados_com_regra": "quantos lados tem regra de administracao",
        "adm_mesmo_tipo": "os dois tem a mesma regra de administracao",
        "pk_lados_com_papel": "quantos lados tem papel CYP conhecido",
        "pk_inibidor_x_substrato":
            "um inibe a enzima da qual o outro e substrato",
        "pk_indutor_x_substrato":
            "um induz a enzima da qual o outro e substrato",
        "pk_mesmo_sistema": "os dois atuam na mesma enzima CYP",
        "pk_inibidores": "quantos inibidores de CYP no par",
        "pk_indutores": "quantos indutores de CYP no par",
        "pk_substratos": "quantos substratos de CYP no par",
    }
    if nome_attr.startswith("tarja_"):
        return "tarja %s em %d lado(s)" % (
            nome_attr[6:].lower().replace("_", " "), int(valor))
    if nome_attr.startswith("adm_tipo_"):
        return "regra de administracao %s em %d lado(s)" % (
            nome_attr[9:].lower().replace("_", " "), int(valor))
    return mapa.get(nome_attr, nome_attr)


def contribuicoes(modelo, dados_um, X_ref, nomes, k=6):
    """Ocultacao uma-a-uma. Devolve os k atributos de maior efeito."""
    base = modelo.prever(dados_um)[0]
    x = dados_um.X[0]
    variantes = np.repeat(x.reshape(1, -1), len(nomes), axis=0)
    for j in range(len(nomes)):
        variantes[j, j] = X_ref[j]
    d2 = Dados(variantes, np.zeros(len(nomes), np.int8),
               dados_um.pares * len(nomes), dados_um.ctx, dados_um.atc)
    p = modelo.prever(d2)
    efeito = base - p               # quanto CAI ao remover o atributo
    ordem = np.argsort(-np.abs(efeito))[:k]
    return float(base), [(nomes[j], float(x[j]), float(efeito[j])) for j in ordem]


def main() -> int:
    con = conectar()
    d = np.load(TREINO / "dataset_m1.npz")
    a_id, b_id = d["a_id"], d["b_id"]
    y = d["y"].astype(np.int8)
    regime = d["regime_farmaco"]
    pares = list(zip(a_id.tolist(), b_id.tolist()))
    atc = {s: c for s, c in con.execute(
        "SELECT id, atc_codigo FROM substancia WHERE atc_codigo IS NOT NULL")}
    nomes_atc = {c: (pt or en) for c, pt, en in con.execute(
        "SELECT codigo, nome_pt, nome_en FROM classe_atc")}
    nome_subst = {s: n for s, n in con.execute(
        "SELECT id, nome_dcb FROM substancia")}
    r = {"versao_dados": versao_dados(con)}

    titulo("EXPLICABILIDADE — modelo SEM_GRAFO, split POR_FARMACO")

    tr, va, te = regime == 0, regime == 1, regime == 2
    arestas = list(zip(a_id[tr & (y == 1)].tolist(), b_id[tr & (y == 1)].tolist()))
    ctx = carregar_contexto(con, arestas, origem_grafo="TREINO_POR_FARMACO")
    nomes = espaco(ctx, BLOCOS)
    X = construir(ctx, pares, BLOCOS)
    dtr = Dados(X[tr], y[tr], [pares[i] for i in np.flatnonzero(tr)], ctx, atc)
    dva = Dados(X[va], y[va], [pares[i] for i in np.flatnonzero(va)], ctx, atc)

    gb = GradientBoosting(); gb.treinar(dtr)
    lr = Logistica(); lr.treinar(dtr)

    # ---------------------------------------- 1. importancia por permutacao
    secao("1. IMPORTANCIA POR PERMUTACAO — gradient boosting (validacao)")
    g = rng(9)
    sel = g.choice(len(dva.y), size=min(N_AMOSTRA_PERM, len(dva.y)), replace=False)
    imp = permutation_importance(gb.m, X[va][sel], y[va][sel], n_repeats=3,
                                 random_state=20260909, scoring="roc_auc",
                                 n_jobs=-1)
    ordem = np.argsort(-imp.importances_mean)[:20]
    print("  atributo                                  queda de AUC ao embaralhar")
    perm = []
    for j in ordem:
        print("  %-44s %.4f  (+-%.4f)"
              % (nomes[j][:44], imp.importances_mean[j], imp.importances_std[j]))
        perm.append(dict(atributo=nomes[j], queda_auc=float(imp.importances_mean[j]),
                         desvio=float(imp.importances_std[j]),
                         em_portugues=frase(nomes[j], 1, nomes_atc)))
    r["importancia_permutacao"] = perm
    soma_atc = sum(imp.importances_mean[j] for j, n in enumerate(nomes)
                   if n.startswith("atc"))
    soma_reg = sum(imp.importances_mean[j] for j, n in enumerate(nomes)
                   if n.startswith(("produtos", "tarja", "lados_com")))
    soma_pk = sum(imp.importances_mean[j] for j, n in enumerate(nomes)
                  if n.startswith("pk"))
    soma_adm = sum(imp.importances_mean[j] for j, n in enumerate(nomes)
                   if n.startswith("adm"))
    print()
    for rot, v in (("bloco ATC (classe farmacologica)", soma_atc),
                   ("bloco REG (mercado e tarja)", soma_reg),
                   ("bloco ADM (regra de administracao)", soma_adm),
                   ("bloco PK (papel CYP)", soma_pk)):
        linha(rot, "%.4f" % v)
    r["importancia_por_bloco"] = dict(ATC=float(soma_atc), REG=float(soma_reg),
                                      ADM=float(soma_adm), PK=float(soma_pk))

    # ------------------------------------------- 2. coeficientes da logistica
    secao("2. COEFICIENTES — regressao logistica (direcao e tamanho)")
    coef = lr.m.coef_[0]
    ordem = np.argsort(-np.abs(coef))[:16]
    coefs = []
    for j in ordem:
        sinal = "aumenta" if coef[j] > 0 else "reduz"
        print("  %-44s %+.3f  (%s a chance estimada)"
              % (nomes[j][:44], coef[j], sinal))
        coefs.append(dict(atributo=nomes[j], coeficiente=float(coef[j]),
                          direcao=sinal,
                          em_portugues=frase(nomes[j], 1, nomes_atc)))
    r["coeficientes_logistica"] = coefs

    # ------------------------------------------------ 3. explicacao local
    secao("3. EXPLICACAO POR PREVISAO — ocultacao uma-a-uma")
    X_ref = np.median(X[tr], axis=0)         # valor de referencia = mediana
    exemplos_id = [int(i) for i in np.flatnonzero(te)[:0]]
    # escolhe 3 pares reais do teste: um positivo, um negativo, um par de
    # farmacos conhecidos de balcao se estiver disponivel
    idx_te = np.flatnonzero(te)
    p_te = gb.prever(Dados(X[te], y[te], [pares[i] for i in idx_te], ctx, atc))
    ordem_pos = idx_te[np.argsort(-p_te)]
    ordem_neg = idx_te[np.argsort(p_te)]
    escolhidos = [int(ordem_pos[0]), int(ordem_neg[0])]
    meio = idx_te[np.argsort(np.abs(p_te - 0.5))][0]
    escolhidos.append(int(meio))
    r["exemplos"] = []
    for i in escolhidos:
        a, b = pares[i]
        dum = Dados(X[i:i + 1], y[i:i + 1], [pares[i]], ctx, atc)
        base, contrib = contribuicoes(gb, dum, X_ref, nomes)
        print("\n  %s  x  %s" % (nome_subst.get(a, a), nome_subst.get(b, b)))
        print("    probabilidade estimada: %.3f   |   rotulo real: %s"
              % (base, "afirmado por fonte" if y[i] else "nao afirmado"))
        print("    o modelo pesou:")
        itens = []
        for nm, val, ef in contrib:
            txt = frase(nm, val, nomes_atc)
            seta = "+" if ef > 0 else "-"
            print("      [%s%.3f] %s" % (seta, abs(ef), txt))
            itens.append(dict(atributo=nm, valor=val, efeito=ef,
                              em_portugues=txt))
        r["exemplos"].append(dict(
            substancia_a=nome_subst.get(a), substancia_b=nome_subst.get(b),
            probabilidade=base, rotulo=int(y[i]), contribuicoes=itens))

    print("""
  LEITURA OBRIGATORIA JUNTO COM O NUMERO: nenhuma linha acima e mecanismo.
  "os dois sao do subgrupo C09" explica o que o MODELO viu; nao afirma que
  ha interacao farmacologica, nem qual seria. Se houver mecanismo conhecido,
  ele vem da fonte pelo caminho deterministico e aparece no achado
  DOCUMENTADO — nunca daqui.""")

    gravar("40_explicabilidade.json", r)
    print("\nGravado: ml/saida/40_explicabilidade.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
