# -*- coding: utf-8 -*-
"""
PREPARA O CONHECIMENTO QUE VAI DENTRO DO PROGRAMA.

Produz `conhecimento/conhecimento.db` — o banco que acompanha o `.exe` e vira,
na primeira execucao, o banco do usuario. E o banco de desenvolvimento com as
16 tabelas de ATENDIMENTO esvaziadas.

POR QUE ESVAZIAR EM VEZ DE APAGAR AS TABELAS
--------------------------------------------
As tabelas de atendimento ficam, vazias. O arquivo entregue e um banco
COMPLETO: copiado para a pasta do usuario, ja aceita o primeiro atendimento
sem migracao nenhuma. Apagar as tabelas obrigaria o programa a recria-las na
primeira execucao, e uma criacao de esquema no arranque e exatamente o tipo de
passo que falha em campo, na maquina de alguem, sem ninguem por perto.

POR QUE UM ARQUIVO SO, E NAO DOIS
---------------------------------
Oito chaves estrangeiras ligam atendimento a conhecimento (medicamento →
substancia, alergia → substancia, condicao → doenca, achado → substancia...) e
o SQLite **nao aplica chave estrangeira entre arquivos diferentes**. Separar em
`conhecimento.db` + `atendimentos.db` desligaria justamente a protecao de que
a atualizacao do conhecimento mais precisa: descobrir que um atendimento antigo
aponta para uma substancia que a versao nova nao tem mais. Ver D-051.

A separacao existe — mas no momento da ATUALIZACAO, feita por
`scripts/atualizar_conhecimento.py`, e nao no disco.

Uso: python scripts/preparar_conhecimento.py [--saida PASTA]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

ORIGEM = RAIZ / "database" / "conciliador.db"

# As 16 tabelas do atendimento. A mesma lista de `tests/fase9_convergencia.py`
# e de `scripts/atualizar_conhecimento.py` — se divergirem, o backup de um
# lado apaga o dado do outro, por isso ela e conferida por teste.
ATENDIMENTO = (
    "paciente", "atendimento", "atendimento_medicamento", "atendimento_item",
    "posologia", "horario_administracao", "rotina_paciente",
    "paciente_alergia", "paciente_condicao", "paciente_habito",
    "conciliacao", "conciliacao_par", "achado", "achado_evidencia",
    "nao_avaliado", "anotacao_profissional",
)


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def main() -> int:
    saida = RAIZ / "conhecimento"
    if "--saida" in sys.argv:
        saida = Path(sys.argv[sys.argv.index("--saida") + 1]).resolve()
    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / "conhecimento.db"

    print("=" * 74)
    print("PREPARANDO O CONHECIMENTO PARA DISTRIBUICAO")
    print("=" * 74)
    if not ORIGEM.exists():
        print("banco de origem ausente: %s" % ORIGEM)
        return 1

    print("origem:  %s (%.1f MB)" % (ORIGEM, ORIGEM.stat().st_size / 1024 ** 2))
    if destino.exists():
        destino.unlink()
    shutil.copy2(ORIGEM, destino)

    con = sqlite3.connect(destino)
    con.execute("PRAGMA foreign_keys = OFF")     # apagando na ordem inversa
    try:
        tabelas = {n for (n,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        faltando = [t for t in ATENDIMENTO if t not in tabelas]
        if faltando:
            print("ERRO: tabelas de atendimento ausentes no esquema: %s"
                  % faltando)
            return 1

        apagadas = {}
        for t in reversed(ATENDIMENTO):
            n = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            if n:
                con.execute("DELETE FROM %s" % t)
            apagadas[t] = n
        con.execute("DELETE FROM sqlite_sequence") if con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'"
        ).fetchone() else None
        con.commit()

        # Conferencia OBRIGATORIA antes de seguir: o conhecimento nao pode ter
        # sido tocado. Comparado contra a origem, tabela por tabela.
        orig = sqlite3.connect("file:%s?mode=ro" % ORIGEM.as_posix(), uri=True)
        try:
            divergentes = []
            for t in sorted(tabelas):
                if t in ATENDIMENTO or t.startswith("sqlite_"):
                    continue
                a = orig.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                b = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                if a != b:
                    divergentes.append((t, a, b))
        finally:
            orig.close()
        if divergentes:
            print("ERRO: esvaziar o atendimento mexeu no conhecimento: %s"
                  % divergentes)
            return 1

        # MODO DE DIARIO: DELETE, nao WAL. Tres motivos, todos praticos.
        #
        # 1. Um banco WAL precisa de `-wal` e `-shm` AO LADO. O pacote levava
        #    os tres arquivos, e a V2 da Fase 10 flagrou o `-shm` sendo
        #    recriado dentro da pasta do programa a cada execucao.
        # 2. Numa instalacao em pasta somente leitura, abrir um banco WAL —
        #    mesmo so para ler — tenta criar o `-shm` e pode FALHAR.
        # 3. O guia de instalacao manda copiar UM arquivo para fazer backup.
        #    Em WAL isso e incorreto: as transacoes recentes estao no `-wal`,
        #    e a copia sairia incompleta. Em DELETE, um arquivo e o banco
        #    inteiro — a instrucao passa a ser verdadeira.
        con.execute("PRAGMA journal_mode = DELETE")
        con.execute("PRAGMA foreign_keys = ON")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            print("ERRO: %d violação(ões) de chave estrangeira no resultado"
                  % len(fk))
            return 1
        con.commit()
        con.execute("VACUUM")
        con.commit()

        prop = dict(con.execute("SELECT chave, valor FROM propriedade")) \
            if "propriedade" in tabelas else {}
        resumo = {t: con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                  for t in ("substancia", "produto", "apresentacao",
                            "classe_atc", "interacao_substancia",
                            "regra_administracao", "interacao_doenca",
                            "evidencia", "modelo", "predicao")}
        ativos = con.execute("SELECT COUNT(*) FROM modelo WHERE ativo=1"
                             ).fetchone()[0]
        integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
        diario = con.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        con.close()

    # Nenhum resto de WAL pode viajar no pacote.
    for resto in (destino.with_name(destino.name + "-wal"),
                  destino.with_name(destino.name + "-shm")):
        if resto.exists():
            resto.unlink()

    digest = sha256(destino)
    manifesto = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivo": destino.name,
        "bytes": destino.stat().st_size,
        "sha256": digest,
        "conhecimento_versao": prop.get("conhecimento.versao"),
        "conhecimento_digital": prop.get("conhecimento.digital"),
        "esquema_versao": prop.get("esquema.versao"),
        "conteudo": resumo,
        "modelos_ativos": ativos,
        "integridade": integridade,
        "journal_mode": diario,
        "tabelas_de_atendimento_esvaziadas": list(ATENDIMENTO),
        "declaracao": "Conhecimento para distribuição. As tabelas de "
                      "atendimento existem e estão vazias. Nenhum modelo "
                      "está ativo.",
    }
    (saida / "conhecimento.json").write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\ndestino: %s (%.1f MB)" % (destino, destino.stat().st_size / 1024 ** 2))
    print("sha256:  %s" % digest)
    print("versão:  %s · digital %s"
          % (prop.get("conhecimento.versao"), prop.get("conhecimento.digital")))
    print("\nconteúdo preservado:")
    for k, v in resumo.items():
        print("  %-24s %s" % (k, v))
    print("\nlinhas de atendimento removidas: %d"
          % sum(v for v in apagadas.values()))
    print("modelos ativos: %d · integridade: %s · diário: %s"
          % (ativos, integridade, diario))
    if diario.lower() != "delete":
        print("\nERRO: o banco distribuído ficou em modo %r. Em WAL ele "
              "precisa de arquivos vizinhos, e a instrução de backup do guia "
              "(copiar um arquivo) deixaria de ser verdadeira." % diario)
        return 1
    if ativos:
        print("\nERRO: o conhecimento distribuído tem modelo ATIVO. O `.exe` "
              "sairia prevendo — e a Fase 7 decidiu o contrário.")
        return 1
    print("\nCONHECIMENTO PRONTO PARA DISTRIBUICAO.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
