# -*- coding: utf-8 -*-
"""
ATUALIZACAO DO CONHECIMENTO — sem perder um atendimento.

O PROBLEMA
----------
O banco em uso tem duas coisas de naturezas diferentes no mesmo arquivo:
CONHECIMENTO (substancias, interacoes, regras, evidencias — igual para todo
mundo, substituivel) e ATENDIMENTO (pacientes, conciliacoes, achados,
anotacoes — do usuario, insubstituivel).

Trocar o arquivo inteiro por uma versao nova do conhecimento levaria junto os
atendimentos. Este modulo faz o contrario: parte do conhecimento NOVO e traz o
atendimento do usuario para dentro dele.

    conhecimento novo (intocado)  +  atendimento do usuario  ->  banco novo

POR QUE NAO DOIS ARQUIVOS SEPARADOS (D-051)
-------------------------------------------
Porque OITO chaves estrangeiras ligam atendimento a conhecimento — medicamento
-> substancia, alergia -> substancia, condicao -> doenca, achado -> substancia
— e o SQLite **nao aplica chave estrangeira entre arquivos diferentes**.
Separar desligaria exatamente a trava de que esta operacao mais precisa: saber
que um atendimento antigo aponta para uma substancia que a versao nova nao tem
mais. Com um arquivo so, `PRAGMA foreign_key_check` responde isso, e a
atualizacao e RECUSADA em vez de deixar o dado orfao.

A ORDEM, e cada passo existe por um motivo
------------------------------------------
  1. conferir o arquivo novo      corrompido ou incompativel para aqui
  2. fazer backup                 antes de qualquer escrita, sempre
  3. montar em arquivo TEMPORARIO o banco em uso nao e tocado enquanto isso
  4. conferir o resultado         chave estrangeira, integridade, contagens
  5. trocar                       so depois de tudo conferido

Se qualquer passo falhar, o banco em uso continua exatamente como estava.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caminhos                                            # noqa: E402
import instalacao                                          # noqa: E402
import versao as ver                                       # noqa: E402

# ORDEM IMPORTA: pai antes de filho, ou a chave estrangeira recusa a insercao.
ATENDIMENTO_EM_ORDEM = (
    "paciente",
    "atendimento",
    "atendimento_medicamento",
    "atendimento_item",
    "rotina_paciente",
    "paciente_alergia",
    "paciente_condicao",
    "paciente_habito",
    "posologia",
    "horario_administracao",
    "conciliacao",
    "conciliacao_par",
    "achado",
    "achado_evidencia",
    "nao_avaliado",
    "anotacao_profissional",
)


class ErroDeAtualizacao(RuntimeError):
    """Recusa declarada. O banco em uso nao foi tocado."""


def _abrir_ro(caminho: Path) -> sqlite3.Connection:
    return sqlite3.connect("file:%s?mode=ro" % caminho.as_posix(), uri=True)


def conferir_candidato(novo: Path) -> dict:
    """O arquivo novo serve? Levanta com o motivo quando nao."""
    if not novo.exists():
        raise ErroDeAtualizacao("Arquivo não encontrado:\n  %s" % novo)
    try:
        con = _abrir_ro(novo)
    except sqlite3.Error as exc:
        raise ErroDeAtualizacao(
            "O arquivo não é um banco SQLite legível (%s):\n  %s" % (exc, novo))
    try:
        try:
            integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise ErroDeAtualizacao(
                "O arquivo está corrompido ou não é um banco (%s):\n  %s"
                % (exc, novo))
        if integridade != "ok":
            raise ErroDeAtualizacao(
                "O arquivo está corrompido (integrity_check: %s)." % integridade)
        tabelas = {n for (n,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        faltando = [t for t in instalacao.ESSENCIAIS if t not in tabelas]
        if faltando:
            raise ErroDeAtualizacao(
                "O arquivo não é um conhecimento do Conciliador: faltam as "
                "tabelas %s." % ", ".join(faltando))
        for t in ATENDIMENTO_EM_ORDEM:
            if t not in tabelas:
                raise ErroDeAtualizacao(
                    "O arquivo não tem a tabela de atendimento %r. Ele não "
                    "pode receber os seus atendimentos." % t)
        prop = dict(con.execute("SELECT chave, valor FROM propriedade")) \
            if "propriedade" in tabelas else {}
        esquema = prop.get("esquema.versao")
        if esquema is None:
            raise ErroDeAtualizacao(
                "O arquivo não declara a versão do esquema. Sem isso não há "
                "como saber se ele é compatível com este programa.")
        if esquema != ver.ESQUEMA:
            raise ErroDeAtualizacao(
                "Versão de esquema incompatível.\n"
                "  este programa espera: %s\n  o arquivo declara:    %s\n\n"
                "Atualize o programa antes de atualizar o conhecimento."
                % (ver.ESQUEMA, esquema))
        n_atend = con.execute("SELECT COUNT(*) FROM atendimento").fetchone()[0]
        if n_atend:
            raise ErroDeAtualizacao(
                "O arquivo contém %d atendimento(s). Um conhecimento para "
                "distribuição não pode trazer dados de paciente." % n_atend)
        ativos = con.execute(
            "SELECT COUNT(*) FROM modelo WHERE ativo=1").fetchone()[0] \
            if "modelo" in tabelas else 0
        return {
            "versao": prop.get("conhecimento.versao"),
            "digital": prop.get("conhecimento.digital"),
            "esquema": esquema,
            "substancias": con.execute(
                "SELECT COUNT(*) FROM substancia").fetchone()[0],
            "interacoes": con.execute(
                "SELECT COUNT(*) FROM interacao_substancia").fetchone()[0],
            "modelos_ativos": ativos,
        }
    finally:
        con.close()


def fazer_backup(banco: Path) -> Path:
    pasta = caminhos.backups()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / ("conciliador_%s.db"
                       % datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(banco, destino)
    return destino


def atualizar(novo: Path, verboso: bool = True) -> dict:
    banco = caminhos.banco()
    if not banco.exists():
        raise ErroDeAtualizacao(
            "Não há banco em uso para atualizar. Abra o programa uma vez "
            "antes.")

    info_novo = conferir_candidato(novo)
    antes = instalacao.conferir_banco(banco)
    if verboso:
        print("conhecimento em uso: versão %s · digital %s · %d atendimento(s)"
              % (antes.get("conhecimento_versao"),
                 antes.get("conhecimento_digital"), antes["atendimentos"]))
        print("conhecimento novo:   versão %s · digital %s"
              % (info_novo["versao"], info_novo["digital"]))

    backup = fazer_backup(banco)
    if verboso:
        print("backup: %s" % backup)

    temporario = banco.with_suffix(".novo.tmp")
    if temporario.exists():
        temporario.unlink()
    shutil.copy2(novo, temporario)

    movidas = {}
    con = None
    montado = False
    try:
        con = sqlite3.connect(temporario)
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("ATTACH DATABASE ? AS usuario", (str(banco),))
        try:
            con.execute("BEGIN")
            for t in ATENDIMENTO_EM_ORDEM:
                n = con.execute(
                    "SELECT COUNT(*) FROM usuario.%s" % t).fetchone()[0]
                if n:
                    con.execute(
                        "INSERT INTO main.%s SELECT * FROM usuario.%s" % (t, t))
                movidas[t] = n
            con.execute("COMMIT")
        finally:
            con.execute("DETACH DATABASE usuario")

        # ---- passo 4: conferir ANTES de trocar
        con.execute("PRAGMA foreign_keys = ON")
        quebradas = con.execute("PRAGMA foreign_key_check").fetchall()
        if quebradas:
            alvos = sorted({q[0] for q in quebradas})
            raise ErroDeAtualizacao(
                "ATUALIZAÇÃO RECUSADA — %d referência(s) quebrariam.\n\n"
                "Os seus atendimentos apontam para dados de conhecimento que "
                "a versão nova não tem mais (tabelas: %s).\n\n"
                "Nada foi alterado. O banco em uso continua como estava."
                % (len(quebradas), ", ".join(alvos)))
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ErroDeAtualizacao(
                "O banco montado não passou no teste de integridade. "
                "Nada foi alterado.")
        for t in ATENDIMENTO_EM_ORDEM:
            n = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
            if n != movidas[t]:
                raise ErroDeAtualizacao(
                    "Perda de dados detectada em %r: %d linha(s) na origem, "
                    "%d no resultado. Nada foi alterado."
                    % (t, movidas[t], n))
        depois_sub = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
        montado = True
    finally:
        # FECHAR ANTES DE APAGAR. No Windows um arquivo aberto nao pode ser
        # removido: a primeira versao deste bloco tentava apagar o temporario
        # com a conexao ainda aberta, o `unlink` levantava PermissionError — e
        # esse erro SUBSTITUIA a recusa. O usuario via um rastreamento de pilha
        # no lugar de "ATUALIZACAO RECUSADA, nada foi alterado", que e
        # exatamente a mensagem que ele precisava ler.
        if con is not None:
            try:
                con.close()
            except sqlite3.Error:
                pass
        if not montado and temporario.exists():
            try:
                temporario.unlink()
            except OSError:
                pass

    # ---- passo 5: trocar. O anterior vira `.anterior` antes de sumir, para
    # que uma falha entre as duas operacoes nao deixe o usuario sem banco.
    anterior = banco.with_suffix(".anterior.tmp")
    if anterior.exists():
        anterior.unlink()
    banco.rename(anterior)
    try:
        temporario.rename(banco)
    except OSError:
        anterior.rename(banco)
        raise ErroDeAtualizacao(
            "Não foi possível substituir o banco. O anterior foi restaurado.")
    anterior.unlink()

    resultado = {
        "backup": str(backup),
        "versao_anterior": antes.get("conhecimento_versao"),
        "versao_nova": info_novo["versao"],
        "digital_nova": info_novo["digital"],
        "substancias": depois_sub,
        "atendimentos_preservados": movidas["atendimento"],
        "pacientes_preservados": movidas["paciente"],
        "achados_preservados": movidas["achado"],
        "linhas_de_atendimento": sum(movidas.values()),
    }
    if verboso:
        print("\nATUALIZACAO CONCLUIDA")
        for k, v in resultado.items():
            print("  %-26s %s" % (k, v))
    return resultado


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python app/atualizacao.py <conhecimento.db>")
        sys.exit(2)
    try:
        atualizar(Path(sys.argv[1]).resolve())
    except (ErroDeAtualizacao, instalacao.ErroDeInstalacao) as exc:
        print("\n%s" % exc)
        sys.exit(1)
