# -*- coding: utf-8 -*-
"""
AS FAMILIAS DE MODELO COMPARADAS — todas atras da mesma interface.

Nenhuma familia foi escolhida antes de medir. Estao aqui em ordem crescente
de complexidade, e cada uma declara custo e interpretabilidade para que a
tabela de comparacao final nao seja so metrica.

    1  PREVALENCIA .............. constante. E o piso: qualquer modelo que
                                  nao passe daqui nao existe.
    2  REGRA_ATC_N2 ............. regra deterministica de duas celulas:
                                  "os dois farmacos sao do mesmo subgrupo
                                  terapeutico?". Interpretabilidade maxima.
    3  TABELA_CLASSE_x_CLASSE ... taxa observada no treino para cada par de
                                  subgrupos ATC. Uma tabela, sem gradiente.
                                  E o modelo mais explicavel que existe para
                                  um farmaceutico: "nesta base, 34% dos pares
                                  entre B01 e N02 tem interacao afirmada".
    4  LOGISTICA ................ linear, coeficiente por atributo, e a
                                  contribuicao por previsao e exata (nao
                                  precisa de SHAP para ser explicada).
    5  LOGISTICA_PESO_BALANCEADO  igual, com peso de classe no treino.
    6  ARVORE ................... uma arvore de profundidade 6, legivel
                                  inteira em uma pagina.
    7  FLORESTA ................. 120 arvores; ganha em desempenho, perde a
                                  leitura direta.
    8  GRADIENT_BOOSTING ........ histogram-based do scikit-learn (mesma
                                  familia do LightGBM, sem dependencia nova).
    9  SVM_LINEAR ............... margem maxima. Treinado em subamostra e com
                                  Platt para virar probabilidade — o custo
                                  quadratico do kernel nao cabe em 320 mil
                                  linhas, e isso e limitacao declarada, nao
                                  omissao.
   10  GRAFO_ADAMIC_ADAR ........ o representante da familia de GRAFO. Nao e
                                  GNN: e a heuristica de predicao de ligacao
                                  que a literatura de grafo usa como base, e
                                  serve para responder se a estrutura de
                                  vizinhanca tem algo a oferecer AQUI antes de
                                  investir numa rede sobre grafo.

XGBoost e LightGBM nao estao instalados nesta maquina e nao foram
acrescentados: `HistGradientBoostingClassifier` e a mesma tecnica
(boosting por histograma) e o projeto sera empacotado num .exe, onde cada
dependencia nova pesa. Registrado como decisao, nao como falta.
"""
from __future__ import annotations

import collections
import math

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from sklearn.tree import DecisionTreeClassifier

SEMENTE_MODELO = 20260909
LIMITE_SVM = 60000          # linhas na subamostra do SVM


class Dados:
    """O que uma familia recebe. Um objeto, para nenhuma assinatura divergir."""

    def __init__(self, X, y, pares, ctx, atc):
        self.X = X
        self.y = y
        self.pares = pares
        self.ctx = ctx          # Contexto de _features (grafo SO de treino)
        self.atc = atc          # dict id -> codigo ATC


class Familia:
    nome = "?"
    usa_matriz = True
    interpretabilidade = "?"
    custo = "?"

    def treinar(self, d: Dados) -> None:
        raise NotImplementedError

    def prever(self, d: Dados) -> np.ndarray:
        raise NotImplementedError


# ------------------------------------------------------------------ 1. piso

class Prevalencia(Familia):
    nome = "PREVALENCIA"
    usa_matriz = False
    interpretabilidade = "total (um numero)"
    custo = "nulo"

    def treinar(self, d):
        self.p = float(d.y.mean())

    def prever(self, d):
        return np.full(len(d.y), self.p)


# --------------------------------------------------------------- 2. regra

class RegraAtcN2(Familia):
    nome = "REGRA_ATC_N2"
    usa_matriz = False
    interpretabilidade = "total (uma pergunta)"
    custo = "nulo"

    def _regra(self, d):
        out = np.zeros(len(d.pares), dtype=bool)
        for i, (a, b) in enumerate(d.pares):
            ca, cb = d.atc.get(a), d.atc.get(b)
            out[i] = bool(ca and cb and ca[:3] == cb[:3])
        return out

    def treinar(self, d):
        m = self._regra(d)
        self.p_sim = float(d.y[m].mean()) if m.any() else float(d.y.mean())
        self.p_nao = float(d.y[~m].mean()) if (~m).any() else float(d.y.mean())

    def prever(self, d):
        m = self._regra(d)
        return np.where(m, self.p_sim, self.p_nao)


# --------------------------------------------------------------- 3. tabela

class TabelaClasseClasse(Familia):
    """Taxa de positivo por par de subgrupos ATC (nivel 2), com suavizacao.

    A suavizacao e de Laplace com forca `k`: celula com pouca observacao puxa
    para a taxa global em vez de afirmar 0% ou 100% a partir de tres exemplos.
    """
    nome = "TABELA_CLASSE_x_CLASSE"
    usa_matriz = False
    interpretabilidade = "total (uma tabela consultavel)"
    custo = "baixo"
    k = 30.0

    def _chave(self, d, i):
        a, b = d.pares[i]
        ca, cb = d.atc.get(a), d.atc.get(b)
        if not ca or not cb:
            return None
        x, y = ca[:3], cb[:3]
        return (x, y) if x <= y else (y, x)

    def treinar(self, d):
        soma = collections.Counter()
        cont = collections.Counter()
        for i in range(len(d.pares)):
            c = self._chave(d, i)
            if c is None:
                continue
            soma[c] += int(d.y[i])
            cont[c] += 1
        self.global_ = float(d.y.mean())
        self.tab = {c: (soma[c] + self.k * self.global_) / (cont[c] + self.k)
                    for c in cont}
        self.cont = dict(cont)

    def prever(self, d):
        out = np.empty(len(d.pares))
        for i in range(len(d.pares)):
            c = self._chave(d, i)
            out[i] = self.tab.get(c, self.global_) if c else self.global_
        return out


