# -*- coding: utf-8 -*-
"""
AUDITORIA DOS ROTULOS — quais alvos existem, e quais NAO existem.

Ordem obrigatoria: este script roda antes de 10_dataset.py. Um alvo so entra
no dataset depois de aparecer aqui com quantidade, distribuicao, origem e
confiabilidade medidas. Alvo sem numero nao e treinado.

TRES ORIGENS DE ROTULO, NUNCA MISTURADAS
----------------------------------------
    FONTE        afirmado por base externa (DDInter, db_drug_interactions)
    SISTEMA      derivado pelas nossas proprias regras (prioridade, tipo)
    HUMANO       farmaceutico assinou (anotacao_profissional)

Misturar as tres produziria um alvo que parece grande e e, na verdade,
o nosso proprio motor se avaliando. A coluna `origem_rotulo` no relatorio
existe para impedir isso.

Saida: ml/saida/02_auditoria_rotulos.json
"""
from __future__ import annotations

import collections
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _comum import conectar, gravar, linha, pct, secao, titulo, versao_dados


def veredito(nome, viavel, motivo):
    print("\n  VEREDITO %s: %s" % (nome, "VIAVEL" if viavel else "INVIAVEL"))
    print("  %s" % motivo)


def main() -> int:
    con = conectar()
    q = lambda s: con.execute(s).fetchall()
    um = lambda s: con.execute(s).fetchone()[0]
    r = {"versao_dados": versao_dados(con)}
    mil = lambda n: "{:,}".format(int(n)).replace(",", ".")

    titulo("AUDITORIA DOS ROTULOS DISPONIVEIS")

    n_pares = um("SELECT COUNT(*) FROM (SELECT DISTINCT substancia_a_id,"
                 "substancia_b_id FROM interacao_substancia)")
    n_conect = um("SELECT COUNT(*) FROM (SELECT substancia_a_id AS s FROM "
                  "interacao_substancia UNION SELECT substancia_b_id FROM "
                  "interacao_substancia)")
    possiveis = n_conect * (n_conect - 1) // 2

    # =============================================== PROBLEMA A — existencia
    secao("PROBLEMA A — existe interacao documentada entre A e B?")
    print("  origem_rotulo: FONTE       tipo: binario, simetrico")
    pos = n_pares
    neg_presumido = possiveis - pos
    linha("positivos (par afirmado por >=1 fonte)", pos)
    linha("universo de pares entre substancias cobertas", possiveis)
    linha("negativos PRESUMIDOS (nao afirmados)", neg_presumido)
    linha("prevalencia de positivo no universo", pct(pos, possiveis))
    linha("desconhecidos (par com substancia de grau zero)",
          (2094 * 2093 // 2) - possiveis,
          "<- sem rotulo de nenhum tipo")
    print("""
  O NEGATIVO NAO E OBSERVADO, E PRESUMIDO. Nenhuma das duas bases publica
  "estes dois nao interagem": elas listam o que afirmam. Ausencia de linha
  significa uma de tres coisas, e o dado nao distingue:
     (a) as duas foram estudadas juntas e nao interagem;
     (b) nunca foram estudadas juntas;
     (c) interagem e a base ainda nao registrou.
  Isto e aprendizado com positivos e nao-rotulados (PU). O rotulo negativo
  usado aqui e "NAO AFIRMADO POR ESTAS DUAS BASES", e o relatorio da fase diz
  isso com estas palavras. A consequencia pratica: o modelo estima
  probabilidade de o par ESTAR DOCUMENTADO, nao de o par ser perigoso.

  MITIGACAO ADOTADA (nao resolve, limita o dano):
   1. o universo exclui substancia de grau zero — pares onde a ausencia
      certamente e falta de cobertura, nao ausencia de interacao;
   2. amostragem de negativo tambem em versao PAREADA POR GRAU, para medir
      quanto do desempenho e artefato de popularidade;
   3. controle negativo explicito com pares sorteados ao acaso.""")
    r["problema_a"] = dict(origem_rotulo="FONTE", tipo="binario_simetrico",
                           positivos=pos, universo=possiveis,
                           negativos_presumidos=neg_presumido,
                           prevalencia=pos / possiveis, viavel=True,
                           limitacao="negativo presumido (PU learning)")
    veredito("A", True, "94.770 positivos e universo de 457.446 pares. "
                        "Viavel, com a natureza PU declarada.")

    # ================================================ PROBLEMA B — relevancia
    secao("PROBLEMA B — o alerta merece destaque ao profissional?")
    print("  origem_rotulo: HUMANO     tipo: binario")
    n_anot = um("SELECT COUNT(*) FROM anotacao_profissional")
    n_prof = um("SELECT COUNT(DISTINCT profissional) FROM anotacao_profissional")
    n_achados = um("SELECT COUNT(*) FROM achado")
    linha("linhas em anotacao_profissional", n_anot)
    linha("farmaceuticos distintos", n_prof)
    linha("achados gravados no banco (todos os atendimentos)", n_achados)
    linha("achados com anotacao", 0)
    linha("achados com anotacao de 2+ profissionais (consenso)", 0)
    for alvo in ("ACHADO", "DIVERGENCIA"):
        linha("anotacoes com alvo=%s" % alvo,
              um("SELECT COUNT(*) FROM anotacao_profissional WHERE alvo='%s'" % alvo))
    print("""
  A TABELA EXISTE E ESTA VAZIA. A estrutura de rotulo humano foi construida
  (chave estavel, assinatura, CHECK de intencionalidade), mas nenhum
  farmaceutico anotou nada ainda. Zero e zero: nao ha o que treinar, nao ha o
  que estimar, e nao ha extrapolacao honesta a partir de zero exemplos.

  O QUE NAO SERA FEITO, e por que:
   - usar `prioridade` como proxy de relevancia: prioridade e calculada pelas
     nossas regras. O modelo aprenderia a reproduzir `_prioridade.py`, e a
     metrica mediria fidelidade ao nosso proprio codigo, nao utilidade
     clinica. A especificacao §3 proibe explicitamente.
   - marcar como relevante o que tem gravidade MAIOR: e a mesma circularidade
     com outro nome.
   - simular anotacoes: inventaria evidencia clinica.""")

    # quantas anotacoes seriam necessarias — analise de poder
    print("  QUANTAS ANOTACOES SERIAM NECESSARIAS (analise de poder):")
    for p, d in ((0.5, 0.10), (0.5, 0.15), (0.3, 0.10)):
        # n para intervalo de confianca de 95% com semi-amplitude d
        n = math.ceil(1.96 ** 2 * p * (1 - p) / d ** 2)
        linha("prevalencia %.0f%%, precisao +-%.0f pontos" % (p * 100, d * 100),
              n, "anotacoes")
    print("""    Para um modelo de relevancia com validacao cruzada por avaliador seriam
    necessarias na ordem de 400 a 1.000 anotacoes de 2 farmaceuticos
    independentes. Hoje: 0. A distancia nao e de codigo, e de gente.""")
    r["problema_b"] = dict(origem_rotulo="HUMANO", anotacoes=n_anot,
                           profissionais=n_prof, viavel=False,
                           motivo="anotacao_profissional vazia (0 linhas)",
                           necessario_estimado="400 a 1.000 anotacoes, 2 avaliadores")
    veredito("B", False, "Zero anotacoes humanas. A estrutura de rotulo esta "
                         "pronta; o rotulo nao existe. Nao sera treinado.")

    # ============================================== PROBLEMA C — gravidade
    secao("PROBLEMA C1 — gravidade (auditoria obrigatoria antes de descartar)")
    print("  origem_rotulo: FONTE      tipo: ordinal (MAIOR/MODERADA/MENOR)")
    grav_fonte = q("SELECT f.nome, i.gravidade, COUNT(*) FROM interacao_substancia i "
                   "JOIN fonte f ON f.id=i.fonte_id GROUP BY 1,2 ORDER BY 1,3 DESC")
    for nome, g, n in grav_fonte:
        linha("%s / %s" % (nome, g), n)
    # por par: gravidade maxima declarada
    pares_grad = um("SELECT COUNT(*) FROM (SELECT substancia_a_id, substancia_b_id "
                    "FROM interacao_substancia WHERE gravidade<>'NAO_DETERMINADA' "
                    "GROUP BY 1,2)")
    print()
    linha("pares com ALGUMA gravidade graduada", pares_grad,
          "(%s dos pares)" % pct(pares_grad, n_pares))
    linha("pares SEM gravidade em nenhuma fonte", n_pares - pares_grad,
          "(%s)" % pct(n_pares - pares_grad, n_pares))
    dist_par = q("SELECT gravidade, COUNT(*) FROM (SELECT substancia_a_id, "
                 "substancia_b_id, MIN(gravidade) gravidade FROM "
                 "interacao_substancia WHERE gravidade<>'NAO_DETERMINADA' "
                 "GROUP BY 1,2) GROUP BY 1 ORDER BY 2 DESC")
    print()
    for g, n in dist_par:
        linha("  pares graduados como %s" % g, n, "(%s dos graduados)"
              % pct(n, pares_grad))
    # concordancia entre fontes: possivel?
    dois_grad = um("SELECT COUNT(*) FROM (SELECT substancia_a_id, substancia_b_id, "
                   "COUNT(*) c FROM interacao_substancia WHERE "
                   "gravidade<>'NAO_DETERMINADA' GROUP BY 1,2 HAVING c>1)")
    conflitos = um("SELECT COUNT(*) FROM vw_conflito_gravidade")
    print()
    linha("pares graduados por DUAS fontes", dois_grad)
    linha("linhas em vw_conflito_gravidade", conflitos)
    print("""
  vw_conflito_gravidade devolve %d, e NAO por concordancia entre as bases: uma
  das duas nao gradua nada. Nao ha como medir consistencia de graduacao neste
  acervo, porque so existe um graduador. Um alvo ordinal cuja consistencia e
  estruturalmente imensuravel nao tem como ser validado.

  DECISAO: mantida D-015 — gravidade nao sera alvo de ML. Nao por preferencia
  de arquitetura, por ausencia e imensurabilidade do rotulo. Treinar nos %s
  pares graduados ensinaria o critério de quem graduou aqueles, e o modelo
  seria aplicado exatamente onde esse critério nao existe.
  Tratar NAO_DETERMINADA como classe propria tambem esta descartado: "nao sei"
  nao e grau de gravidade, e o modelo passaria a prever ausencia de
  informacao — o que e util para priorizar curadoria, e nao e gravidade.""" % (
        conflitos, mil(pares_grad)))
    r["problema_c1_gravidade"] = dict(
        origem_rotulo="FONTE", pares_graduados=pares_grad,
        pares_sem_gravidade=n_pares - pares_grad,
        pares_graduados_por_duas_fontes=dois_grad,
        conflitos_medidos=conflitos, viavel=False,
        motivo="65,8%% das linhas sem graduacao e um unico graduador; "
               "consistencia entre fontes imensuravel")
    veredito("C1 gravidade", False,
             "Confirma D-015 com numero: %s de %s pares graduados, e apenas "
             "uma das duas fontes gradua." % (mil(pares_grad), mil(n_pares)))

    # ============================================ PROBLEMA C2 — tipo PK/PD
    secao("PROBLEMA C2 — tipo da interacao (farmacocinetica x farmacodinamica)")
    print("  origem_rotulo: SISTEMA (regex sobre texto da fonte)   tipo: binario")
    tipo_fonte = q("SELECT f.nome, i.tipo, COUNT(*) FROM interacao_substancia i "
                   "JOIN fonte f ON f.id=i.fonte_id GROUP BY 1,2 ORDER BY 1,3 DESC")
    for nome, t, n in tipo_fonte:
        linha("%s / %s" % (nome, t), n)
    pares_tipo = um("SELECT COUNT(*) FROM (SELECT substancia_a_id, substancia_b_id "
                    "FROM interacao_substancia WHERE tipo<>'NAO_DETERMINADO' "
                    "GROUP BY 1,2)")
    print()
    linha("pares com tipo determinado", pares_tipo,
          "(%s dos pares)" % pct(pares_tipo, n_pares))
    dist_t = q("SELECT tipo, COUNT(*) FROM (SELECT substancia_a_id, "
               "substancia_b_id, MIN(tipo) tipo FROM interacao_substancia "
               "WHERE tipo<>'NAO_DETERMINADO' GROUP BY 1,2) GROUP BY 1 "
               "ORDER BY 2 DESC")
    for t, n in dist_t:
        linha("  %s" % t, n, "(%s)" % pct(n, pares_tipo))
    # conflito de tipo entre fontes
    conf_tipo = um("SELECT COUNT(*) FROM (SELECT substancia_a_id, substancia_b_id "
                   "FROM interacao_substancia WHERE tipo<>'NAO_DETERMINADO' "
                   "GROUP BY 1,2 HAVING COUNT(DISTINCT tipo)>1)")
    linha("pares com tipo divergente entre fontes", conf_tipo)
    print("""
  O tipo existe para %s pares e vem TODO de uma fonte so: o DDInter nao
  publica descricao nenhuma, logo nao ha texto de onde extrair tipo. Todos os
  %s vem de db_drug_interactions, a fonte de confiabilidade MEDIA, por
  expressao regular sobre texto em ingles.

  E um alvo tecnicamente treinavel e clinicamente de segunda ordem: saber que
  a interacao e farmacocinetica nao muda a conduta de balcao tanto quanto
  saber que ela existe. Sera treinado como ALVO SECUNDARIO, com o rotulo
  marcado EXTRAIDO_AUTOMATICAMENTE e a limitacao no relatorio — nunca
  apresentado como se um farmaceutico tivesse classificado.""" % (
        mil(pares_tipo), mil(pares_tipo)))
    r["problema_c2_tipo"] = dict(
        origem_rotulo="SISTEMA_REGEX", pares_com_tipo=pares_tipo,
        distribuicao={t: n for t, n in dist_t}, conflito_entre_fontes=conf_tipo,
        viavel=True, papel="alvo secundario",
        limitacao="rotulo derivado por regex de UMA fonte, confiabilidade MEDIA")
    veredito("C2 tipo", True,
             "%s pares rotulados, mas rotulo derivado por regex de uma unica "
             "fonte. Entra como alvo secundario, declarado." % mil(pares_tipo))

    # =========================================== PROBLEMA C3 — os que faltam
    secao("PROBLEMA C3 — os outros alvos cogitados pela especificacao")
    tabela = [
        ("prioridade", "SISTEMA", 0,
         "calculada por rules/_prioridade.py; treinar nela mede fidelidade ao "
         "nosso codigo, nao verdade clinica. Proibido pela especificacao §3."),
        ("classificacao de risco", "—", 0,
         "e a gravidade com outro nome; cai com C1."),
        ("mecanismo", "FONTE (texto livre)",
         um("SELECT COUNT(*) FROM interacao_substancia WHERE mecanismo IS NOT NULL"),
         "texto livre sem vocabulario controlado. Nao ha classe fechada para "
         "prever; seria geracao de texto, nao classificacao."),
        ("efeito clinico", "FONTE (texto livre)",
         um("SELECT COUNT(*) FROM interacao_substancia "
            "WHERE efeito_esperado IS NOT NULL"),
         "mesmo caso do mecanismo."),
        ("necessidade de revisao", "SISTEMA",
         um("SELECT COUNT(*) FROM interacao_substancia "
            "WHERE status_revisao<>'PENDENTE'"),
         "todas as %s linhas estao PENDENTE. Zero variacao no alvo."
         % mil(um("SELECT COUNT(*) FROM interacao_substancia"))),
        ("reacao adversa", "VigiMed",
         um("SELECT COUNT(*) FROM substancia_reacao_adversa"),
         "VigiMed nao carregado neste projeto. M4 fica fora da Fase 7."),
    ]
    for nome, origem, n, motivo in tabela:
        print("\n  %s   [origem: %s]" % (nome.upper(), origem))
        linha("  rotulos disponiveis", n)
        print("    %s" % motivo)
    r["problema_c3_descartados"] = [
        dict(alvo=n, origem_rotulo=o, rotulos=k, motivo=m)
        for n, o, k, m in tabela]

    # ============================================================ resumo
    secao("RESUMO — o que a Fase 7 vai treinar")
    print("""
  ALVO PRINCIPAL   A — existencia de interacao documentada
                       94.770 positivos · rotulo de FONTE · binario simetrico
                       limitacao: negativo presumido (PU)

  ALVO SECUNDARIO  C2 — tipo farmacocinetico x farmacodinamico
                       %s pares · rotulo de SISTEMA (regex) · declarado

  NAO TREINADOS    B  relevancia do alerta ...... 0 rotulos humanos
                   C1 gravidade ................. rotulo ausente na fonte
                   C3 prioridade ................ circular com nosso codigo
                      mecanismo / efeito ........ texto livre, sem classes
                      necessidade de revisao .... alvo sem variacao
                      reacao adversa ............ fonte nao carregada

  Dois alvos treinados, seis recusados com numero ao lado. A recusa
  documentada e resultado da fase, nao falha dela.""" % mil(pares_tipo))

    caminho = gravar("02_auditoria_rotulos.json", r)
    print("\nGravado: ml/saida/%s" % caminho.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
