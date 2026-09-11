# -*- coding: utf-8 -*-
"""
CARGA DE PAPEL FARMACOCINETICO — tabela de farmacos-indice da FDA.

Alimenta o modulo 7 do motor (farmaco x CYP / enzimas / transportadores).

POR QUE SO A FDA, E NAO AS BULAS
--------------------------------
Foi medido antes de decidir: das 150 bulas do acervo, **11** mencionam alguma
enzima ou transportador, e as frases nao sao extraiveis com precisao
aceitavel. Exemplo real, da bula de carbamazepina:

    "A coadministracao de indutores de CYP3A4 com carbamazepina pode diminuir
     as concentracoes plasmaticas de carbamazepina"

Um regex que procure "indutor.*CYP3A4" perto de "carbamazepina" concluiria que
a carbamazepina **e** indutora de CYP3A4. Ela e — mas nao por causa desta
frase, que diz o oposto: fala de indutores que agem SOBRE ela. Acertar pelo
motivo errado e o mesmo erro do `mapping.csv` recusado em D-004, e a proxima
frase acertaria ao contrario.

Entao a tabela de farmacos-indice da FDA entra sozinha: 31 linhas, cada uma
com sistema, papel e **potencia declarada pelo regulador**. Pouco volume, alta
confianca, zero inferencia. A lacuna fica declarada em vez de preenchida com
leitura duvidosa.

O QUE O MOTOR FAZ COM ISTO
--------------------------
Cruza inibidor/indutor de um sistema com substrato do mesmo sistema e produz
achado de **inferencia mecanistica**: natureza POSSIVEL, nunca DOCUMENTADO.
Quando o mesmo par ja tem interacao documentada, esta linha vira evidencia
que EXPLICA o mecanismo, e nao um segundo alerta.

Uso: python pipeline/62_papel_farmacocinetico.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (abrir_carga, campo, chaves_candidatas, conectar,  # noqa: E402
                    fechar_carga, id_fonte, ler_csv, resumo)

FONTE = "FDA - Tabela de farmacos-indice de interacao"
ARQUIVO = "fontes_novas/07_fda_ddi/fda_index_cyp.csv"

# A FDA escreve pelo nome adotado nos EUA (USAN); o Brasil registra pela DCB,
# derivada do INN. Onde os dois divergem, o esqueleto fonetico nao casa, e a
# substancia existe no Brasil. Esta tabela declara a divergencia de
# NOMENCLATURA -- nao afirma farmacologia nenhuma.
#
#   rifampin (USAN)  ==  rifampicin (INN)  ==  rifampicina (DCB, id 1816)
#
# Custava 5 das 31 linhas da FDA, e rifampicina e o indutor enzimatico de
# maior impacto de balcao do conjunto. Cada entrada nova aqui precisa da
# mesma justificativa: fonte da equivalencia, e nao conveniencia.
USAN_PARA_INN = {
    "rifampin": "rifampicin",
}


def indice(con):
    idx = defaultdict(set)
    for sid, chave in con.execute("SELECT id, chave_normalizada FROM substancia"):
        idx[chave].add(sid)
    for sid, chave in con.execute(
            "SELECT substancia_id, chave_normalizada FROM substancia_sinonimo"):
        idx[chave].add(sid)
    return idx


def main() -> int:
    con = conectar()
    if con.execute("SELECT COUNT(*) FROM papel_farmacocinetico").fetchone()[0]:
        print("papel_farmacocinetico ja carregado — nada a fazer")
        con.close()
        return 0

    idx = indice(con)
    fonte_id = id_fonte(con, FONTE)
    carga_id = abrir_carga(con, FONTE, "pipeline/62_papel_farmacocinetico.py",
                           ARQUIVO, "FDA clinical index drugs, consulta 02/09/2026")

    lidos = inseridos = sem_br = ambiguos = 0
    nao_casaram, por_sistema, por_papel = [], defaultdict(int), defaultdict(int)

    for i, linha in ler_csv(ARQUIVO):
        lidos += 1
        farmaco = campo(i, linha, "farmaco")
        sistema = campo(i, linha, "sistema")
        papel = campo(i, linha, "papel")
        potencia = campo(i, linha, "potencia") or "NAO_DECLARADA"
        tabela = campo(i, linha, "tabela_fda")
        obs = campo(i, linha, "observacao")

        cand = set()
        for termo in (farmaco, USAN_PARA_INN.get(farmaco.lower())):
            if not termo:
                continue
            for k in chaves_candidatas(termo):
                cand |= idx.get(k, set())
        if len(cand) > 1:
            ambiguos += 1
            nao_casaram.append("%s (ambiguo: %d candidatos)" % (farmaco, len(cand)))
            continue
        if not cand:
            sem_br += 1
            nao_casaram.append(farmaco)
            continue

        sid = next(iter(cand))
        cur = con.execute(
            "INSERT OR IGNORE INTO papel_farmacocinetico "
            "(substancia_id, sistema, papel, potencia, fonte_id) VALUES (?,?,?,?,?)",
            (sid, sistema, papel, potencia, fonte_id))
        if cur.rowcount:
            inseridos += 1
            por_sistema[sistema] += 1
            por_papel[papel] += 1
            con.execute(
                "INSERT OR IGNORE INTO evidencia (tabela_alvo,id_alvo,fonte_id,"
                "carga_id,documento,trecho,nivel_evidencia,metodo_extracao) "
                "VALUES ('papel_farmacocinetico',?,?,?,?,?,'RESPALDADA','CARGA_DIRETA')",
                (cur.lastrowid, fonte_id, carga_id, ARQUIVO,
                 "%s | %s %s %s | %s" % (tabela, farmaco, papel, sistema, obs)))

    fechar_carga(con, carga_id, lidos, inseridos, lidos - inseridos,
                 "sem correspondencia BR: %d; ambiguos: %d" % (sem_br, ambiguos))
    con.commit()

    subs = con.execute("SELECT COUNT(DISTINCT substancia_id) FROM "
                       "papel_farmacocinetico").fetchone()[0]
    # Pares potencialmente inferiveis: inibidor/indutor x substrato do MESMO sistema.
    pares = con.execute(
        "SELECT COUNT(*) FROM papel_farmacocinetico a "
        "JOIN papel_farmacocinetico b ON b.sistema = a.sistema "
        "WHERE a.papel IN ('INIBIDOR','INDUTOR') AND b.papel='SUBSTRATO' "
        "AND a.substancia_id <> b.substancia_id").fetchone()[0]

    resumo("PAPEL FARMACOCINETICO (FDA)", [
        ("linhas lidas", lidos),
        ("inseridas", inseridos),
        ("sem correspondencia no Brasil", sem_br),
        ("ambiguas (nao resolvidas)", ambiguos),
        ("substancias BR cobertas", "%d de 2094 (%.1f%%)"
         % (subs, 100.0 * subs / 2094)),
        ("por papel", dict(por_papel)),
        ("por sistema", dict(por_sistema)),
        ("pares inferiveis (inibidor/indutor x substrato)", pares),
    ])
    if nao_casaram:
        print("\n  nao casaram com substancia brasileira:")
        for n in sorted(set(nao_casaram)):
            print("    %s" % n)
    print("\n  LIMITE DECLARADO: 8 sistemas CYP, nenhum transportador. "
          "\n  Nao ha no acervo fonte de papel PK com cobertura ampla; a lacuna"
          "\n  esta registrada em docs/novas_fontes.md.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
