# -*- coding: utf-8 -*-
"""
CONSTRUCAO DO DATASET E DOS SPLITS.

UNIVERSO — decidido em 02_auditoria_rotulos
-------------------------------------------
Todos os pares canonicos das 957 substancias que tem pelo menos uma interacao
afirmada. Sao 457.446 pares: 94.770 positivos (20,7%) e 362.676 negativos
PRESUMIDOS.

Nao ha amostragem de negativo no dataset principal. O universo entra inteiro,
com a prevalencia real. Amostrar negativo introduziria uma escolha a defender;
usar tudo nao introduz nenhuma. Balanceamento, quando necessario, e feito por
PESO DE CLASSE dentro do treino — nunca removendo ou replicando linha, e nunca
tocando validacao ou teste (especificacao §10).

Pares que envolvem as 1.137 substancias de grau zero ficam FORA: ali a
ausencia de linha e falta de cobertura da fonte, nao ausencia de interacao.
Chamar aquilo de negativo seria fabricar rotulo. Eles voltam no §20 como
controle negativo e no relatorio como o limite de aplicabilidade do modelo.

QUATRO SPLITS, PORQUE ELES MEDEM COISAS DIFERENTES
--------------------------------------------------
    POR_PAR       pares sorteados. Ambos os farmacos aparecem no treino.
                  E o protocolo da literatura, e o mais otimista.
    POR_FARMACO   farmacos sorteados; o treino usa so pares cujos DOIS lados
                  sao de treino. Isso parte o teste em tres regimes:
                    QUENTE_QUENTE  os dois lados conhecidos  (= POR_PAR)
                    QUENTE_FRIO    um lado inedito
                    FRIO_FRIO      os dois lados ineditos
                  FRIO_FRIO e o analogo mensuravel do ponto cego real.
    PAREADO_GRAU  subconjunto equilibrado em que cada negativo tem grau
                  parecido com o do positivo. Mede quanto do desempenho e
                  artefato de popularidade e nao farmacologia.
    ALEATORIO_PURO controle negativo do §20: pares sorteados sem nenhum
                  criterio, para ver se o modelo distribui probabilidade alta
                  indiscriminadamente.

O grafo usado pelos atributos do bloco GRAFO e montado SO com as arestas de
treino de cada split, e isso e gravado junto com o split para poder ser
conferido de fora.

Saida: data/training/dataset_m1.npz + ml/saida/10_dataset.json
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import (SEMENTE, TREINO, conectar, gravar, linha, pct, rng, secao,
                    titulo, versao_dados)

FRACAO = (0.70, 0.15, 0.15)   # treino / validacao / teste
N_BINS_GRAU = 10


def main() -> int:
    con = conectar()
    r = {"versao_dados": versao_dados(con), "semente": SEMENTE}
    mil = lambda n: "{:,}".format(int(n)).replace(",", ".")

    titulo("DATASET E SPLITS — ALVO A (existe interacao documentada?)")

    # ------------------------------------------------------------ universo
    secao("1. UNIVERSO")
    subst = sorted({s for (s,) in con.execute(
        "SELECT substancia_a_id FROM interacao_substancia "
        "UNION SELECT substancia_b_id FROM interacao_substancia")})
    n = len(subst)
    idx = {s: i for i, s in enumerate(subst)}

    # positivos e rotulos auxiliares por par
    pos = {}
    for a, b, nf, gmin, tipos in con.execute(
            "SELECT substancia_a_id, substancia_b_id, COUNT(*), MIN(gravidade), "
            "GROUP_CONCAT(DISTINCT tipo) FROM interacao_substancia "
            "GROUP BY 1,2"):
        pos[(a, b)] = (nf, gmin, tipos)
    linha("substancias no universo", n)
    linha("pares possiveis", n * (n - 1) // 2)
    linha("positivos", len(pos))
    linha("negativos presumidos", n * (n - 1) // 2 - len(pos))
    linha("prevalencia", pct(len(pos), n * (n - 1) // 2))

    # matriz triangular de todos os pares — indices locais i<j
    iu, ju = np.triu_indices(n, k=1)
    a_ids = np.array(subst, dtype=np.int32)[iu]
    b_ids = np.array(subst, dtype=np.int32)[ju]
    y = np.zeros(len(a_ids), dtype=np.int8)
    n_fontes = np.zeros(len(a_ids), dtype=np.int8)
    for k in range(len(a_ids)):
        p = pos.get((int(a_ids[k]), int(b_ids[k])))
        if p is not None:
            y[k] = 1
            n_fontes[k] = p[0]
    assert int(y.sum()) == len(pos), (int(y.sum()), len(pos))
    linha("linhas montadas", len(y))
    linha("positivos conferidos na matriz", int(y.sum()))

    # graus (grafo completo — usado para desenho de experimento, nunca como
    # atributo; atributo de grafo e sempre so do treino)
    grau = np.zeros(n, dtype=np.int32)
    for (a, b) in pos:
        grau[idx[a]] += 1
        grau[idx[b]] += 1

    # ------------------------------------------------------- split por par
    secao("2. SPLIT POR PAR — ambos os lados conhecidos (otimista)")
    g = rng(1)
    perm = g.permutation(len(y))
    c1 = int(FRACAO[0] * len(y))
    c2 = int((FRACAO[0] + FRACAO[1]) * len(y))
    split_par = np.zeros(len(y), dtype=np.int8)   # 0 treino, 1 val, 2 teste
    split_par[perm[c1:c2]] = 1
    split_par[perm[c2:]] = 2
    for k, nome in enumerate(("treino", "validacao", "teste")):
        m = split_par == k
        linha("%s" % nome, int(m.sum()),
              "positivos %s (%s)" % (mil(y[m].sum()), pct(int(y[m].sum()), int(m.sum()))))

    # --------------------------------------------------- split por farmaco
    secao("3. SPLIT POR FARMACO — o protocolo duro")
    # ESTRATIFICADO POR DECIL DE GRAU. Um sorteio simples de farmacos deixa a
    # prevalencia de positivo diferente entre os regimes (medido: 19,3% no
    # treino contra 23,4% no frio-frio), porque grau e muito desigual e 144
    # farmacos sorteados nao reproduzem a distribuicao. A diferenca nao e
    # defeito do dado, mas confunde a leitura: parte da variacao de metrica
    # viria da prevalencia, nao do regime. Estratificar por decil de grau
    # remove esse confundidor sem tocar no rotulo.
    g = rng(2)
    bins_g = np.quantile(grau, np.linspace(0, 1, N_BINS_GRAU + 1))
    decil = np.clip(np.digitize(grau, bins_g[1:-1]), 0, N_BINS_GRAU - 1)
    grupo = np.zeros(n, dtype=np.int8)            # 0 treino, 1 val, 2 teste
    for d in range(N_BINS_GRAU):
        membros = np.flatnonzero(decil == d)
        membros = membros[g.permutation(len(membros))]
        k1 = int(round(FRACAO[0] * len(membros)))
        k2 = int(round((FRACAO[0] + FRACAO[1]) * len(membros)))
        grupo[membros[k1:k2]] = 1
        grupo[membros[k2:]] = 2
    for k, nome in enumerate(("treino", "validacao", "teste")):
        linha("farmacos em %s" % nome, int((grupo == k).sum()),
              "grau medio %.0f" % grau[grupo == k].mean())

    ga, gb = grupo[iu], grupo[ju]
    # Regime do par: 0 treino(TT) 1 val 2 teste, e o subtipo de frieza
    regime = np.full(len(y), -1, dtype=np.int8)
    regime[(ga == 0) & (gb == 0)] = 0                       # treino
    regime[((ga == 1) & (gb <= 1)) | ((gb == 1) & (ga <= 1))] = 1   # validacao
    tem_teste = (ga == 2) | (gb == 2)
    regime[tem_teste] = 2
    frieza = np.zeros(len(y), dtype=np.int8)  # 0 quente-quente 1 q-frio 2 frio-frio
    frieza[tem_teste] = 1
    frieza[(ga == 2) & (gb == 2)] = 2
    print()
    for k, nome in enumerate(("treino (os dois lados de treino)",
                              "validacao (envolve farmaco de validacao)",
                              "teste (envolve farmaco de teste)")):
        m = regime == k
        linha(nome, int(m.sum()),
              "positivos %s (%s)" % (mil(y[m].sum()), pct(int(y[m].sum()), int(m.sum()))))
    print()
    for k, nome in ((1, "  teste QUENTE_FRIO (um lado inedito)"),
                    (2, "  teste FRIO_FRIO (dois lados ineditos)")):
        m = (regime == 2) & (frieza == k)
        linha(nome, int(m.sum()),
              "positivos %s (%s)" % (mil(y[m].sum()), pct(int(y[m].sum()), int(m.sum()))))
    print("""
  Com o sorteio estratificado por decil de grau as tres prevalencias ficam
  proximas, o que e o objetivo: assim a diferenca de metrica entre QUENTE e
  FRIO mede o regime, e nao a mudanca de prevalencia. Mesmo assim toda
  metrica dependente de prevalencia (PR-AUC, precisao) e reportada com a
  prevalencia do proprio regime ao lado.""")

    # ------------------------------------------------ split pareado por grau
    secao("4. SUBCONJUNTO PAREADO POR GRAU — mede o artefato de popularidade")
    # bins por decil de grau
    bins = np.quantile(grau, np.linspace(0, 1, N_BINS_GRAU + 1))
    bin_de = np.clip(np.digitize(grau, bins[1:-1]), 0, N_BINS_GRAU - 1)
    ba, bb = bin_de[iu], bin_de[ju]
    chave = np.minimum(ba, bb).astype(np.int32) * N_BINS_GRAU + np.maximum(ba, bb)
    pos_i = np.flatnonzero(y == 1)
    neg_i = np.flatnonzero(y == 0)
    g = rng(3)
    # quantos positivos por celula de (bin,bin)
    need = np.bincount(chave[pos_i], minlength=N_BINS_GRAU ** 2)
    por_celula = {c: neg_i[chave[neg_i] == c] for c in np.flatnonzero(need)}
    # Pareamento 1:1 EXATO por celula (bin_a, bin_b). Onde nao ha negativo
    # suficiente na celula, o positivo correspondente e DESCARTADO — manter o
    # positivo sem par desfaria o pareamento e devolveria o artefato de grau
    # pela porta de tras (medido: prevalencia ia a 58,4%).
    esc_neg, esc_pos, descartados = [], [], 0
    for c in np.flatnonzero(need):
        disp = por_celula[c]
        p_cel = pos_i[chave[pos_i] == c]
        k = int(min(len(p_cel), len(disp)))
        descartados += len(p_cel) - k
        if k:
            esc_neg.append(g.choice(disp, size=k, replace=False))
            esc_pos.append(g.choice(p_cel, size=k, replace=False))
    neg_pareado = np.concatenate(esc_neg) if esc_neg else np.array([], np.int64)
    pos_pareado = np.concatenate(esc_pos) if esc_pos else np.array([], np.int64)
    pareado = np.concatenate([pos_pareado, neg_pareado])
    linha("positivos mantidos (com par de grau equivalente)", len(pos_pareado))
    linha("negativos pareados por grau", len(neg_pareado))
    linha("positivos descartados por falta de par", descartados,
          "(celula de grau saturada de positivo)")
    linha("prevalencia no subconjunto", pct(len(pos_pareado), len(pareado)))
    ga_p = grau[iu][pareado]
    gb_p = grau[ju][pareado]
    yp = y[pareado]
    linha("grau medio dos positivos do subconjunto",
          "%.0f" % ((ga_p[yp == 1].mean() + gb_p[yp == 1].mean()) / 2))
    linha("grau medio dos negativos do subconjunto",
          "%.0f" % ((ga_p[yp == 0].mean() + gb_p[yp == 0].mean()) / 2))
    print("""
  Como se le este subconjunto: nele, saber o grau dos dois farmacos nao ajuda
  mais a acertar, porque positivo e negativo tem grau parecido por construcao.
  Se a AUC cair muito aqui, o desempenho no universo era popularidade.""")

    # --------------------------------------------- controle negativo puro
    secao("5. CONTROLE NEGATIVO — pares ao acaso (§20)")
    g = rng(4)
    todos_subst = [s for (s,) in con.execute("SELECT id FROM substancia")]
    ctrl = set()
    while len(ctrl) < 5000:
        a, b = g.choice(todos_subst, size=2, replace=False)
        a, b = (int(a), int(b)) if a < b else (int(b), int(a))
        if (a, b) not in pos:
            ctrl.add((a, b))
    ctrl = sorted(ctrl)
    n_grau0 = sum(1 for a, b in ctrl if a not in idx or b not in idx)
    linha("pares de controle sorteados", len(ctrl))
    linha("  destes, com pelo menos um lado de grau zero", n_grau0,
          "(%s)" % pct(n_grau0, len(ctrl)))
    print("""
  Controle sorteado entre TODAS as 2.094 substancias, inclusive as de grau
  zero, e sem nenhum par positivo. Nenhum modelo e treinado nele: serve para
  medir se a probabilidade sai alta indiscriminadamente.""")

    # --------------------------------------------------------- alvo secundario
    secao("6. ALVO SECUNDARIO C2 — tipo PK x PD (so entre os positivos)")
    tipo = np.full(len(y), -1, dtype=np.int8)   # -1 sem rotulo, 0 PD, 1 PK
    for k in np.flatnonzero(y == 1):
        t = pos[(int(a_ids[k]), int(b_ids[k]))][2] or ""
        tem_pk = "FARMACOCINETICA" in t
        tem_pd = "FARMACODINAMICA" in t
        if tem_pk and not tem_pd:
            tipo[k] = 1
        elif tem_pd and not tem_pk:
            tipo[k] = 0
    linha("pares com rotulo de tipo", int((tipo >= 0).sum()))
    linha("  FARMACOCINETICA", int((tipo == 1).sum()))
    linha("  FARMACODINAMICA", int((tipo == 0).sum()))
    linha("positivos sem tipo (DDInter sem descricao)", int(((y == 1) & (tipo < 0)).sum()))

    # ----------------------------------------------------------- gravacao
    TREINO.mkdir(parents=True, exist_ok=True)
    destino = TREINO / "dataset_m1.npz"
    np.savez_compressed(
        destino,
        substancias=np.array(subst, dtype=np.int32),
        a_id=a_ids, b_id=b_ids, y=y, n_fontes=n_fontes, tipo=tipo,
        split_par=split_par, grupo_farmaco=grupo, regime_farmaco=regime,
        frieza=frieza, grau_completo=grau, bin_grau=bin_de,
        indices_pareado_grau=pareado.astype(np.int64),
        controle_a=np.array([a for a, _ in ctrl], dtype=np.int32),
        controle_b=np.array([b for _, b in ctrl], dtype=np.int32),
        semente=np.array([SEMENTE]),
    )
    secao("7. GRAVADO")
    linha("arquivo", str(destino.relative_to(destino.parent.parent.parent)))
    linha("tamanho", "%.1f MB" % (destino.stat().st_size / 1e6))

    r["universo"] = dict(substancias=n, pares=len(y), positivos=int(y.sum()),
                         prevalencia=float(y.mean()))
    r["split_por_par"] = {nome: dict(
        n=int((split_par == k).sum()), positivos=int(y[split_par == k].sum()))
        for k, nome in enumerate(("treino", "validacao", "teste"))}
    r["split_por_farmaco"] = dict(
        farmacos={nome: int((grupo == k).sum()) for k, nome in
                  enumerate(("treino", "validacao", "teste"))},
        pares={nome: dict(n=int((regime == k).sum()),
                          positivos=int(y[regime == k].sum()))
               for k, nome in enumerate(("treino", "validacao", "teste"))},
        teste_quente_frio=dict(
            n=int(((regime == 2) & (frieza == 1)).sum()),
            positivos=int(y[(regime == 2) & (frieza == 1)].sum())),
        teste_frio_frio=dict(
            n=int(((regime == 2) & (frieza == 2)).sum()),
            positivos=int(y[(regime == 2) & (frieza == 2)].sum())))
    r["pareado_grau"] = dict(positivos=len(pos_pareado),
                             negativos=len(neg_pareado),
                             positivos_descartados=descartados,
                             bins=N_BINS_GRAU)
    r["controle_negativo"] = dict(n=len(ctrl), com_grau_zero=n_grau0)
    r["alvo_secundario_tipo"] = dict(
        com_rotulo=int((tipo >= 0).sum()), pk=int((tipo == 1).sum()),
        pd=int((tipo == 0).sum()))
    r["arquivo"] = str(destino)
    gravar("10_dataset.json", r)
    print("\nGravado: ml/saida/10_dataset.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
