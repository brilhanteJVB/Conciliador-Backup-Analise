# -*- coding: utf-8 -*-
"""
QUALIDADE DOS DADOS DA FASE 5 — o quadro exigido pela especificacao (secao 20).

Monta uma coorte de pacientes sinteticos sobre farmacologia REAL do banco,
roda o motor de conciliacao em todos e publica os numeros: quantos achados,
de que tipo, com que prioridade, quantos com evidencia, quantos extraidos
automaticamente, quantos deduplicados, quantos com conflito de fonte.

REGRA: o paciente e sintetico, a farmacologia nunca. Cada arquétipo abaixo
descreve uma situacao de balcao; os medicamentos sao escolhidos no banco por
consulta, e nao escritos a mao.

Nada aqui e gravado: a coorte inteira vive dentro de uma transacao desfeita.

Uso: python tests/qualidade_fase5.py
"""
from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tests"))
sys.path.insert(0, str(RAIZ / "rules"))

from casos_conciliacao import (achar_alergia_cruzada, achar_contraindicacao,  # noqa: E402
                               achar_interacao_habito, achar_interacao_item,
                               achar_par_cyp, achar_par_interacao,
                               achar_regra_jejum, achar_substancia_sem_interacao,
                               adicionar, adicionar_alergia,
                               adicionar_condicao, adicionar_habito,
                               adicionar_item, banco_temporario,
                               criar_atendimento)
from motor_conciliacao import conciliar_atendimento  # noqa: E402


