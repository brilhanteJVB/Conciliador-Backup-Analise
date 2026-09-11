# -*- coding: utf-8 -*-
"""
O ESPACO DE ATRIBUTOS — definido AQUI e em lugar nenhum mais.

POR QUE ESTE ARQUIVO E UNICO
----------------------------
No sistema anterior o espaco de atributos estava duplicado entre o script de
treino e o de predicao, e quebrou silenciosamente quando o ATC foi
acrescentado: o modelo passou a receber colunas em ordem diferente da que
aprendeu. Aqui treino e predicao importam a MESMA funcao, e `20_treinar.py`
grava `models/espaco_features.json`; `70_predizer.py` aborta se divergir.

TRES REGRAS QUE OS ATRIBUTOS OBEDECEM
-------------------------------------
1. SIMETRIA. O alvo (existe interacao entre A e B?) e simetrico, logo todo
   atributo tambem e: contagem de lados, soma, min/max, ou-logico. Nunca
   "valor de A" numa coluna e "valor de B" em outra — isso ensinaria a ordem
   do id, que nao e farmacologia. O autoteste verifica par por par.

2. NENHUM ATRIBUTO SAI DA FONTE DO ROTULO. ATC vem da OMS, tarja e numero de
   produtos vem da CMED, papel CYP vem da FDA, regra de administracao vem do
   DrugBank/bulas. Nenhuma dessas fontes afirma interacao farmaco x farmaco.
   As colunas que descrevem a propria interacao (tipo, gravidade, mecanismo,
   efeito, descricao) estao listadas em 01_auditoria_dataset.COLUNAS_CIRCULARES
   e nao aparecem aqui.

3. O BLOCO GRAFO E DECLARADAMENTE DERIVADO DO ROTULO. Grau, vizinhos comuns e
   Adamic-Adar sao contagens de arestas — ou seja, de rotulos positivos. Ficam
   num bloco separado, sao calculados SO com as arestas do conjunto de treino,
   e existe ablacao sem eles. Um modelo que depende deles nao serve para o
   problema real do projeto: as 1.137 substancias de grau zero.

O 5o NIVEL DO ATC NAO ENTRA. Medido em 01: nenhum codigo de 5o nivel e
compartilhado por duas substancias — o 5o nivel E a substancia, e usa-lo seria
entregar o identificador ao modelo.

Autoteste: python ml/_features.py
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import conectar

BLOCOS = ("ATC", "REG", "ADM", "PK", "GRAFO")

# Valores fechados, lidos do banco em 09/09/2026 e fixados aqui para que o
# espaco de atributos nao mude de tamanho quando uma carga nova acrescentar
# uma categoria. Categoria nova exige alteracao explicita e novo treino.
TARJAS = ("MIP", "TARJA_VERMELHA", "TARJA_VERMELHA_RETENCAO", "TARJA_PRETA")
TIPOS_ADM = ("INDIFERENTE_ALIMENTO", "COM_ALIMENTO", "JEJUM",
             "COM_AGUA_ABUNDANTE", "CONFORME_SINTOMA",
             "NAO_PARTIR_NAO_TRITURAR", "ANTES_ALIMENTO", "APOS_ALIMENTO",
             "SUBLINGUAL")
ATC_N1 = tuple("ABCDGHJLMNPRSV")


@dataclass
class Contexto:
    """Tudo o que o construtor de atributos precisa, carregado uma vez.

    `adjacencia` e `grau` vem SEMPRE do conjunto de treino. Passar o grafo
    inteiro aqui e o erro de vazamento classico desta tarefa, e por isso o
    campo `origem_grafo` e obrigatorio e vai gravado no resultado.
    """
    atc: dict = field(default_factory=dict)          # id -> codigo ATC (7 ch)
    tarja: dict = field(default_factory=dict)         # id -> canal_dispensacao
    n_produtos: dict = field(default_factory=dict)    # id -> int
    tem_cas: dict = field(default_factory=dict)
    tem_dcb: dict = field(default_factory=dict)
    adm: dict = field(default_factory=dict)           # id -> set(tipo)
    pk: dict = field(default_factory=dict)            # id -> set((sistema,papel))
    adjacencia: dict = field(default_factory=dict)    # id -> set(id)
    grau: dict = field(default_factory=dict)
    atc_n2_vistos: tuple = ()
    origem_grafo: str = "NAO_DEFINIDA"


def carregar_contexto(con, arestas_treino=None,
                      origem_grafo="NAO_DEFINIDA") -> Contexto:
    """Le os atributos por substancia. `arestas_treino` monta o grafo.

    arestas_treino=None produz grafo VAZIO (grau zero para todos) — e o que
    se usa quando o bloco GRAFO nao entra, e o que garante que esquecer de
    passar o treino nao vaze o grafo inteiro por acidente.
    """
    c = Contexto(origem_grafo=origem_grafo)
    for sid, atc, tarja, nprod, cas, dcb in con.execute(
            "SELECT id, atc_codigo, canal_dispensacao, n_produtos_ativos, "
            "cas, dcb_numero FROM substancia"):
        if atc:
            c.atc[sid] = atc
        if tarja:
            c.tarja[sid] = tarja
        c.n_produtos[sid] = nprod or 0
        c.tem_cas[sid] = 1 if cas else 0
        c.tem_dcb[sid] = 1 if dcb else 0
    for sid, tipo in con.execute(
            "SELECT substancia_id, tipo FROM regra_administracao"):
        c.adm.setdefault(sid, set()).add(tipo)
    for sid, sistema, papel in con.execute(
            "SELECT substancia_id, sistema, papel FROM papel_farmacocinetico"):
        c.pk.setdefault(sid, set()).add((sistema, papel))

    # Niveis 2 vistos: fixa a ordem das colunas de forma reproduzivel.
    c.atc_n2_vistos = tuple(sorted({a[:3] for a in c.atc.values()}))

    if arestas_treino:
        for a, b in arestas_treino:
            c.adjacencia.setdefault(a, set()).add(b)
            c.adjacencia.setdefault(b, set()).add(a)
        c.grau = {k: len(v) for k, v in c.adjacencia.items()}
    return c


# ------------------------------------------------------------ espaco de nomes

def espaco(ctx: Contexto, blocos=BLOCOS) -> list[str]:
    """Nomes das colunas, na ordem exata em que `construir` as produz."""
    nomes: list[str] = []
    if "ATC" in blocos:
        nomes += ["atc_lados_com_codigo",
                  "atc_n1_igual", "atc_n2_igual", "atc_n3_igual", "atc_n4_igual"]
        nomes += ["atc_grupo1_%s" % g for g in ATC_N1]
        nomes += ["atc_grupo2_%s" % g for g in ctx.atc_n2_vistos]
    if "REG" in blocos:
        nomes += ["tarja_%s" % t for t in TARJAS]
        nomes += ["tarja_desconhecida_lados",
                  "produtos_log_min", "produtos_log_max", "produtos_log_soma",
                  "lados_com_cas", "lados_com_dcb"]
    if "ADM" in blocos:
        nomes += ["adm_lados_com_regra", "adm_mesmo_tipo"]
        nomes += ["adm_tipo_%s" % t for t in TIPOS_ADM]
    if "PK" in blocos:
        nomes += ["pk_lados_com_papel", "pk_inibidores", "pk_indutores",
                  "pk_substratos", "pk_mesmo_sistema",
                  "pk_inibidor_x_substrato", "pk_indutor_x_substrato"]
    if "GRAFO" in blocos:
        nomes += ["g_grau_log_min", "g_grau_log_max", "g_grau_log_soma",
                  "g_vizinhos_comuns", "g_jaccard", "g_adamic_adar",
                  "g_ligacao_preferencial_log"]
    return nomes


# ------------------------------------------------------------- construcao

def construir(ctx: Contexto, pares, blocos=BLOCOS) -> np.ndarray:
    """Matriz (n_pares x n_atributos), float32, na ordem de `espaco`."""
    n_col = len(espaco(ctx, blocos))
    X = np.zeros((len(pares), n_col), dtype=np.float32)
    idx_n2 = {g: i for i, g in enumerate(ctx.atc_n2_vistos)}
    idx_n1 = {g: i for i, g in enumerate(ATC_N1)}
    idx_tarja = {t: i for i, t in enumerate(TARJAS)}
    idx_adm = {t: i for i, t in enumerate(TIPOS_ADM)}

    for r, (a, b) in enumerate(pares):
        j = 0
        if "ATC" in blocos:
            ca, cb = ctx.atc.get(a), ctx.atc.get(b)
            X[r, j] = (ca is not None) + (cb is not None)
            j += 1
            for tam in (1, 3, 4, 5):
                X[r, j] = 1.0 if (ca and cb and ca[:tam] == cb[:tam]) else 0.0
                j += 1
            base = j
            for c in (ca, cb):
                if c and c[0] in idx_n1:
                    X[r, base + idx_n1[c[0]]] += 1.0
            j = base + len(ATC_N1)
            base = j
            for c in (ca, cb):
                if c and c[:3] in idx_n2:
                    X[r, base + idx_n2[c[:3]]] += 1.0
            j = base + len(ctx.atc_n2_vistos)

        if "REG" in blocos:
            base = j
            desconhecida = 0
            for s in (a, b):
                t = ctx.tarja.get(s)
                if t in idx_tarja:
                    X[r, base + idx_tarja[t]] += 1.0
                else:
                    desconhecida += 1
            j = base + len(TARJAS)
            X[r, j] = desconhecida
            j += 1
            pa = math.log1p(ctx.n_produtos.get(a, 0))
            pb = math.log1p(ctx.n_produtos.get(b, 0))
            X[r, j] = min(pa, pb); j += 1
            X[r, j] = max(pa, pb); j += 1
            X[r, j] = pa + pb; j += 1
            X[r, j] = ctx.tem_cas.get(a, 0) + ctx.tem_cas.get(b, 0); j += 1
            X[r, j] = ctx.tem_dcb.get(a, 0) + ctx.tem_dcb.get(b, 0); j += 1

        if "ADM" in blocos:
            ta, tb = ctx.adm.get(a, set()), ctx.adm.get(b, set())
            X[r, j] = (1 if ta else 0) + (1 if tb else 0); j += 1
            X[r, j] = 1.0 if (ta and tb and ta & tb) else 0.0; j += 1
            base = j
            for t in list(ta) + list(tb):
                if t in idx_adm:
                    X[r, base + idx_adm[t]] += 1.0
            j = base + len(TIPOS_ADM)

        if "PK" in blocos:
            pa_, pb_ = ctx.pk.get(a, set()), ctx.pk.get(b, set())
            todos = list(pa_) + list(pb_)
            X[r, j] = (1 if pa_ else 0) + (1 if pb_ else 0); j += 1
            X[r, j] = sum(1 for _, p in todos if p == "INIBIDOR"); j += 1
            X[r, j] = sum(1 for _, p in todos if p == "INDUTOR"); j += 1
            X[r, j] = sum(1 for _, p in todos if p == "SUBSTRATO"); j += 1
            sist_a = {s for s, _ in pa_}
            sist_b = {s for s, _ in pb_}
            X[r, j] = 1.0 if sist_a & sist_b else 0.0; j += 1
            # Par mecanistico: um inibe o CYP do qual o outro e substrato.
            # E a unica combinacao de atributos que carrega mecanismo, e nao
            # so associacao — vale nos dois sentidos, logo e simetrica.
            inib_a = {s for s, p in pa_ if p == "INIBIDOR"}
            inib_b = {s for s, p in pb_ if p == "INIBIDOR"}
            indu_a = {s for s, p in pa_ if p == "INDUTOR"}
            indu_b = {s for s, p in pb_ if p == "INDUTOR"}
            subs_a = {s for s, p in pa_ if p == "SUBSTRATO"}
            subs_b = {s for s, p in pb_ if p == "SUBSTRATO"}
            X[r, j] = 1.0 if (inib_a & subs_b) or (inib_b & subs_a) else 0.0
            j += 1
            X[r, j] = 1.0 if (indu_a & subs_b) or (indu_b & subs_a) else 0.0
            j += 1

        if "GRAFO" in blocos:
            va = ctx.adjacencia.get(a, set())
            vb = ctx.adjacencia.get(b, set())
            ga, gb = len(va), len(vb)
            la, lb = math.log1p(ga), math.log1p(gb)
            X[r, j] = min(la, lb); j += 1
            X[r, j] = max(la, lb); j += 1
            X[r, j] = la + lb; j += 1
            comuns = va & vb
            X[r, j] = len(comuns); j += 1
            uniao = len(va | vb)
            X[r, j] = (len(comuns) / uniao) if uniao else 0.0; j += 1
            aa = 0.0
            for z in comuns:
                gz = len(ctx.adjacencia.get(z, ()))
                if gz > 1:
                    aa += 1.0 / math.log(gz)
            X[r, j] = aa; j += 1
            X[r, j] = math.log1p(ga * gb); j += 1

        assert j == n_col, (j, n_col)
    return X


# ---------------------------------------------------------------- autoteste

def _autoteste() -> int:
    print("AUTOTESTE DO ESPACO DE ATRIBUTOS")
    con = conectar()
    arestas = con.execute("SELECT DISTINCT substancia_a_id, substancia_b_id "
                          "FROM interacao_substancia LIMIT 20000").fetchall()
    ctx = carregar_contexto(con, arestas, origem_grafo="AUTOTESTE")
    nomes = espaco(ctx)
    falhas = []

    print("  atributos no espaco completo: %d" % len(nomes))
    for b in BLOCOS:
        print("    bloco %-6s %3d atributos" % (b, len(espaco(ctx, (b,)))))
    if len(nomes) != len(set(nomes)):
        falhas.append("nome de atributo repetido")

    # 1. simetria: construir(a,b) == construir(b,a)
    amostra = arestas[:400]
    X1 = construir(ctx, amostra)
    X2 = construir(ctx, [(b, a) for a, b in amostra])
    if not np.array_equal(X1, X2):
        dif = np.where(~np.isclose(X1, X2))
        falhas.append("ASSIMETRIA em %d celulas, colunas %s"
                      % (len(dif[0]), sorted({nomes[c] for c in dif[1]})[:5]))
    else:
        print("  simetria: 400 pares, construir(a,b) == construir(b,a)  OK")

    # 2. largura da matriz igual ao espaco declarado
    if X1.shape[1] != len(nomes):
        falhas.append("largura %d != espaco %d" % (X1.shape[1], len(nomes)))
    else:
        print("  largura da matriz == len(espaco())  OK")

    # 3. sem NaN nem infinito
    if not np.isfinite(X1).all():
        falhas.append("NaN ou infinito na matriz")
    else:
        print("  nenhum NaN/infinito  OK")

    # 4. grafo vazio produz bloco GRAFO todo zero (nao vaza por acidente)
    ctx0 = carregar_contexto(con, None, origem_grafo="VAZIO")
    Xg = construir(ctx0, amostra, ("GRAFO",))
    if Xg.any():
        falhas.append("bloco GRAFO nao zerou com grafo vazio")
    else:
        print("  grafo vazio -> bloco GRAFO todo zero  OK")

    # 5. substancia fora do treino tem grau zero (o ponto cego, medido)
    fora = con.execute(
        "SELECT id FROM substancia WHERE id NOT IN "
        "(SELECT substancia_a_id FROM interacao_substancia "
        " UNION SELECT substancia_b_id FROM interacao_substancia) LIMIT 2"
    ).fetchall()
    if len(fora) == 2:
        Xf = construir(ctx, [(fora[0][0], fora[1][0])], ("GRAFO",))
        if Xf.any():
            falhas.append("substancia de grau zero recebeu atributo de grafo")
        else:
            print("  substancia de grau zero -> atributos de grafo zerados  OK")

    # 6. o 5o nivel do ATC nao aparece em nenhum nome de coluna
    if any(len(n.split("_")[-1]) == 7 and n.startswith("atc_grupo")
           for n in nomes):
        falhas.append("codigo ATC de 5o nivel usado como atributo")
    else:
        print("  nenhum atributo usa ATC de 5o nivel  OK")

    # 7. nenhum nome de coluna vem de tabela do rotulo
    proibidos = ("gravidade", "tipo_interacao", "mecanismo", "efeito",
                 "descricao", "prioridade")
    ruim = [n for n in nomes if any(p in n for p in proibidos)]
    if ruim:
        falhas.append("atributo com nome de coluna circular: %s" % ruim)
    else:
        print("  nenhum atributo derivado da tabela de interacao  OK")

    print()
    if falhas:
        for f in falhas:
            print("  FALHA: %s" % f)
        return 1
    print("AUTOTESTE OK — %d atributos, todos simetricos." % len(nomes))
    return 0


if __name__ == "__main__":
    sys.exit(_autoteste())
