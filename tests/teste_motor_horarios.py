# -*- coding: utf-8 -*-
"""
VERIFICACAO 1 (funcional) do motor de horarios.

Treze casos clinicos, cada um com resultado esperado conhecido. Os casos
usam substancias e regras REAIS do banco; so o paciente e sintetico.

Uso: python tests/teste_motor_horarios.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "rules"))
sys.path.insert(0, str(RAIZ / "tests"))

from casos_clinicos import (ROTINA_PADRAO, adicionar_item,  # noqa: E402
                            adicionar_medicamento, banco_temporario,
                            criar_atendimento, sem_posologia,
                            substancia_com_regra, substancia_com_separacao,
                            substancia_por_nome)
from motor_horarios import montar_agenda  # noqa: E402

falhas = []
casos_rodados = 0


def confere(caso, desc, ok, detalhe=""):
    print("     [%s] %s %s" % ("OK " if ok else "FALHA", desc, detalhe))
    if not ok:
        falhas.append("%s / %s" % (caso, desc))


def tipos(agenda):
    return [c.tipo for c in agenda.conflitos]


def motivos(agenda):
    return [n.motivo for n in agenda.nao_avaliado]


def caso(titulo):
    global casos_rodados
    casos_rodados += 1
    print("\n%2d. %s" % (casos_rodados, titulo))


def main() -> int:
    with banco_temporario() as con:

        # ---------------------------------------------------------- 1
        caso("Medicamento em jejum, tomado bem longe da refeição")
        s = substancia_por_nome(con, "levotiroxina")
        a = criar_atendimento(con, "T-01")
        adicionar_medicamento(con, a, s[0], "Puran T4", 50, "mcg", 1,
                              horarios=("05:30",))
        ag = montar_agenda(con, a)
        ev = ag.eventos[0]
        confere("T-01", "regra de jejum reconhecida",
                ev.relacao_alimento == "JEJUM", ev.relacao_alimento)
        confere("T-01", "sem conflito de refeição",
                "JEJUM_PROXIMO_DE_REFEICAO" not in tipos(ag), str(tipos(ag)))
        confere("T-01", "orientação em português",
                bool(ev.orientacao) and "jejum" in ev.orientacao.lower(),
                ev.orientacao)

        # ---------------------------------------------------------- 2
        caso("Mesmo medicamento em jejum, agora junto do café da manhã")
        a = criar_atendimento(con, "T-02")
        adicionar_medicamento(con, a, s[0], "Puran T4", 50, "mcg", 1,
                              horarios=("07:00",))
        ag = montar_agenda(con, a)
        confere("T-02", "conflito de jejum detectado",
                "JEJUM_PROXIMO_DE_REFEICAO" in tipos(ag), str(tipos(ag)))
        c = [x for x in ag.conflitos if x.tipo == "JEJUM_PROXIMO_DE_REFEICAO"][0]
        confere("T-02", "conflito classificado",
                c.classificacao in ("CONFLITO_CONFIRMADO", "POSSIVEL_CONFLITO"),
                c.classificacao)
        confere("T-02", "justificativa cita o horário da refeição",
                "07:00" in c.justificativa, c.justificativa[:70])

        # ---------------------------------------------------------- 3
        caso("Medicamento com alimento, tomado longe de qualquer refeição")
        s2 = substancia_com_regra(con, "COM_ALIMENTO")
        a = criar_atendimento(con, "T-03")
        adicionar_medicamento(con, a, s2[0], s2[1], 1, "comprimido", 1,
                              horarios=("10:00",))
        ag = montar_agenda(con, a)
        confere("T-03", "possível conflito de alimento",
                "ALIMENTO_EXIGIDO_SEM_REFEICAO_PROXIMA" in tipos(ag),
                str(tipos(ag)))

        # ---------------------------------------------------------- 4
        caso("Mesmo medicamento, agora no horário do almoço")
        a = criar_atendimento(con, "T-04")
        adicionar_medicamento(con, a, s2[0], s2[1], 1, "comprimido", 1,
                              horarios=("12:00",))
        ag = montar_agenda(con, a)
        confere("T-04", "sem conflito de alimento",
                "ALIMENTO_EXIGIDO_SEM_REFEICAO_PROXIMA" not in tipos(ag),
                str(tipos(ag)))

        # ---------------------------------------------------------- 5
        caso("Separação com intervalo conhecido, alvo presente e perto")
        sep = substancia_com_separacao(con, com_intervalo=True)
        a = criar_atendimento(con, "T-05")
        adicionar_medicamento(con, a, sep[0], sep[1], 1, "comprimido", 1,
                              horarios=("08:00",))
        adicionar_item(con, a, sep[4], horario="08:00")
        ag = montar_agenda(con, a)
        confere("T-05", "separação não respeitada é detectada",
                "SEPARACAO_NAO_RESPEITADA" in tipos(ag), str(tipos(ag)))
        c = [x for x in ag.conflitos if x.tipo == "SEPARACAO_NAO_RESPEITADA"]
        if c:
            confere("T-05", "intervalo exigido preservado",
                    c[0].intervalo_exigido == sep[2],
                    "exigido=%s observado=%s" % (c[0].intervalo_exigido,
                                                 c[0].intervalo_observado))
            confere("T-05", "conflito confirmado",
                    c[0].classificacao == "CONFLITO_CONFIRMADO",
                    c[0].classificacao)

        # ---------------------------------------------------------- 6
        caso("Mesma separação, agora com o intervalo respeitado")
        a = criar_atendimento(con, "T-06")
        adicionar_medicamento(con, a, sep[0], sep[1], 1, "comprimido", 1,
                              horarios=("08:00",))
        adicionar_item(con, a, sep[4], horario="14:00")
        ag = montar_agenda(con, a)
        confere("T-06", "sem conflito de separação",
                "SEPARACAO_NAO_RESPEITADA" not in tipos(ag), str(tipos(ag)))

        # ---------------------------------------------------------- 7
        caso("Separação exigida com intervalo DESCONHECIDO na fonte")
        sd = substancia_com_separacao(con, com_intervalo=False)
        if sd:
            a = criar_atendimento(con, "T-07")
            adicionar_medicamento(con, a, sd[0], sd[1], 1, "comprimido", 1,
                                  horarios=("08:00",))
            if sd[4]:
                adicionar_item(con, a, sd[4], horario="08:00")
            ag = montar_agenda(con, a)
            confere("T-07", "classificado como regra desconhecida",
                    "SEPARACAO_COM_INTERVALO_DESCONHECIDO" in tipos(ag)
                    or "REGRA_SEM_INTERVALO_ESTABELECIDO" in motivos(ag),
                    str(tipos(ag)) + str(motivos(ag)))
            textos = " ".join(c.justificativa for c in ag.conflitos) + \
                " ".join(n.detalhe for n in ag.nao_avaliado)
            confere("T-07", "nenhum intervalo foi inventado",
                    "não está estabelecido" in textos
                    or "não publica o intervalo" in textos, textos[:80])
        else:
            print("     (nenhuma regra sem intervalo no banco; caso pulado)")

        # ---------------------------------------------------------- 8
        caso("Antiácido por CLASSE ATC, não por substância")
        anti = con.execute(
            "SELECT s.id, s.nome_dcb FROM substancia s WHERE s.atc_codigo "
            "LIKE 'A02A%' LIMIT 1").fetchone()
        alvo = con.execute(
            "SELECT s.id, s.nome_dcb FROM regra_separacao r "
            "JOIN substancia s ON s.id=r.substancia_id "
            "WHERE r.alvo_tipo='CLASSE_ATC' LIMIT 1").fetchone()
        if anti and alvo:
            a = criar_atendimento(con, "T-08")
            adicionar_medicamento(con, a, alvo[0], alvo[1], 1, "comprimido", 1,
                                  horarios=("08:00",))
            adicionar_medicamento(con, a, anti[0], anti[1], 1, "comprimido", 1,
                                  horarios=("08:00",))
            ag = montar_agenda(con, a)
            confere("T-08", "conflito por classe é detectado",
                    any("SEPARACAO" in t for t in tipos(ag)), str(tipos(ag)))
        else:
            print("     (sem antiácido com ATC A02A no banco; caso pulado)")

        # ---------------------------------------------------------- 9
        caso("Frequência declarada não bate com os horários informados")
        a = criar_atendimento(con, "T-09")
        adicionar_medicamento(con, a, s[0], "Puran T4", 50, "mcg", 3,
                              horarios=("05:30",))
        ag = montar_agenda(con, a)
        confere("T-09", "incompatibilidade detectada",
                "FREQUENCIA_INCOMPATIVEL_COM_HORARIOS" in tipos(ag),
                str(tipos(ag)))

        # ---------------------------------------------------------- 10
        caso("Intervalo entre doses menor que o declarado")
        a = criar_atendimento(con, "T-10")
        adicionar_medicamento(con, a, s2[0], s2[1], 1, "comprimido", 2,
                              intervalo=12, horarios=("12:00", "16:00"))
        ag = montar_agenda(con, a)
        confere("T-10", "intervalo insuficiente detectado",
                "INTERVALO_ENTRE_DOSES_MENOR_QUE_O_DECLARADO" in tipos(ag),
                str(tipos(ag)))
        c = [x for x in ag.conflitos
             if x.tipo == "INTERVALO_ENTRE_DOSES_MENOR_QUE_O_DECLARADO"]
        if c:
            confere("T-10", "observado 4 h contra 12 h exigidas",
                    c[0].intervalo_observado == 4.0
                    and c[0].intervalo_exigido == 12,
                    "obs=%s exig=%s" % (c[0].intervalo_observado,
                                        c[0].intervalo_exigido))

        # ---------------------------------------------------------- 11
        caso("Medicamento sem posologia registrada")
        a = criar_atendimento(con, "T-11")
        sem_posologia(con, a, s[0], "Puran T4")
        ag = montar_agenda(con, a)
        confere("T-11", "declarado como não avaliado",
                "POSOLOGIA_NAO_INFORMADA" in motivos(ag), str(motivos(ag)))
        confere("T-11", "nenhum evento inventado", not ag.eventos,
                str(len(ag.eventos)))

        # ---------------------------------------------------------- 12
        caso("Medicamento se necessário (PRN), sem horário fixo")
        a = criar_atendimento(con, "T-12")
        adicionar_medicamento(con, a, s2[0], s2[1], 1, "comprimido", None,
                              horarios=(), continuo=0, prn=1,
                              condicao="se dor")
        ag = montar_agenda(con, a)
        confere("T-12", "evento criado sem horário",
                len(ag.eventos) == 1 and ag.eventos[0].hora is None,
                str([(e.medicamento, e.hora) for e in ag.eventos]))
        confere("T-12", "marcado como se necessário",
                ag.eventos[0].se_necessario
                and ag.eventos[0].status_informacao ==
                "SE_NECESSARIO_SEM_HORARIO_FIXO",
                ag.eventos[0].status_informacao)

        # ---------------------------------------------------------- 13
        caso("Horário fora da rotina e substância não reconhecida")
        a = criar_atendimento(con, "T-13")
        adicionar_medicamento(con, a, s[0], "Puran T4", 50, "mcg", 1,
                              horarios=("03:00",))
        adicionar_medicamento(con, a, None, "remédio da vizinha", 1,
                              "comprimido", 1, horarios=("09:00",))
        ag = montar_agenda(con, a)
        confere("T-13", "horário fora da rotina detectado",
                "HORARIO_FORA_DA_ROTINA" in tipos(ag), str(tipos(ag)))
        confere("T-13", "não reconhecido é declarado",
                "SUBSTANCIA_NAO_RECONHECIDA" in motivos(ag), str(motivos(ag)))

        # ---------------------------------------------------------- 14
        caso("Paciente polimedicado: agenda montada e ordenada")
        a = criar_atendimento(con, "T-14")
        for nome, sid, horas in (("Puran T4", s[0], ("05:30",)),
                                 (s2[1], s2[0], ("12:00", "19:30")),
                                 (sep[1], sep[0], ("08:00",))):
            adicionar_medicamento(con, a, sid, nome, 1, "comprimido",
                                  len(horas), horarios=horas)
        ag = montar_agenda(con, a)
        horas = [e.hora for e in ag.eventos]
        confere("T-14", "eventos em ordem crescente de horário",
                horas == sorted(horas), str(horas))
        confere("T-14", "4 tomadas montadas", len(ag.eventos) == 4,
                str(len(ag.eventos)))
        print("     resumo:", ag.resumo())

        # ---------------------------------------------------------- 15
        caso("Duplicidade da mesma substância no atendimento")
        a = criar_atendimento(con, "T-15")
        adicionar_medicamento(con, a, s[0], "Puran T4", 50, "mcg", 1,
                              horarios=("05:30",))
        adicionar_medicamento(con, a, s[0], "Levoid", 25, "mcg", 1,
                              horarios=("05:45",))
        ag = montar_agenda(con, a)
        confere("T-15", "duplicidade detectada",
                "DUPLICIDADE_DA_MESMA_SUBSTANCIA" in tipos(ag), str(tipos(ag)))

        # ---------------------------------------------------------- 16
        caso("Sem rotina informada: regra alimentar não pode ser verificada")
        a = criar_atendimento(con, "T-16", rotina={})
        adicionar_medicamento(con, a, s[0], "Puran T4", 50, "mcg", 1,
                              horarios=("07:00",))
        ag = montar_agenda(con, a)
        confere("T-16", "ausência de rotina é declarada",
                "HORARIO_NAO_INFORMADO" in motivos(ag), str(motivos(ag)))
        confere("T-16", "não afirmou conflito sem base",
                "JEJUM_PROXIMO_DE_REFEICAO" not in tipos(ag), str(tipos(ag)))

    print("\n" + "=" * 66)
    print("casos clínicos executados: %d" % casos_rodados)
    if falhas:
        print("FALHAS: %d" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("TODOS OS CASOS CLÍNICOS PASSARAM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