# =====================================================================
# ARQUETIPOS — situacoes de balcao, nao listas de farmacos
# =====================================================================
def coorte(con, rnd):
    """Devolve [(codigo, descricao, atendimento_id)]."""
    casos = []
    par_maior = achar_par_interacao(con, "MAIOR")
    par_mod = achar_par_interacao(con, "MODERADA")
    ci = achar_contraindicacao(con)
    ci_cautela = achar_contraindicacao(con, "USAR_COM_CAUTELA")
    item = achar_interacao_item(con)
    alcool = achar_interacao_habito(con, "ALCOOL")
    cyp = achar_par_cyp(con, "FORTE")
    jejum = achar_regra_jejum(con)
    cruzada = achar_alergia_cruzada(con)

    def novo(codigo, desc):
        aid = criar_atendimento(con, codigo)
        casos.append((codigo, desc, aid))
        return aid

    # 1 — polimedicado com prescricao e relato divergentes
    aid = novo("P01", "Polimedicado: prescrição × relato, dose divergente")
    adicionar(con, aid, par_maior[0], par_maior[1], lista="PRESCRITA",
              dose=10.0, unidade="mg", horarios=("08:00",))
    adicionar(con, aid, par_maior[0], par_maior[1], lista="RELATADA",
              dose=20.0, unidade="mg", horarios=("08:00",))
    adicionar(con, aid, par_maior[2], par_maior[3], lista="PRESCRITA",
              horarios=("20:00",))
    adicionar(con, aid, par_mod[0], par_mod[1], lista="RELATADA",
              horarios=("12:00",), origem="AUTOMEDICACAO")

    # 2 — condicao clinica declarada com contraindicacao na bula
    aid = novo("P02", "Condição clínica com contraindicação em bula")
    adicionar(con, aid, ci[0], ci[1], lista="RELATADA", horarios=("08:00",))
    adicionar_condicao(con, aid, doenca_id=ci[2])

    # 3 — precaucao, nao proibicao
    aid = novo("P03", "Condição com precaução (não proibição)")
    if ci_cautela:
        adicionar(con, aid, ci_cautela[0], ci_cautela[1], lista="RELATADA",
                  horarios=("08:00",))
        adicionar_condicao(con, aid, doenca_id=ci_cautela[2])

    # 4 — alergia declarada exatamente ao que usa
    aid = novo("P04", "Alergia declarada à substância em uso")
    adicionar(con, aid, par_maior[0], par_maior[1], lista="RELATADA",
              horarios=("08:00",))
    adicionar_alergia(con, aid, substancia_id=par_maior[0],
                      reacao="edema de glote", gravidade="ANAFILAXIA")

    # 5 — alergia a outro farmaco da mesma classe
    aid = novo("P05", "Alergia a outro fármaco da mesma classe ATC")
    if cruzada:
        adicionar(con, aid, cruzada[0], cruzada[1], lista="RELATADA",
                  horarios=("08:00",))
        adicionar_alergia(con, aid, substancia_id=cruzada[2], reacao="exantema")

    # 6 — chá/planta que o paciente declarou usar
    aid = novo("P06", "Planta/alimento declarado pelo paciente")
    adicionar(con, aid, item[0], item[1], lista="RELATADA", horarios=("08:00",))
    adicionar_item(con, aid, item[2], item[3], horario="08:00")

    # 7 — álcool declarado
    aid = novo("P07", "Hábito de álcool declarado")
    adicionar(con, aid, alcool[0], alcool[1], lista="RELATADA",
              horarios=("22:00",))
    adicionar_habito(con, aid, "ALCOOL", "ATUAL", frequencia="diário")

    # 8 — inferencia mecanistica por enzima
    aid = novo("P08", "Inibidor forte de CYP com substrato sensível")
    adicionar(con, aid, cyp[0], cyp[1], lista="RELATADA", horarios=("08:00",))
    adicionar(con, aid, cyp[2], cyp[3], lista="RELATADA", horarios=("20:00",))

    # 9 — jejum em conflito com o café da manhã
    aid = novo("P09", "Jejum tomado junto do café da manhã")
    adicionar(con, aid, jejum[0], jejum[1], lista="RELATADA",
              horarios=("07:05",))

    # 10 — duplicidade por marca e generico
    aid = novo("P10", "Marca e genérico do mesmo princípio ativo")
    adicionar(con, aid, par_maior[0], par_maior[1] + " (marca)",
              lista="RELATADA", horarios=("08:00",))
    adicionar(con, aid, par_maior[0], par_maior[1] + " genérico",
              lista="RELATADA", horarios=("20:00",))

    # 11 — sem posologia, situacao comum no balcao
    aid = novo("P11", "Paciente não sabe a dose nem os horários")
    adicionar(con, aid, par_maior[0], par_maior[1], lista="RELATADA",
              dose=None, vezes=None, horarios=())
    adicionar(con, aid, par_maior[2], par_maior[3], lista="RELATADA",
              com_posologia=False)

    # 12 — item nao reconhecido
    aid = novo("P12", "Medicamento que o sistema não reconhece")
    adicionar(con, aid, None, "aquele comprimido amarelo", lista="RELATADA",
              horarios=("08:00",))
    adicionar(con, aid, par_maior[0], par_maior[1], lista="RELATADA",
              horarios=("08:00",))

    # 13 — medicamento suspenso que segue em uso
    aid = novo("P13", "Suspenso que continua em uso")
    adicionar(con, aid, par_maior[0], par_maior[1], lista="PRESCRITA",
              horarios=("08:00",))
    adicionar(con, aid, par_maior[0], par_maior[1], lista="RELATADA",
              horarios=("08:00",))
    adicionar(con, aid, par_maior[0], par_maior[1], lista="ANTERIOR",
              horarios=("08:00",))

    # 14 — PRN
    aid = novo("P14", "Analgésico se necessário, sem horário fixo")
    adicionar(con, aid, par_maior[0], par_maior[1], lista="RELATADA",
              prn=1, continuo=0, vezes=None, condicao="se dor")

    # 15 — controle negativo
    aid = novo("P15", "Controle negativo: um item, nenhum contexto")
    # Cuidado ao escrever isto em SQL: a tabela interacao_substancia
    # tambem tem coluna id, e o SQLite resolve o nome na tabela mais
    # interna. A condicao viraria i.substancia_a_id = i.id e a consulta
    # devolveria nada. Por isso usa-se o ajudante, que qualifica tudo.
    sozinho = achar_substancia_sem_interacao(con)
    adicionar(con, aid, sozinho[0], sozinho[1], lista="RELATADA",
              horarios=("08:00",))
    for h in ("TABAGISMO", "ALCOOL", "CAFEINA"):
        adicionar_habito(con, aid, h, "NUNCA")

    # 16 a 20 — cinco pacientes de 5 medicamentos sorteados no banco
    ids = [r[0] for r in con.execute(
        "SELECT id FROM substancia WHERE n_produtos_ativos > 15 LIMIT 500")]
    for k in range(5):
        aid = novo("P%02d" % (16 + k), "Sorteado: 5 medicamentos de balcão")
        for sid in rnd.sample(ids, 5):
            nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                               (sid,)).fetchone()[0]
            adicionar(con, aid, sid, nome, lista="RELATADA",
                      horarios=(rnd.choice(("07:00", "08:00", "12:00",
                                            "20:00", "22:00")),))
    return casos


def linha(rotulo, valor, total=None):
    if total:
        print("  %-52s %6s  (%.1f%%)" % (rotulo, valor, 100.0 * valor / total))
    else:
        print("  %-52s %6s" % (rotulo, valor))


