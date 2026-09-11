# -*- coding: utf-8 -*-
"""
CARIMBO DE IDENTIDADE DO CONHECIMENTO.

Grava em `propriedade` a versao, a impressao digital e a data do conhecimento
que acabou de ser carregado. Sem isto um arquivo `.db` distribuido e anonimo:
nao da para dizer de qual carga ele veio, e um alerta ja mostrado ao
farmaceutico nao pode mais ser atribuido a versao do conhecimento que o
produziu.

A IMPRESSAO DIGITAL E A MESMA DO ML, de proposito. `ml/_comum.versao_dados`
ja resolve o problema dificil — identificar o CONTEUDO do banco sem depender
da data de importacao nem do hash do arquivo `.db`, que muda a cada
atendimento gravado. Reimplementar aqui produziria dois numeros que
divergiriam no primeiro detalhe, e a rastreabilidade do modelo depende de eles
serem o mesmo numero.

Se `ml/` nao puder ser importado (numpy ausente, por exemplo), o passo grava
a versao e a data assim mesmo e DECLARA que a impressao digital ficou de fora,
em vez de inventar um valor.

Uso: python pipeline/80_identidade.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import conectar, resumo                        # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def impressao_digital(con) -> tuple[str, str]:
    """(valor, observacao). Importa `ml/` so aqui dentro: o pipeline nao pode
    depender de numpy para carregar dado."""
    # `import _comum` devolveria o modulo do PIPELINE, que ja esta carregado e
    # nao tem `versao_dados` — os dois arquivos se chamam `_comum.py`. Por isso
    # o de `ml/` e carregado por caminho, sob outro nome.
    try:
        import importlib.util as _iu
        spec = _iu.spec_from_file_location("_ml_comum", RAIZ / "ml" / "_comum.py")
        mlc = _iu.module_from_spec(spec)
        sys.modules["_ml_comum"] = mlc
        spec.loader.exec_module(mlc)
        return mlc.versao_dados(con)["impressao"], "ml/_comum.versao_dados"
    except Exception as exc:                                # noqa: BLE001
        return "", "NAO CALCULADA (%s: %s)" % (type(exc).__name__, exc)


def gravar(con, chave: str, valor: str) -> None:
    con.execute(
        "INSERT INTO propriedade (chave, valor, atualizado_em) "
        "VALUES (?,?,datetime('now')) "
        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, "
        "atualizado_em=excluded.atualizado_em", (chave, valor))


def main() -> int:
    con = conectar()
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                       "AND name='propriedade'").fetchone():
        print("A tabela `propriedade` nao existe neste banco. Ela entrou no "
              "esquema na Fase 10 — reconstrua com --recriar, ou aplique\n"
              "  CREATE TABLE propriedade (chave TEXT PRIMARY KEY, "
              "valor TEXT NOT NULL,\n"
              "    atualizado_em TEXT NOT NULL DEFAULT (datetime('now')));")
        con.close()
        return 1

    sys.path.insert(0, str(RAIZ / "app"))
    try:
        import versao as v
        esquema = v.ESQUEMA
    except Exception:                                       # noqa: BLE001
        esquema = "1.0"

    agora = datetime.now()
    digital, origem = impressao_digital(con)
    gravar(con, "conhecimento.versao", agora.strftime("%Y.%m.%d"))
    gravar(con, "conhecimento.gerado_em", agora.isoformat(timespec="seconds"))
    gravar(con, "esquema.versao", esquema)
    if digital:
        gravar(con, "conhecimento.digital", digital)
    con.commit()

    n_sub = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
    n_int = con.execute("SELECT COUNT(*) FROM interacao_substancia").fetchone()[0]
    con.close()

    resumo("IDENTIDADE DO CONHECIMENTO", [
        ("versao", agora.strftime("%Y.%m.%d")),
        ("impressao digital", digital or "NAO CALCULADA"),
        ("origem da impressao", origem),
        ("versao do esquema", esquema),
        ("substancias", n_sub),
        ("interacoes farmaco x farmaco", n_int),
        ("idempotente", "sim — reescreve as mesmas quatro chaves"),
    ])
    return 0


if __name__ == "__main__":
    sys.exit(main())
