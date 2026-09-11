# -*- coding: utf-8 -*-
"""
Deteccao de contradicao ENTRE fontes nas regras de administracao.

O esquema guarda uma linha por (substancia, tipo, fonte) de proposito
(P-01), justamente para que duas fontes possam discordar. Este script acha
essas discordancias e as registra em auditoria_conflito.

Nao resolve nenhuma: a Fase 20 da especificacao proibe escolher em silencio.
Quem decide e o farmaceutico, e ate la o motor exibe a divergencia.

Contradicao aqui = duas regras EXCLUSIVAS entre si para a mesma substancia
('em jejum' e 'com alimento' nao podem valer ao mesmo tempo).

Uso: python pipeline/58_conflitos_administracao.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import conectar, resumo  # noqa: E402

# Grupos de tipos mutuamente exclusivos. Tipos fora daqui convivem sem
# problema: 'com agua abundante' + 'nao partir' e perfeitamente coerente.
EXCLUSIVOS = {"JEJUM", "COM_ALIMENTO", "APOS_ALIMENTO",
              "ANTES_ALIMENTO", "INDIFERENTE_ALIMENTO"}

# 'INDIFERENTE_ALIMENTO' contra qualquer outro e divergencia branda: a fonte
# so esta sendo menos especifica. Jejum contra com-alimento e contradicao dura.
def dureza(a: str, b: str) -> str:
    if "INDIFERENTE_ALIMENTO" in (a, b):
        return "DIVERGENCIA_DE_ESPECIFICIDADE"
    return "CONTRADICAO"


def main() -> int:
    con = conectar()

    linhas = con.execute(
        "SELECT r.substancia_id, s.nome_dcb, r.tipo, f.nome, r.id "
        "FROM regra_administracao r "
        "JOIN substancia s ON s.id = r.substancia_id "
        "JOIN fonte f ON f.id = r.fonte_id "
        "WHERE r.tipo IN (%s)" % ",".join("?" * len(EXCLUSIVOS)),
        tuple(EXCLUSIVOS)).fetchall()

    por_substancia = defaultdict(list)
    for sid, nome, tipo, fonte, rid in linhas:
        por_substancia[(sid, nome)].append((tipo, fonte, rid))

    n_conflitos = n_contradicoes = n_divergencias = 0
    exemplos = []
    for (sid, nome), regras in por_substancia.items():
        tipos = {t for t, _, _ in regras}
        if len(tipos) < 2:
            continue
        # registra o par mais grave encontrado
        lista = sorted(regras)
        a, b = lista[0], lista[1]
        classe = dureza(a[0], b[0])
        ja = con.execute(
            "SELECT 1 FROM auditoria_conflito WHERE tabela_alvo='regra_administracao' "
            "AND id_alvo=? AND fonte_a=? AND fonte_b=? AND valor_a=? AND valor_b=?",
            (sid, a[1], b[1], a[0], b[0])).fetchone()
        if ja:
            continue
        con.execute(
            "INSERT OR IGNORE INTO auditoria_conflito (tabela_alvo,id_alvo,descricao,"
            "fonte_a,valor_a,fonte_b,valor_b,decisao,justificativa) "
            "VALUES ('regra_administracao',?,?,?,?,?,?,'NAO_RESOLVIDO',?)",
            (sid,
             "%s: fontes discordam sobre a relação com alimento" % nome,
             a[1], a[0], b[1], b[0],
             "Registrado sem resolver. %s. As duas regras permanecem no banco "
             "e a interface mostra a divergência ao farmacêutico." %
             ("Contradição direta entre orientações" if classe == "CONTRADICAO"
              else "Uma fonte é apenas menos específica que a outra")))
        n_conflitos += 1
        if classe == "CONTRADICAO":
            n_contradicoes += 1
        else:
            n_divergencias += 1
        if len(exemplos) < 8:
            exemplos.append((nome, a[0], a[1][:26], b[0], b[1][:26], classe))

    con.commit()

    concordam = con.execute(
        "SELECT COUNT(*) FROM vw_regra_concordancia WHERE n_fontes > 1"
    ).fetchone()[0]
    total_conf = con.execute(
        "SELECT COUNT(*) FROM auditoria_conflito").fetchone()[0]

    resumo("CONFLITOS ENTRE FONTES — REGRAS DE ADMINISTRACAO", [
        ("substancias com regra de alimentacao", len(por_substancia)),
        ("conflitos novos registrados", n_conflitos),
        ("  contradicao direta (jejum x com alimento)", n_contradicoes),
        ("  divergencia de especificidade", n_divergencias),
        ("regras confirmadas por duas fontes", concordam),
        ("total em auditoria_conflito", total_conf),
    ])
    if exemplos:
        print("\n  amostra:")
        for nome, ta, fa, tb, fb, classe in exemplos:
            print("    %-24s %-22s (%s)" % (nome[:24], ta, fa))
            print("    %-24s %-22s (%s)  -> %s" % ("", tb, fb, classe))
    print("\n  Nenhum conflito foi resolvido automaticamente.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
