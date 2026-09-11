# -*- coding: utf-8 -*-
"""
CARGA DE INTERACAO FARMACO x FARMACO — DDInter + db_drug_interactions.

E a primeira tarefa da Fase 5: sem esta tabela o motor de conciliacao nao
tem modulo 1, e `interacao_substancia` estava vazia.

AS DUAS FONTES SE COMPLEMENTAM E NAO SE SUBSTITUEM
--------------------------------------------------
  DDInter                 gradua a gravidade (Major/Moderate/Minor/Unknown)
                          e NAO publica descricao nenhuma.
  db_drug_interactions    publica a descricao do efeito, em ingles, e NAO
                          gradua nada.

Por isso cada uma entra como uma LINHA PROPRIA do mesmo par (a unicidade do
esquema e por `fonte_id`, decisao P-01). Fundir as duas numa linha so
destruiria a possibilidade de detectar discordancia, e e o que faz
`vw_conflito_gravidade` existir.

O QUE ESTE SCRIPT NUNCA FAZ
---------------------------
  - Nao inventa gravidade. `Unknown` do DDInter vira NAO_DETERMINADA, e o
    db_drug_interactions entra inteiro como NAO_DETERMINADA porque a fonte
    nao gradua. Sao 0 linhas com gravidade deduzida.
  - Nao inventa conduta. Nenhuma das duas fontes publica conduta; a coluna
    fica NULL e o motor declara a ausencia.
  - Nao traduz pela metade. A descricao so vira portugues quando o molde
    casa inteiro (pipeline/traducao_interacao.py); senao fica NULL e o
    ingles original permanece em `descricao_original`.
  - Nao resolve ambiguidade por sorteio. Nome estrangeiro que casa com mais
    de uma substancia brasileira vai para `resolucao_ambigua` e o par e
    descartado, contado e declarado.

Uso: python pipeline/60_interacoes_substancia.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (ACERVO, abrir_carga, campo, chaves_candidatas, conectar,  # noqa: E402
                    fechar_carga, id_fonte, inserir_unico, ler_csv, resumo)
from traducao_interacao import traduzir  # noqa: E402

FONTE_DDINTER = "DDInter"
FONTE_DBDI = "db_drug_interactions"

ARQUIVOS_DDINTER = ["DDInter/ddinter_downloads_code_%s.csv" % c
                    for c in "ABDHLPRV"]
ARQUIVO_DBDI = "db_drug_interactions.csv"

# DDInter publica o nivel; nao ha traducao de valor, so de rotulo.
NIVEL = {"major": "MAIOR", "moderate": "MODERADA", "minor": "MENOR",
         "unknown": "NAO_DETERMINADA"}

# Classificacao do MECANISMO a partir do molde da frase. Farmacocinetica e
# farmacodinamica sao distinguiveis pelo verbo da fonte; o que nao se
# distingue fica NAO_DETERMINADO em vez de receber um chute.
PADRAO_PK = re.compile(
    r"\b(metabolism of|serum concentration|absorption of|excretion rate|"
    r"bioavailability of|protein binding|active metabolites)\b", re.I)
PADRAO_PD = re.compile(r"\b(activities of|risk or severity of)\b", re.I)


def classificar_tipo(descricao: str) -> str:
    if not descricao:
        return "NAO_DETERMINADO"
    if PADRAO_PK.search(descricao):
        return "FARMACOCINETICA"
    if PADRAO_PD.search(descricao):
        return "FARMACODINAMICA"
    return "NAO_DETERMINADO"


# ---------------------------------------------------------------- resolucao
def indice_substancias(con):
    """chave normalizada -> conjunto de ids de substancia brasileira."""
    idx = defaultdict(set)
    for sid, chave in con.execute("SELECT id, chave_normalizada FROM substancia"):
        idx[chave].add(sid)
    for sid, chave in con.execute(
            "SELECT substancia_id, chave_normalizada FROM substancia_sinonimo"):
        idx[chave].add(sid)
    return idx


class Resolvedor:
    """Nome estrangeiro -> substancia brasileira, com memoria e ambiguidade.

    Guarda o resultado por nome: os arquivos repetem os mesmos 1.939 nomes em
    160 mil linhas, e normalizar duas vezes o mesmo nome seria desperdicio.
    """

    def __init__(self, con, idx):
        self.con = con
        self.idx = idx
        self.cache = {}
        self.ambiguos = {}          # nome -> [ids]
        self.sem_correspondencia = set()

    def resolve(self, nome: str):
        if not nome:
            return None
        chave = nome.strip().lower()
        if chave in self.cache:
            return self.cache[chave]
        candidatos = set()
        for k in chaves_candidatas(nome):
            candidatos |= self.idx.get(k, set())
        if len(candidatos) == 1:
            sid = next(iter(candidatos))
        elif len(candidatos) > 1:
            sid = None
            self.ambiguos[nome.strip()] = sorted(candidatos)
        else:
            sid = None
            self.sem_correspondencia.add(nome.strip())
        self.cache[chave] = sid
        return sid

    def gravar_ambiguidades(self, fonte_id, carga_id):
        """Ambiguidade preservada para curadoria, nunca resolvida por sorteio."""
        n = 0
        for termo, ids in self.ambiguos.items():
            nomes = [{"id": i, "nome_dcb": self.con.execute(
                "SELECT nome_dcb FROM substancia WHERE id=?", (i,)).fetchone()[0]}
                for i in ids]
            cur = self.con.execute(
                "INSERT OR IGNORE INTO resolucao_ambigua (termo_origem, "
                "chave_normalizada, fonte_id, carga_id, candidatos, n_candidatos) "
                "VALUES (?,?,?,?,?,?)",
                (termo, (chaves_candidatas(termo) or [""])[0], fonte_id, carga_id,
                 json.dumps(nomes, ensure_ascii=False), len(ids)))
            n += cur.rowcount if cur.rowcount > 0 else 0
        return n

    def gravar_sinonimos_inn(self):
        """Nome em ingles que casou 1:1 vira sinonimo INN da substancia.

        E o que permite `traducao_interacao.carregar_mapa_nomes` escrever
        "omeprazol" onde a fonte escreveu "Omeprazole". So o casamento
        inequivoco entra: o ambiguo continua fora, de proposito.
        """
        from normalizacao import skeleton
        n = 0
        for nome_lower, sid in self.cache.items():
            if sid is None:
                continue
            cur = self.con.execute(
                "INSERT OR IGNORE INTO substancia_sinonimo (substancia_id, nome, "
                "chave_normalizada, tipo) VALUES (?,?,?,'INN')",
                (sid, nome_lower, skeleton(nome_lower)))
            n += 1 if cur.rowcount > 0 else 0
        return n


# ------------------------------------------------------------------- cargas
def carregar_ddinter(con, resolvedor):
    fonte_id = id_fonte(con, FONTE_DDINTER)
    carga_id = abrir_carga(con, FONTE_DDINTER, "pipeline/60_interacoes_substancia.py",
                           ARQUIVOS_DDINTER[0], "DDInter download completo")
    lidos = inseridos = ignorados = mesmo_farmaco = ja_existiam = 0
    vistos = set()
    por_nivel = defaultdict(int)

    for rel in ARQUIVOS_DDINTER:
        for idx, linha in ler_csv(rel):
            lidos += 1
            a = campo(idx, linha, "Drug_A")
            b = campo(idx, linha, "Drug_B")
            nivel = (campo(idx, linha, "Level") or "unknown").strip().lower()
            sa, sb = resolvedor.resolve(a), resolvedor.resolve(b)
            if sa is None or sb is None:
                ignorados += 1
                continue
            if sa == sb:
                # Dois nomes estrangeiros que caem na mesma substancia BR
                # (forma acida x sal). Nao e par: e a mesma molecula.
                mesmo_farmaco += 1
                continue
            par = (min(sa, sb), max(sa, sb))
            if par in vistos:
                ignorados += 1
                continue
            vistos.add(par)
            gravidade = NIVEL.get(nivel, "NAO_DETERMINADA")
            por_nivel[gravidade] += 1
            iid, novo = inserir_unico(
                con, "interacao_substancia",
                dict(substancia_a_id=par[0], substancia_b_id=par[1],
                     tipo="NAO_DETERMINADO", gravidade=gravidade,
                     origem="FONTE_EXTERNA", fonte_id=fonte_id,
                     status_revisao="PENDENTE"),
                "substancia_a_id=? AND substancia_b_id=? AND fonte_id=?",
                (par[0], par[1], fonte_id))
            con.execute(
                "INSERT OR IGNORE INTO evidencia (tabela_alvo,id_alvo,fonte_id,"
                "carga_id,documento,trecho,nivel_evidencia,metodo_extracao) "
                "VALUES ('interacao_substancia',?,?,?,?,?,'LIMITADA','CARGA_DIRETA')",
                (iid, fonte_id, carga_id, rel,
                 "%s x %s | Level=%s" % (a, b, nivel)))
            if novo:
                inseridos += 1
            else:
                ja_existiam += 1

    novos_amb = resolvedor.gravar_ambiguidades(fonte_id, carga_id)
    fechar_carga(con, carga_id, lidos, inseridos, ignorados,
                 "mesmo farmaco BR nos dois lados: %d; ambiguidades novas: %d"
                 % (mesmo_farmaco, novos_amb))
    con.commit()
    return dict(lidos=lidos, inseridos=inseridos, ignorados=ignorados,
                ja_existiam=ja_existiam, mesmo_farmaco=mesmo_farmaco,
                por_nivel=dict(por_nivel))


def carregar_dbdi(con, resolvedor, mapa_nomes):
    fonte_id = id_fonte(con, FONTE_DBDI)
    carga_id = abrir_carga(con, FONTE_DBDI, "pipeline/60_interacoes_substancia.py",
                           ARQUIVO_DBDI)
    lidos = inseridos = ignorados = mesmo_farmaco = traduzidas = 0
    ja_existiam = 0
    vistos = set()
    por_tipo = defaultdict(int)

    for idx, linha in ler_csv(ARQUIVO_DBDI):
        lidos += 1
        a = campo(idx, linha, "Drug 1")
        b = campo(idx, linha, "Drug 2")
        desc = campo(idx, linha, "Interaction Description")
        sa, sb = resolvedor.resolve(a), resolvedor.resolve(b)
        if sa is None or sb is None:
            ignorados += 1
            continue
        if sa == sb:
            mesmo_farmaco += 1
            continue
        par = (min(sa, sb), max(sa, sb))
        if par in vistos:
            ignorados += 1
            continue
        vistos.add(par)

        pt, ok = traduzir(desc, mapa_nomes)
        if ok:
            traduzidas += 1
        tipo = classificar_tipo(desc)
        por_tipo[tipo] += 1
        iid, novo = inserir_unico(
            con, "interacao_substancia",
            dict(substancia_a_id=par[0], substancia_b_id=par[1], tipo=tipo,
                 efeito_esperado=(pt if ok else None),
                 descricao_original=(desc or None),
                 gravidade="NAO_DETERMINADA", origem="FONTE_EXTERNA",
                 fonte_id=fonte_id, status_revisao="PENDENTE"),
            "substancia_a_id=? AND substancia_b_id=? AND fonte_id=?",
            (par[0], par[1], fonte_id))
        # CARGA_DIRETA, e nao REGEX: o par e a descricao sao colunas do
        # arquivo, lidas sem interpretacao. O unico campo derivado por padrao
        # de texto e `tipo` (PK/PD), que e secundario e nao e o que a
        # evidencia atesta. Marcar a linha inteira como REGEX rebaixava a
        # confianca de 54 mil interacoes por causa de um campo acessorio —
        # defeito encontrado pelo caso 18 da verificacao funcional. A
        # procedencia fraca desta fonte ja esta declarada onde deve estar:
        # `fonte.confiabilidade = MEDIA` (ver pipeline/10_fontes.py).
        con.execute(
            "INSERT OR IGNORE INTO evidencia (tabela_alvo,id_alvo,fonte_id,"
            "carga_id,documento,trecho,nivel_evidencia,metodo_extracao) "
            "VALUES ('interacao_substancia',?,?,?,?,?,'LIMITADA','CARGA_DIRETA')",
            (iid, fonte_id, carga_id, ARQUIVO_DBDI, desc))
        if novo:
            inseridos += 1
        else:
            ja_existiam += 1

    novos_amb = resolvedor.gravar_ambiguidades(fonte_id, carga_id)
    fechar_carga(con, carga_id, lidos, inseridos, ignorados,
                 "mesmo farmaco BR nos dois lados: %d; traduzidas: %d; "
                 "ambiguidades novas: %d" % (mesmo_farmaco, traduzidas, novos_amb))
    con.commit()
    return dict(lidos=lidos, inseridos=inseridos, ignorados=ignorados,
                ja_existiam=ja_existiam, mesmo_farmaco=mesmo_farmaco,
                traduzidas=traduzidas, por_tipo=dict(por_tipo))


def main() -> int:
    con = conectar()
    if con.execute("SELECT COUNT(*) FROM interacao_substancia").fetchone()[0]:
        print("interacao_substancia ja carregada — nada a fazer "
              "(use --recriar no pipeline para refazer)")
        con.close()
        return 0

    idx = indice_substancias(con)
    resolvedor = Resolvedor(con, idx)

    print("carregando DDInter (gradua gravidade, nao publica descricao)...")
    r1 = carregar_ddinter(con, resolvedor)

    # Os sinonimos INN precisam existir ANTES da traducao, para que o texto
    # em portugues nomeie o farmaco em DCB brasileiro.
    n_inn = resolvedor.gravar_sinonimos_inn()
    con.commit()
    from traducao_interacao import carregar_mapa_nomes
    mapa = carregar_mapa_nomes(con)

    print("carregando db_drug_interactions (descreve o efeito, nao gradua)...")
    r2 = carregar_dbdi(con, resolvedor, mapa)

    total = con.execute("SELECT COUNT(*) FROM interacao_substancia").fetchone()[0]
    pares = con.execute("SELECT COUNT(*) FROM (SELECT DISTINCT substancia_a_id, "
                        "substancia_b_id FROM interacao_substancia)").fetchone()[0]
    duas_fontes = con.execute(
        "SELECT COUNT(*) FROM (SELECT substancia_a_id, substancia_b_id "
        "FROM interacao_substancia GROUP BY 1,2 HAVING COUNT(DISTINCT fonte_id)>1)"
    ).fetchone()[0]
    conflitos = con.execute("SELECT COUNT(*) FROM vw_conflito_gravidade").fetchone()[0]
    sem_grav = con.execute("SELECT COUNT(*) FROM interacao_substancia "
                           "WHERE gravidade='NAO_DETERMINADA'").fetchone()[0]
    com_pt = con.execute("SELECT COUNT(*) FROM interacao_substancia "
                         "WHERE efeito_esperado IS NOT NULL").fetchone()[0]
    subs = con.execute(
        "SELECT COUNT(DISTINCT s) FROM (SELECT substancia_a_id AS s FROM "
        "interacao_substancia UNION SELECT substancia_b_id FROM "
        "interacao_substancia)").fetchone()[0]

    resumo("INTERACAO FARMACO x FARMACO", [
        ("DDInter — linhas lidas", r1["lidos"]),
        ("DDInter — inseridas agora", r1["inseridos"]),
        ("DDInter — ja existiam (carga incremental)", r1["ja_existiam"]),
        ("DDInter — por nivel", r1["por_nivel"]),
        ("db_drug — linhas lidas", r2["lidos"]),
        ("db_drug — inseridas agora", r2["inseridos"]),
        ("db_drug — ja existiam (carga incremental)", r2["ja_existiam"]),
        ("db_drug — descricoes traduzidas", r2["traduzidas"]),
        ("db_drug — por tipo", r2["por_tipo"]),
        ("nomes EN gravados como sinonimo INN", n_inn),
        ("nomes sem correspondencia BR", len(resolvedor.sem_correspondencia)),
        ("nomes ambiguos (nao resolvidos)", len(resolvedor.ambiguos)),
        ("", ""),
        ("linhas em interacao_substancia", total),
        ("pares distintos", pares),
        ("pares afirmados por DUAS fontes", duas_fontes),
        ("pares com CONFLITO de gravidade", conflitos),
        ("linhas com gravidade NAO_DETERMINADA", "%d (%.1f%%)"
         % (sem_grav, 100.0 * sem_grav / max(1, total))),
        ("linhas com efeito em portugues", "%d (%.1f%%)"
         % (com_pt, 100.0 * com_pt / max(1, total))),
        ("substancias BR com ao menos uma interacao", "%d de 2094 (%.1f%%)"
         % (subs, 100.0 * subs / 2094)),
    ])
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
