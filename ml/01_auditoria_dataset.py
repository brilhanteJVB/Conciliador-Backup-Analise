# -*- coding: utf-8 -*-
"""
AUDITORIA DO DATASET — roda ANTES de definir alvo e ANTES de qualquer treino.

A pergunta que este script responde nao e "quantas linhas eu tenho", e sim
"quantas OBSERVACOES INDEPENDENTES eu tenho". Sao numeros diferentes e a
diferenca decide o tamanho real do experimento.

O QUE E MEDIDO
--------------
 1. Multiplicidade: linhas por par, pares por fonte, sobreposicao entre fontes.
 2. Simetria: o esquema forca `a_id < b_id`; isto CONFIRMA que nao existe
    par invertido duplicado, em vez de supor.
 3. Direcionalidade: quais relacoes sao simetricas e quais nao sao.
 4. Grafo: grau, grau zero, densidade, componentes conexas. E a medicao que
    decide se GNN faz sentido, antes de qualquer treino.
 5. Cobertura de atributo por substancia — o teto do que qualquer modelo pode
    aprender.
 6. Contaminacao potencial: quais colunas do banco sao derivadas da PROPRIA
    fonte do rotulo e por isso nao podem ser atributo.

Saida: ml/saida/01_auditoria_dataset.json
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import conectar, gravar, linha, pct, secao, titulo, versao_dados

# Colunas que descrevem o par e sao DERIVADAS do texto da fonte do rotulo.
# Usa-las como atributo de "existe interacao?" seria circular: o valor so
# existe porque a interacao existe. Ficam listadas aqui para que o construtor
# de atributos possa ser conferido contra a lista.
COLUNAS_CIRCULARES = [
    ("interacao_substancia.tipo",
     "PK/PD sai de regex sobre a descricao da propria interacao"),
    ("interacao_substancia.gravidade",
     "graduacao da propria afirmacao de interacao"),
    ("interacao_substancia.mecanismo",
     "traduzido da descricao da interacao"),
    ("interacao_substancia.efeito_esperado",
     "traduzido da descricao da interacao"),
    ("interacao_substancia.descricao_original",
     "e o texto do rotulo"),
    ("achado.prioridade",
     "calculada pelas nossas proprias regras a partir do rotulo"),
]

CONECTADAS = ("(SELECT substancia_a_id FROM interacao_substancia "
              "UNION SELECT substancia_b_id FROM interacao_substancia)")


def main() -> int:
    con = conectar()
    q = lambda s: con.execute(s).fetchall()
    um = lambda s: con.execute(s).fetchone()[0]
    r = {"versao_dados": versao_dados(con)}
    mil = lambda n: "{:,}".format(int(n)).replace(",", ".")

    titulo("AUDITORIA DO DATASET DE INTERACAO FARMACO x FARMACO")
    print("Banco: database/conciliador.db   impressao: %s"
          % r["versao_dados"]["impressao"])

    # ---------------------------------------------------------- 1. volume
    secao("1. VOLUME — linha nao e observacao")
    n_linhas = um("SELECT COUNT(*) FROM interacao_substancia")
    n_pares = um("SELECT COUNT(*) FROM (SELECT DISTINCT substancia_a_id,"
                 "substancia_b_id FROM interacao_substancia)")
    n_subst = um("SELECT COUNT(*) FROM substancia")
    n_com_aresta = um("SELECT COUNT(*) FROM " + CONECTADAS)
    linha("linhas em interacao_substancia", n_linhas)
    linha("pares distintos (a<b)", n_pares)
    linha("linhas por par (media)", "%.2f" % (n_linhas / n_pares))
    linha("substancias no banco", n_subst)
    linha("substancias com >=1 interacao", n_com_aresta,
          "(%s)" % pct(n_com_aresta, n_subst))
    print("\n  A inflacao vem de duas fontes afirmando o mesmo par. O dataset")
    print("  tem %s observacoes de par, nao %s." % (mil(n_pares), mil(n_linhas)))
    r["volume"] = dict(linhas=n_linhas, pares=n_pares, substancias=n_subst,
                       substancias_com_aresta=n_com_aresta,
                       linhas_por_par=n_linhas / n_pares)

    # -------------------------------------------------- 2. multiplicidade
    secao("2. MULTIPLICIDADE E DUPLICIDADE")
    dist = q("SELECT c, COUNT(*) FROM (SELECT COUNT(*) c FROM "
             "interacao_substancia GROUP BY substancia_a_id, substancia_b_id) "
             "GROUP BY c ORDER BY c")
    for c, n in dist:
        linha("pares afirmados por %d fonte(s)" % c, n, "(%s)" % pct(n, n_pares))
    por_fonte = q("SELECT f.id, f.nome, f.confiabilidade, COUNT(*) "
                  "FROM interacao_substancia i JOIN fonte f ON f.id=i.fonte_id "
                  "GROUP BY 1,2,3 ORDER BY 4 DESC")
    print()
    for fid, nome, conf, n in por_fonte:
        linha("fonte %d — %s (%s)" % (fid, nome, conf), n)
    dup_exata = um("SELECT COUNT(*) FROM (SELECT substancia_a_id, substancia_b_id,"
                   " fonte_id, COUNT(*) c FROM interacao_substancia "
                   "GROUP BY 1,2,3 HAVING c>1)")
    linha("duplicata exata (mesmo par, mesma fonte)", dup_exata,
          "<- UNIQUE(a,b,fonte_id) impede")
    n_dois = int(dist[-1][1])
    r["multiplicidade"] = dict(
        distribuicao={int(c): int(n) for c, n in dist},
        por_fonte=[dict(id=f, nome=n, confiabilidade=c, linhas=k)
                   for f, n, c, k in por_fonte],
        duplicata_exata=dup_exata, pares_com_duas_fontes=n_dois)

    # ------------------------------------------------------- 3. simetria
    secao("3. SIMETRIA E DIRECIONALIDADE")
    viola = um("SELECT COUNT(*) FROM interacao_substancia "
               "WHERE substancia_a_id >= substancia_b_id")
    linha("linhas violando a<b (par invertido)", viola,
          "<- CHECK do esquema impede")
    print("""
  SIMETRICAS (par canonico, uma linha):
    farmaco x farmaco     — "A interage com B" == "B interage com A".
                            A ordem em que o paciente tomou nao muda o par.
  ASSIMETRICAS (nao viram par canonico, e nao entram neste dataset):
    papel_farmacocinetico — "A inibe CYP3A4" e "B e substrato de CYP3A4" sao
                            papeis diferentes; a direcao do efeito depende de
                            qual e qual. Vira ATRIBUTO do lado, nao rotulo.
    regra_separacao       — tem lado que deve ser adiado.
    interacao_doenca      — farmaco -> doenca, nunca o contrario.
  CONSEQUENCIA: o alvo de existencia e simetrico, logo os atributos de par tem
  de ser simetricos tambem (soma, ou-logico, min/max), nunca "valor de A" e
  "valor de B" em posicoes fixas — isso ensinaria a ordem do id.""")
    r["simetria"] = dict(violacoes=viola, auto_par=0)

    # ---------------------------------------------------------- 4. grafo
    secao("4. GRAFO DE INTERACAO — a medicao que decide sobre GNN")
    arestas = q("SELECT DISTINCT substancia_a_id, substancia_b_id "
                "FROM interacao_substancia")
    grau = collections.Counter()
    adj = collections.defaultdict(set)
    for a, b in arestas:
        grau[a] += 1
        grau[b] += 1
        adj[a].add(b)
        adj[b].add(a)
    todos = [i for (i,) in q("SELECT id FROM substancia")]
    graus = sorted(grau.get(i, 0) for i in todos)
    zero = sum(1 for g in graus if g == 0)
    conectados = [g for g in graus if g > 0]
    n_c = len(conectados)
    possiveis = n_c * (n_c - 1) // 2
    dens = 100.0 * n_pares / possiveis
    linha("substancias com grau ZERO", zero,
          "(%s)  <- ponto cego" % pct(zero, n_subst))
    linha("substancias com grau >= 1", n_c, "(%s)" % pct(n_c, n_subst))
    linha("grau medio (todas as substancias)", "%.1f" % (sum(graus) / len(graus)))
    linha("grau medio (so as conectadas)", "%.1f" % (sum(conectados) / n_c))
    linha("grau mediano (conectadas)", conectados[n_c // 2])
    linha("grau maximo", conectados[-1])
    linha("pares possiveis entre as conectadas", possiveis)
    linha("pares observados", n_pares)
    linha("DENSIDADE do subgrafo conectado", ("%.2f%%" % dens).replace(".", ","))

    visto, comps = set(), []
    for s in list(adj):
        if s in visto:
            continue
        fila, comp = [s], set()
        visto.add(s)
        while fila:
            x = fila.pop()
            comp.add(x)
            for y in adj[x]:
                if y not in visto:
                    visto.add(y)
                    fila.append(y)
        comps.append(len(comp))
    comps.sort(reverse=True)
    linha("componentes conexas (entre as conectadas)", len(comps))
    linha("maior componente", comps[0], "(%s das conectadas)" % pct(comps[0], n_c))
    print("""
  LEITURA: o grafo e dois objetos colados. Entre as %d conectadas ele e DENSO
  (%s de todos os pares possiveis ja e aresta) e tem uma componente unica —
  ha pouca estrutura de vizinhanca a explorar, porque quase todo mundo e
  vizinho de quase todo mundo. E ha %d substancias com grau zero, onde um
  modelo que propaga por aresta nao tem o que propagar. Essas %d sao
  exatamente as que motivam o projeto: o farmaceutico consulta o sistema
  justamente sobre o que nao esta na base.""" % (
        n_c, ("%.1f%%" % dens).replace(".", ","), zero, zero))
    r["grafo"] = dict(grau_zero=zero, conectadas=n_c,
                      grau_medio_todas=sum(graus) / len(graus),
                      grau_medio_conectadas=sum(conectados) / n_c,
                      grau_mediano=conectados[n_c // 2], grau_max=conectados[-1],
                      pares_possiveis=possiveis, pares_observados=n_pares,
                      densidade=n_pares / possiveis,
                      componentes=len(comps), maior_componente=comps[0])

    # ------------------------------------------- 5. cobertura de atributo
    secao("5. COBERTURA DE ATRIBUTO — o teto do que se pode aprender")
    cobre = {}
    for rot, sql in [
        ("codigo ATC", "atc_codigo IS NOT NULL"),
        ("canal de dispensacao (tarja)", "canal_dispensacao IS NOT NULL"),
        ("CAS", "cas IS NOT NULL"),
        ("numero DCB", "dcb_numero IS NOT NULL"),
        ("indice terapeutico estreito=1", "indice_terapeutico_estreito=1"),
        ("na RENAME=1", "na_rename=1"),
    ]:
        n_all = um("SELECT COUNT(*) FROM substancia WHERE " + sql)
        n_con = um("SELECT COUNT(*) FROM substancia WHERE %s AND id IN %s"
                   % (sql, CONECTADAS))
        cobre[rot] = dict(todas=n_all, conectadas=n_con)
        linha(rot, n_all, "(%s de todas | %s das conectadas)"
              % (pct(n_all, n_subst), pct(n_con, n_c)))
    for rot, tab in [("papel farmacocinetico (CYP)", "papel_farmacocinetico"),
                     ("alvo molecular", "substancia_alvo"),
                     ("regra de administracao", "regra_administracao"),
                     ("interacao com doenca", "interacao_doenca"),
                     ("interacao com item", "interacao_item"),
                     ("reacao adversa", "substancia_reacao_adversa")]:
        n_all = um("SELECT COUNT(DISTINCT substancia_id) FROM " + tab)
        n_con = um("SELECT COUNT(DISTINCT substancia_id) FROM %s "
                   "WHERE substancia_id IN %s" % (tab, CONECTADAS))
        cobre[rot] = dict(todas=n_all, conectadas=n_con)
        linha(rot, n_all, "(%s de todas | %s das conectadas)"
              % (pct(n_all, n_subst), pct(n_con, n_c)))
    r["cobertura_atributo"] = cobre
    print("""
  O que sobra como atributo REAL: a hierarquia ATC (%s das conectadas), a
  tarja e o numero de produtos ativos. CYP cobre %d substancias e alvo
  molecular NENHUMA — a camada IUPHAR nao foi carregada neste projeto.
  Estrutura quimica (fingerprint, descritor molecular) nao existe no acervo:
  ha CAS, que e identificador, nao estrutura. Nao ha como calcular
  similaridade estrutural sem carregar fonte nova.""" % (
        pct(cobre["codigo ATC"]["conectadas"], n_c),
        cobre["papel farmacocinetico (CYP)"]["todas"]))

    # ------------------------------------------- 6. ATC como identificador
    secao("6. GRANULARIDADE DO ATC — por que o 5o nivel nao pode ser atributo")
    niveis = collections.Counter(
        len(c) for (c,) in q("SELECT atc_codigo FROM substancia "
                             "WHERE atc_codigo IS NOT NULL"))
    for k in sorted(niveis):
        linha("substancias com codigo de %d caracteres" % k, niveis[k])
    dup5 = um("SELECT COUNT(*) FROM (SELECT atc_codigo, COUNT(*) c FROM "
              "substancia WHERE atc_codigo IS NOT NULL GROUP BY 1 HAVING c>1)")
    linha("codigos ATC de 5o nivel com >1 substancia", dup5)
    n_classes = {}
    for nv, tam in [(1, 1), (2, 3), (3, 4), (4, 5)]:
        n = um("SELECT COUNT(DISTINCT SUBSTR(atc_codigo,1,%d)) FROM substancia "
               "WHERE atc_codigo IS NOT NULL" % tam)
        n_classes[nv] = n
        linha("classes distintas no nivel %d (%d chars)" % (nv, tam), n)
    print("""
  Todo codigo gravado e de 5o nivel e nenhum e compartilhado por duas
  substancias: o 5o nivel E a substancia. Usa-lo como atributo categorico
  seria entregar o id ao modelo. Os niveis 1 a 4 sao classe de verdade e
  entram; o 5o fica fora. (Mesmo motivo de D-028 para duplicidade.)
  LIMITACAO: a coluna guarda UM codigo por substancia; farmaco com mais de uma
  indicacao ATC perde os outros. E limite do esquema atual, nao do modelo.""")
    r["atc"] = dict(niveis_tamanho={int(k): int(v) for k, v in niveis.items()},
                    codigos5_compartilhados=dup5, classes_por_nivel=n_classes)

    # ------------------------------------------------ 7. eixo temporal
    secao("7. EIXO TEMPORAL — split por data e possivel?")
    datas = [d for (d,) in q("SELECT DISTINCT SUBSTR(data_importacao,1,10) "
                             "FROM carga ORDER BY 1")]
    linha("datas distintas de importacao", len(datas), str(datas))
    cols_data = um("SELECT COUNT(*) FROM pragma_table_info"
                   "('interacao_substancia') WHERE name LIKE '%data%'")
    linha("colunas de data na tabela de interacao", cols_data)
    print("""
  NAO. Todas as cargas sao do mesmo dia e nenhuma das duas fontes publica a
  data em que a interacao foi documentada. Split temporal fica declarado como
  IMPOSSIVEL com os dados atuais — nao substituido por proxy.""")
    r["temporal"] = dict(datas=datas, viavel=False,
                         motivo="fonte nao publica data de documentacao")

    # --------------------------------------------- 8. colunas circulares
    secao("8. COLUNAS QUE NAO PODEM SER ATRIBUTO (circularidade)")
    for col, motivo in COLUNAS_CIRCULARES:
        print("  %-42s %s" % (col, motivo))
    print("""
  Registro: no sistema ANTERIOR o vetor farmacodinamico era extraido de
  db_drug_interactions.csv — o mesmo arquivo que dava o rotulo. A ablacao
  "SEM PD" custava 0,0428 de AUC. Neste projeto essa coluna nao existe: os
  atributos vem de WHO ATC, CMED e FDA, fontes que nao afirmam interacao
  nenhuma. A circularidade foi resolvida por construcao. A ablacao sera feita
  igual, sobre os atributos de GRAFO, que tem o mesmo problema por outro
  caminho: grau e contagem de rotulos positivos disfarcada de atributo.""")
    r["colunas_circulares"] = [dict(coluna=c, motivo=m)
                               for c, m in COLUNAS_CIRCULARES]

    # ------------------------------------------ 9. unidade do treinamento
    secao("9. UNIDADE DO DATASET — decisao")
    print("""  Unidade escolhida: O PAR CANONICO DE SUBSTANCIAS (a<b), uma linha por par.

  Por que nao a linha de interacao: %s linhas viram %s pares porque duas
  fontes afirmam o mesmo par. Treinar nas linhas daria peso 2 a %s pares
  (%s deles) e peso 1 ao resto — o modelo aprenderia "este par aparece em
  duas bases", que e propriedade da compilacao, nao farmacologia.

  Por que nao o achado: achado depende de paciente. Existencia de interacao e
  propriedade do par; misturar contexto de paciente num alvo que pretende ser
  geral e exatamente o que a especificacao §12 proibe.

  O numero de fontes que afirmam o par NAO e descartado: vira o rotulo
  auxiliar `n_fontes`, usado para medir concordancia entre bases e para o
  teste de robustez do rotulo — nunca como atributo de entrada.""" % (
        mil(n_linhas), mil(n_pares), mil(n_dois), pct(n_dois, n_pares)))
    r["unidade"] = "par_canonico_de_substancias"

    caminho = gravar("01_auditoria_dataset.json", r)
    print("\nGravado: ml/saida/%s" % caminho.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