# ---------------------------------------------------------- 4/5. logistica

class Logistica(Familia):
    nome = "LOGISTICA"
    interpretabilidade = "alta (coeficiente por atributo)"
    custo = "baixo"
    peso = None

    def treinar(self, d):
        self.esc = StandardScaler().fit(d.X)
        self.m = LogisticRegression(max_iter=3000, C=1.0,
                                    class_weight=self.peso,
                                    random_state=SEMENTE_MODELO)
        self.m.fit(self.esc.transform(d.X), d.y)

    def prever(self, d):
        return self.m.predict_proba(self.esc.transform(d.X))[:, 1]


class LogisticaPeso(Logistica):
    nome = "LOGISTICA_PESO_BALANCEADO"
    peso = "balanced"
    interpretabilidade = "alta (coeficiente por atributo)"


# --------------------------------------------------------------- 6/7. arvores

class Arvore(Familia):
    nome = "ARVORE"
    interpretabilidade = "alta (arvore legivel)"
    custo = "baixo"

    def treinar(self, d):
        self.m = DecisionTreeClassifier(max_depth=6, min_samples_leaf=200,
                                        random_state=SEMENTE_MODELO)
        self.m.fit(d.X, d.y)

    def prever(self, d):
        return self.m.predict_proba(d.X)[:, 1]


class Floresta(Familia):
    nome = "FLORESTA"
    interpretabilidade = "media (importancia, sem regra unica)"
    custo = "alto"

    def treinar(self, d):
        self.m = RandomForestClassifier(n_estimators=120, min_samples_leaf=4,
                                        n_jobs=-1, random_state=SEMENTE_MODELO)
        self.m.fit(d.X, d.y)

    def prever(self, d):
        return self.m.predict_proba(d.X)[:, 1]


# ---------------------------------------------------------------- 8. boosting

class GradientBoosting(Familia):
    nome = "GRADIENT_BOOSTING"
    interpretabilidade = "media (importancia por permutacao)"
    custo = "medio"

    def treinar(self, d):
        self.m = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.1, max_leaf_nodes=31,
            early_stopping=True, validation_fraction=0.1,
            random_state=SEMENTE_MODELO)
        self.m.fit(d.X, d.y)

    def prever(self, d):
        return self.m.predict_proba(d.X)[:, 1]


# --------------------------------------------------------------------- 9. SVM

class SvmLinear(Familia):
    nome = "SVM_LINEAR"
    interpretabilidade = "media (peso por atributo)"
    custo = "alto (subamostra)"

    def treinar(self, d):
        g = np.random.default_rng(SEMENTE_MODELO)
        idx = (g.choice(len(d.y), size=LIMITE_SVM, replace=False)
               if len(d.y) > LIMITE_SVM else np.arange(len(d.y)))
        self.n_treino = int(len(idx))
        self.esc = StandardScaler().fit(d.X[idx])
        self.m = LinearSVC(C=0.1, dual="auto", max_iter=5000,
                           random_state=SEMENTE_MODELO)
        self.m.fit(self.esc.transform(d.X[idx]), d.y[idx])
        # Platt: transforma margem em probabilidade, ajustado no MESMO treino
        s = self.m.decision_function(self.esc.transform(d.X[idx])).reshape(-1, 1)
        self.platt = LogisticRegression(max_iter=1000).fit(s, d.y[idx])

    def prever(self, d):
        s = self.m.decision_function(self.esc.transform(d.X)).reshape(-1, 1)
        return self.platt.predict_proba(s)[:, 1]


# ------------------------------------------------------------------- 10. grafo

class GrafoAdamicAdar(Familia):
    """Heuristica de predicao de ligacao, calibrada por logistica de 1 variavel.

    A logistica so transforma o escore em probabilidade; e monotona, logo a
    AUC e exatamente a do Adamic-Adar cru. O grafo vem do Contexto, que por
    construcao tem somente as arestas de treino.
    """
    nome = "GRAFO_ADAMIC_ADAR"
    usa_matriz = False
    interpretabilidade = "alta (vizinhos em comum, listaveis)"
    custo = "baixo"

    def _escore(self, d):
        adj = d.ctx.adjacencia
        out = np.zeros((len(d.pares), 2))
        for i, (a, b) in enumerate(d.pares):
            va, vb = adj.get(a, set()), adj.get(b, set())
            comuns = va & vb
            aa = 0.0
            for z in comuns:
                gz = len(adj.get(z, ()))
                if gz > 1:
                    aa += 1.0 / math.log(gz)
            out[i, 0] = aa
            out[i, 1] = math.log1p(len(va) * len(vb))
        return out

    def treinar(self, d):
        self.m = LogisticRegression(max_iter=2000).fit(self._escore(d), d.y)

    def prever(self, d):
        return self.m.predict_proba(self._escore(d))[:, 1]


TODAS = [Prevalencia, RegraAtcN2, TabelaClasseClasse, Logistica, LogisticaPeso,
         Arvore, Floresta, GradientBoosting, SvmLinear, GrafoAdamicAdar]

# Familias que nao consomem a matriz de atributos: rodam uma vez por split,
# nao uma vez por configuracao de atributo.
SEM_MATRIZ = [f.nome for f in TODAS if not f.usa_matriz]