def main() -> int:
    rnd = random.Random(20260909)
    with banco_temporario() as con:
        casos = coorte(con, rnd)
        resultados = [(cod, desc, conciliar_atendimento(con, aid))
                      for cod, desc, aid in casos]

        print("=" * 78)
        print("QUALIDADE DOS DADOS — FASE 5")
        print("=" * 78)

        print("\nCOORTE")
        for cod, desc, res in resultados:
            print("  %-5s %-48s %2d achados · %2d div · %2d não aval."
                  % (cod, desc[:48], res.resumo["achados"],
                     res.resumo["divergencias"], res.resumo["nao_avaliado"]))

        n_pac = len(resultados)
        n_med = sum(r.resumo["medicamentos"] for _c, _d, r in resultados)
        principais = [a for _c, _d, r in resultados for a in r.achados]
        agrupados = [a for _c, _d, r in resultados for a in r.achados_agrupados]
        nao_aval = [n for _c, _d, r in resultados for n in r.nao_avaliado]
        pares = [p for _c, _d, r in resultados for p in r.pares]
        total_ach = len(principais)

        print("\nVOLUME")
        linha("pacientes sintéticos", n_pac)
        linha("medicamentos analisados", n_med)
        linha("achados apresentados (representantes)", total_ach)
        linha("achados absorvidos pelo agrupamento", len(agrupados))
        linha("achados antes do agrupamento",
              total_ach + len(agrupados))
        linha("média de achados por paciente", "%.1f" % (total_ach / n_pac))
        linha("itens declarados como NÃO avaliados", len(nao_aval))
        linha("pares de conciliação", len(pares))

        print("\nPOR TIPO (módulo)")
        for t, n in Counter(a.tipo for a in principais).most_common():
            linha(t, n, total_ach)

        print("\nPOR PRIORIDADE")
        for p in ("CRITICO", "ALTO", "MODERADO", "BAIXO", "INFORMATIVO"):
            linha(p, sum(1 for a in principais if a.prioridade == p), total_ach)

        print("\nPOR GRAVIDADE DECLARADA PELA FONTE")
        for g, n in Counter(a.gravidade_fonte or "(não se aplica)"
                            for a in principais).most_common():
            linha(g, n, total_ach)

        print("\nPOR CONFIANÇA DO SISTEMA (eixo independente da gravidade)")
        for c in ("ALTA", "MEDIA", "BAIXA"):
            linha(c, sum(1 for a in principais if a.confianca_sistema == c),
                  total_ach)

        print("\nPOR STATUS DA INFORMAÇÃO")
        for s, n in Counter(a.status_informacao for a in principais).most_common():
            linha(s, n, total_ach)

        print("\nPOR NATUREZA DA AFIRMAÇÃO")
        for s, n in Counter(a.natureza for a in principais).most_common():
            linha(s, n, total_ach)

        print("\nEVIDÊNCIA")
        com_ev = sum(1 for a in principais if a.evidencias)
        duas = sum(1 for a in principais
                   if len({e.fonte for e in a.evidencias}) > 1)
        conflito = sum(1 for a in principais if a.conflito_tipo)
        trecho = sum(1 for a in principais if a.trecho)
        linha("achados com ao menos uma evidência", com_ev, total_ach)
        linha("achados sem evidência nenhuma", total_ach - com_ev, total_ach)
        linha("achados sustentados por DUAS ou mais fontes", duas, total_ach)
        linha("achados com conflito declarado entre fontes", conflito, total_ach)
        linha("achados com trecho literal da fonte", trecho, total_ach)
        linha("evidências no total",
              sum(len(a.evidencias) for a in principais))

        print("\nREVISÃO")
        auto = sum(1 for a in principais
                   if a.status_informacao == "EXTRAIDO_AUTOMATICAMENTE")
        revis = sum(1 for a in principais if a.status_informacao == "REVISADO")
        prev = sum(1 for a in principais if a.origem_achado != "REGRA")
        linha("achados de extração automática (não revisada)", auto, total_ach)
        linha("achados revisados por farmacêutico", revis, total_ach)
        linha("achados previstos por modelo (ML ainda não existe)", prev,
              total_ach)
        linha("achados que exigem revisão profissional",
              sum(1 for a in principais if a.requer_revisao_profissional),
              total_ach)

        print("\nCONCILIAÇÃO")
        for s, n in Counter(p.situacao for p in pares).most_common():
            linha(s, n, len(pares) or 1)
        print("\n  por tipo de divergência:")
        for t, n in Counter(p.tipo_divergencia for p in pares
                            if p.tipo_divergencia).most_common():
            print("    %-50s %6d" % (t, n))
        nd = sum(1 for p in pares if p.intencionalidade != "NAO_DETERMINADA")
        linha("pares com intencionalidade decidida por script", nd)

        print("\nO QUE O SISTEMA DECLARA QUE NÃO AVALIOU")
        for m, n in Counter(n.motivo for n in nao_aval).most_common():
            linha(m, n, len(nao_aval) or 1)

        print("\nDEDUPLICAÇÃO")
        por_grupo = defaultdict(int)
        for a in agrupados:
            por_grupo[a.agrupado_em] += 1
        linha("grupos com mais de uma detecção", len(por_grupo))
        linha("detecções absorvidas", len(agrupados))
        perdidas = 0
        for _c, _d, r in resultados:
            for a in r.achados_agrupados:
                rep = next((x for x in r.achados
                            if x.grupo_chave == a.agrupado_em), None)
                if rep is None:
                    continue
                origens = {e.origem_afirmacao for e in rep.evidencias}
                perdidas += sum(1 for e in a.evidencias
                                if e.origem_afirmacao not in origens)
        linha("evidências perdidas no agrupamento", perdidas)

        print("\nLIMITAÇÕES DECLARADAS PELO PRÓPRIO MOTOR")
        for lim, n in Counter(lim for _c, _d, r in resultados
                              for lim in r.limitacoes).most_common(8):
            print("  %2dx %s" % (n, lim[:100]))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
