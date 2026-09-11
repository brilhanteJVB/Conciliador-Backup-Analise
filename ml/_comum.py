# -*- coding: utf-8 -*-
"""
Infraestrutura comum da camada de Machine Learning.

REGRAS QUE ESTE ARQUIVO EXISTE PARA SUSTENTAR
---------------------------------------------
1. Reprodutibilidade. SEMENTE e uma constante, nao um argumento opcional.
   Todo sorteio da fase passa por `rng()`.
2. Par canonico. O esquema exige `substancia_a_id < substancia_b_id`; aqui
   isso e uma funcao unica (`par`), para que nenhum script reinvente a ordem.
3. Versao do dado. `versao_dados()` devolve uma impressao digital do banco
   (contagens + hash das cargas). Sem ela, um resultado nao e reproduzivel:
   nao se sabe sobre qual banco foi medido.
4. Saida em disco. Toda medicao vira JSON em `ml/saida/`, para que a
   verificacao independente (92) leia o numero em vez de recalcula-lo por
   dentro do mesmo processo.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
BANCO = RAIZ / "database" / "conciliador.db"
SAIDA = RAIZ / "ml" / "saida"
TREINO = RAIZ / "data" / "training"
MODELOS = RAIZ / "models"

# A semente da fase. Trocar este numero muda todo resultado publicado.
SEMENTE = 20260909


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(BANCO)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def rng(desvio: int = 0) -> np.random.Generator:
    """Gerador com semente fixa. `desvio` separa sorteios independentes."""
    return np.random.default_rng(SEMENTE + desvio)


def par(a: int, b: int) -> tuple[int, int]:
    """Par canonico. Interacao farmaco x farmaco e simetrica (ver doc §6)."""
    return (a, b) if a < b else (b, a)


def versao_dados(con: sqlite3.Connection) -> dict:
    """Impressao digital do banco: o que identifica ESTE dataset.

    Nao e o hash do arquivo .db (que muda a cada atendimento gravado, e o
    atendimento nao faz parte do dataset). Sao as contagens das tabelas de
    conhecimento mais o hash dos arquivos de origem registrados em `carga`.

    A DATA DA IMPORTACAO FICA DE FORA de proposito. Reconstruir o banco a
    partir das mesmas fontes tem de devolver a MESMA impressao digital — e e
    isso que torna um resultado reproduzivel. Se a data entrasse, todo
    `--recriar` invalidaria a rastreabilidade de todo experimento anterior
    sem que uma linha de dado tivesse mudado.
    """
    tabelas = ["substancia", "classe_atc", "interacao_substancia",
               "papel_farmacocinetico", "interacao_doenca", "interacao_item",
               "interacao_habito", "regra_administracao", "anotacao_profissional"]
    contagens = {t: con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                 for t in tabelas}
    # CONTAGEM NAO BASTA. A cobertura de ATC mudou de 1.153 para 1.159 sem
    # que nenhuma contagem se mexesse — `substancia` continuava com 2.094
    # linhas, so que 6 delas ganharam `atc_codigo` numa segunda passada do
    # pipeline (defeito corrigido pelo passo 68). A impressao digital nao viu,
    # e um experimento deixou de ser reproduzivel em silencio. Agora ela inclui
    # o CONTEUDO das colunas que viram atributo de ML.
    colunas = con.execute(
        "SELECT COUNT(atc_codigo), COUNT(canal_dispensacao), COUNT(cas), "
        "COUNT(dcb_numero), SUM(n_produtos_ativos) FROM substancia").fetchone()
    perfil = con.execute(
        "SELECT tipo, COUNT(*) FROM regra_administracao GROUP BY 1 ORDER BY 1"
    ).fetchall()
    pk = con.execute(
        "SELECT sistema, papel, COUNT(*) FROM papel_farmacocinetico "
        "GROUP BY 1,2 ORDER BY 1,2").fetchall()
    contagens["_colunas_substancia"] = list(colunas)
    contagens["_perfil_regra_administracao"] = perfil
    contagens["_perfil_papel_pk"] = pk
    # A impressao digital identifica QUAIS arquivos, com qual conteudo,
    # formaram este banco — nao quantas vezes o pipeline rodou. A deduplicacao
    # e feita em Python, preservando a ordem de `id`: usar SELECT DISTINCT
    # exigiria trocar o ORDER BY e isso mudaria o hash de todo experimento ja
    # publicado sem um unico dado ter mudado.
    cargas, vistas = [], set()
    for linha in con.execute(
            "SELECT script, documento_origem, hash_arquivo "
            "FROM carga ORDER BY id"):
        if linha not in vistas:
            vistas.add(linha)
            cargas.append(linha)
    bruto = json.dumps({"contagens": contagens, "cargas": cargas},
                       sort_keys=True, ensure_ascii=False)
    return {
        "contagens": contagens,
        "n_cargas": len(cargas),
        "impressao": hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16],
    }


def gravar(nome: str, dados: dict) -> Path:
    SAIDA.mkdir(parents=True, exist_ok=True)
    caminho = SAIDA / nome
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2,
                                  default=_serializavel),
                       encoding="utf-8")
    return caminho


def ler(nome: str) -> dict:
    return json.loads((SAIDA / nome).read_text(encoding="utf-8"))


def carregar_predizer():
    """Importa `ml/70_predizer.py`, cujo nome comeca por digito.

    O modulo PRECISA entrar em `sys.modules` antes de ser executado: com
    `from __future__ import annotations`, o decorador `@dataclass` resolve as
    anotacoes procurando o proprio modulo pelo nome, e falha se ele nao
    estiver registrado. Isso ja custou um erro obscuro; fica numa funcao so.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "predizer", RAIZ / "ml" / "70_predizer.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _serializavel(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o))


# ---------------------------------------------------------------- relatorio

def titulo(texto: str) -> None:
    print("\n" + "=" * 74)
    print(texto)
    print("=" * 74)


def secao(texto: str) -> None:
    print("\n--- %s" % texto)


def linha(rotulo: str, valor, nota: str = "") -> None:
    v = "{:,}".format(valor).replace(",", ".") if isinstance(valor, int) else valor
    print("  %-52s %14s %s" % (rotulo, v, nota))


def pct(n: int, total: int) -> str:
    return "0,0%" if not total else ("%.1f%%" % (100.0 * n / total)).replace(".", ",")


if __name__ == "__main__":
    con = conectar()
    v = versao_dados(con)
    titulo("VERSAO DOS DADOS")
    for k, n in v["contagens"].items():
        linha(k, n)
    linha("cargas registradas", v["n_cargas"])
    linha("impressao digital", v["impressao"])
    linha("semente da fase", SEMENTE)
    print()
    sys.exit(0)
