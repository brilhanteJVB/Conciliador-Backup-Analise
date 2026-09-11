# -*- coding: utf-8 -*-
"""
Infraestrutura comum do pipeline: caminhos, conexao, leitura de CSV do
acervo e registro de carga/evidencia.

REGRA: o acervo e SOMENTE LEITURA. Nada aqui abre a origem para escrita.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

ACERVO = Path(r"C:\Conteudos banco de dados tcc")
RAIZ = Path(__file__).resolve().parent.parent
BANCO = RAIZ / "database" / "conciliador.db"
SCHEMA = RAIZ / "database" / "schema.sql"
RAW = RAIZ / "data" / "raw"

csv.field_size_limit(10 * 1024 * 1024)

# Encodings e cabecalhos irregulares medidos na auditoria (docs/auditoria §3).
# Guardados aqui para que nenhum script precise redescobri-los.
LEITURA = {
    "TA_CONSULTA_MEDICAMENTOS.CSV": dict(enc="iso-8859-1", delim=";", pular=0),
    "fontes_novas/02_cmed_precos_drogaria/TA_PRECO_MEDICAMENTO.csv":
        dict(enc="utf-8-sig", delim=";", pular=41),      # banner institucional
    "fontes_novas/02_cmed_precos_drogaria/TA_PRECOS_MEDICAMENTOS.csv":
        dict(enc="windows-1252", delim=";", pular=0),
    "fontes_novas/03_dcb_denominacoes/chave_substancia_br.csv":
        dict(enc="utf-8-sig", delim=",", pular=0),
    "fontes_novas/05_atc_classes/WHO_ATC-DDD_2026-04-25.csv":
        dict(enc="utf-8-sig", delim=",", pular=0),
    "fontes_novas/07_complementares/DADOS_ABERTOS_MEDICAMENTOS.csv":
        dict(enc="iso-8859-1", delim=";", pular=0),
    "fontes_novas/07_fda_ddi/fda_index_cyp.csv":
        dict(enc="utf-8-sig", delim=",", pular=0),
    # DDInter: oito arquivos, um por grupo anatomico ATC. Mesmo perfil.
    "DDInter/ddinter_downloads_code_A.csv": dict(enc="utf-8-sig", delim=",", pular=0),
    "DDInter/ddinter_downloads_code_B.csv": dict(enc="utf-8-sig", delim=",", pular=0),
    "DDInter/ddinter_downloads_code_D.csv": dict(enc="utf-8-sig", delim=",", pular=0),
    "DDInter/ddinter_downloads_code_H.csv": dict(enc="utf-8-sig", delim=",", pular=0),
    "DDInter/ddinter_downloads_code_L.csv": dict(enc="utf-8-sig", delim=",", pular=0),
    "DDInter/ddinter_downloads_code_P.csv": dict(enc="utf-8-sig", delim=",", pular=0),
    "DDInter/ddinter_downloads_code_R.csv": dict(enc="utf-8-sig", delim=",", pular=0),
    "DDInter/ddinter_downloads_code_V.csv": dict(enc="utf-8-sig", delim=",", pular=0),
    "db_drug_interactions.csv": dict(enc="utf-8", delim=",", pular=0),
}


def ler_csv(rel: str):
    """Itera dicts de um CSV do acervo, usando o perfil medido na auditoria.

    Devolve (indice_por_nome, lista_de_celulas) por linha para nao depender
    de DictReader quando ha cabecalho repetido ou irregular.
    """
    perfil = LEITURA.get(rel)
    caminho = ACERVO / rel
    if perfil is None:
        raise KeyError(
            "perfil de leitura nao registrado para %r. Acrescente em "
            "LEITURA com encoding, delimitador e linhas a pular, conforme "
            "auditoria/saida/inventario_bruto.json." % rel)
    with open(caminho, "r", encoding=perfil["enc"], errors="strict",
              newline="") as fh:
        leitor = csv.reader(fh, delimiter=perfil["delim"])
        for _ in range(perfil["pular"]):
            next(leitor, None)
        cab = next(leitor, None)
        if cab is None:
            return
        idx = {c.strip(): i for i, c in enumerate(cab)}
        for linha in leitor:
            if linha and any(str(c).strip() for c in linha):
                yield idx, linha


def campo(idx, linha, nome, padrao=""):
    i = idx.get(nome)
    if i is None or i >= len(linha):
        return padrao
    v = (linha[i] or "").strip()
    # '-' e o marcador de ausente da CMED (50.217 ocorrencias em EAN)
    return padrao if v in ("", "-", "NULL", "N/A") else v


def hash_arquivo(rel: str, limite=8 * 1024 * 1024) -> str:
    """Hash do conteudo: detecta troca silenciosa da origem.

    Uma fonte pode ser um DIRETORIO (as 150 bulas sao 150 arquivos). Nesse
    caso o hash e da lista ordenada de nome+tamanho, que muda se algum
    arquivo for acrescentado, removido ou alterado.
    """
    caminho = ACERVO / rel
    h = hashlib.sha256()
    if caminho.is_dir():
        for f in sorted(caminho.iterdir()):
            if f.is_file():
                h.update(("%s:%d;" % (f.name, f.stat().st_size)).encode())
        return h.hexdigest()[:24]
    h.update(str(caminho.stat().st_size).encode())
    with open(caminho, "rb") as fh:
        h.update(fh.read(limite))
    return h.hexdigest()[:24]


def chaves_candidatas(nome: str) -> list:
    """Esqueletos alternativos para casar nome estrangeiro com substancia BR.

    O ingles usa a forma acida onde o Brasil registra o sal:
    'alendronic acid' (EN) e 'alendronato de sodio' (BR) sao a mesma
    molecula, mas o esqueleto sai 'akid alendronik' contra 'alendronat'.
    Aqui geramos o candidato '-ate' alem do direto. Nao altera o esqueleto
    canonico: apenas amplia a busca.
    """
    from normalizacao import skeleton
    saida, vistos = [], set()

    def junta(n):
        if not n:
            return
        e = skeleton(n)
        if e and len(e) >= 3 and e not in vistos:
            vistos.add(e)
            saida.append(e)

    junta(nome)
    m = re.match(r"^(.*?)ic\s+acid$", (nome or "").strip(), re.I)
    if m and m.group(1):
        junta(m.group(1) + "ate")
    return saida


def conectar(criar=False) -> sqlite3.Connection:
    if criar and BANCO.exists():
        BANCO.unlink()
    novo = not BANCO.exists()
    BANCO.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BANCO)
    con.execute("PRAGMA foreign_keys = ON")
    if novo:
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        con.commit()
    return con


def id_fonte(con, nome: str) -> int:
    r = con.execute("SELECT id FROM fonte WHERE nome = ?", (nome,)).fetchone()
    if r is None:
        raise LookupError("fonte %r nao registrada. Rode pipeline/10_fontes.py" % nome)
    return r[0]


class OrigemAlterada(RuntimeError):
    """O arquivo do acervo mudou desde a carga anterior."""


def abrir_carga(con, fonte: str, script: str, documento: str, versao=None) -> int:
    """Registra o LOTE de carga e devolve seu id (P-02).

    `carga` e o LOTE de dados, nao o log de execucoes. A identidade do lote e
    (fonte, script, documento, hash do arquivo): enquanto a origem nao muda, e
    o mesmo lote, e reexecutar o pipeline nao cria lote novo. Sem isso, cada
    execucao acrescentava 11 linhas de `carga` que nao correspondiam a dado
    nenhum, e a impressao digital do banco (usada pela Fase 7 para dizer que um
    experimento e reproduzivel) mudava sem um unico dado ter mudado.

    Se o arquivo MUDOU, a carga incremental para e exige `--recriar`. Isso e
    deliberado: reconciliar origem alterada exigiria tratar remocao, renomeacao
    e renormalizacao de chave, e fazer isso pela metade e como dado errado
    entra em silencio. O hash existe justamente para dar esse aviso. Ver D-045.
    """
    fid = id_fonte(con, fonte)
    h = hash_arquivo(documento) if (ACERVO / documento).exists() else None
    r = con.execute(
        "SELECT id, hash_arquivo FROM carga WHERE fonte_id=? AND script=? "
        "AND documento_origem=? ORDER BY id DESC LIMIT 1",
        (fid, script, documento)).fetchone()
    if r is not None:
        if r[1] == h:
            return r[0]
        raise OrigemAlterada(
            "o arquivo %r mudou desde a carga anterior (hash %s -> %s).\n"
            "A carga incremental nao reconcilia origem alterada — ela so sabe "
            "nao repetir o que ja entrou.\nRode com --recriar para reconstruir "
            "o banco a partir da origem nova." % (documento, r[1], h))
    cur = con.execute(
        "INSERT INTO carga (fonte_id, script, documento_origem, versao, hash_arquivo) "
        "VALUES (?,?,?,?,?)", (fid, script, documento, versao, h))
    con.commit()
    return cur.lastrowid


def fechar_carga(con, carga_id: int, lidos: int, inseridos: int,
                 ignorados: int, observacao=None) -> None:
    """Fecha o lote — e SO o lote que ainda esta aberto.

    Numa reexecucao o lote ja foi fechado com os numeros da carga de verdade.
    Sobrescreve-los com os zeros de uma passada que nao inseriu nada apagaria
    a resposta de "quantas linhas entraram deste arquivo", que e a razao de a
    tabela existir.
    """
    con.execute(
        "UPDATE carga SET registros_lidos=?, registros_inseridos=?, "
        "registros_ignorados=?, observacao=? "
        "WHERE id=? AND registros_lidos IS NULL",
        (lidos, inseridos, ignorados, observacao, carga_id))
    con.commit()


def inserir_unico(con, tabela: str, dados: dict, onde: str, params_onde):
    """INSERT OR IGNORE e devolve (id, inserido_agora).

    Existe porque `cur.lastrowid` depois de um INSERT OR IGNORE que IGNOROU
    devolve o id da insercao anterior — silenciosamente errado. Varios ETLs se
    protegiam com `if cur.rowcount:`, o que evita o id errado mas tambem pula
    tudo o que vem depois; quando o id e necessario (evidencia, vinculo), a
    unica saida correta e reler a linha que ja existe.

    `tabela` e `onde` sao literais escritos aqui no repositorio, nunca entrada
    de usuario.
    """
    cols = list(dados)
    cur = con.execute(
        "INSERT OR IGNORE INTO %s (%s) VALUES (%s)"
        % (tabela, ",".join(cols), ",".join("?" * len(cols))),
        [dados[c] for c in cols])
    if cur.rowcount:
        return cur.lastrowid, True
    r = con.execute("SELECT id FROM %s WHERE %s" % (tabela, onde),
                    params_onde).fetchone()
    if r is None:
        raise RuntimeError(
            "INSERT em %s foi ignorado mas a linha nao foi encontrada por %r. "
            "A clausula de recuperacao nao corresponde ao UNIQUE da tabela."
            % (tabela, onde))
    return r[0], False


def registrar_evidencia(con, tabela: str, id_alvo: int, fonte_id: int,
                        carga_id: int, documento: str,
                        nivel="NAO_AVALIADA", metodo="CARGA_DIRETA",
                        trecho=None) -> None:
    con.execute(
        "INSERT OR IGNORE INTO evidencia (tabela_alvo,id_alvo,fonte_id,carga_id,"
        "documento,trecho,nivel_evidencia,metodo_extracao) VALUES (?,?,?,?,?,?,?,?)",
        (tabela, id_alvo, fonte_id, carga_id, documento, trecho, nivel, metodo))


def resumo(titulo: str, pares) -> None:
    print("\n" + titulo)
    for k, v in pares:
        print("  %-44s %s" % (k, v))
