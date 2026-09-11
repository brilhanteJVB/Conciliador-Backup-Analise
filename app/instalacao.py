# -*- coding: utf-8 -*-
"""
PRIMEIRA EXECUCAO, SEGREDO DA SESSAO E DIAGNOSTICO DE PARTIDA.

O QUE ACONTECE QUANDO O PROGRAMA ABRE
-------------------------------------
1. A pasta de dados do usuario e criada, se nao existir, e a escrita e testada
   DE VERDADE — criando e apagando um arquivo. `os.access(W_OK)` mente no
   Windows: devolve verdadeiro para pastas barradas por ACL.
2. Se nao houver banco, o conhecimento que veio com o programa
   (`conhecimento/conhecimento.db`) e COPIADO para la. E copia, nunca uso
   direto: o banco em uso precisa gravar atendimento, e o que veio com o
   programa e somente leitura.
3. O banco e conferido: existe, abre, tem as tabelas, passa no
   `integrity_check`.

O QUE ESTE MODULO NUNCA FAZ
---------------------------
  - NAO sobrescreve um banco existente. Nunca. Se ha banco, ha atendimento
    dentro dele, e atendimento e do usuario. Atualizar conhecimento e outra
    operacao, deliberada, com backup — `scripts/atualizar_conhecimento.py`.
  - NAO cria dado clinico para preencher ausencia. Banco faltando e erro
    declarado, nao motivo para inventar um banco vazio que pareceria
    funcionar e responderia "nenhuma interacao conhecida" para tudo.
  - NAO ativa modelo. O `.exe` sai com ML desligado, como a Fase 7 decidiu.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caminhos                                            # noqa: E402

# Tabelas sem as quais o banco nao e o banco deste sistema.
ESSENCIAIS = ("substancia", "interacao_substancia", "regra_administracao",
              "fonte", "evidencia", "atendimento", "achado")


class ErroDeInstalacao(RuntimeError):
    """Impede o programa de subir, com uma mensagem que o usuario entende."""


# ===================================================================== segredo
def segredo_da_sessao() -> str:
    """Assina o cookie de sessao. Um por INSTALACAO, gerado na primeira vez.

    Ate a Fase 9 havia um valor constante no codigo. Num programa distribuido
    isso significa que todas as copias assinam com a mesma chave — e embora
    aqui o cookie carregue apenas a fila de mensagens de tela, e nao
    identidade nem dado de paciente, segredo constante em binario distribuido
    e habito que nao deve sobreviver ao empacotamento.
    """
    if os.environ.get("CONCILIADOR_SECRET"):
        return os.environ["CONCILIADOR_SECRET"]
    arquivo = caminhos.base_dados() / "config" / "sessao.chave"
    try:
        if arquivo.exists():
            valor = arquivo.read_text(encoding="utf-8").strip()
            if valor:
                return valor
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        valor = secrets.token_hex(32)
        arquivo.write_text(valor, encoding="utf-8")
        return valor
    except OSError:
        # Sem poder gravar, a sessao vale enquanto o processo viver. E pior do
        # que persistir, mas melhor do que nao abrir — e a partida vai falhar
        # logo adiante, em `preparar()`, com mensagem propria.
        return secrets.token_hex(32)


# =================================================================== conferir
def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def conferir_banco(caminho: Path) -> dict:
    """Abre o banco e responde o que ele e. Levanta se nao servir."""
    if not caminho.exists():
        raise ErroDeInstalacao(
            "O banco de dados não foi encontrado em:\n  %s" % caminho)
    try:
        con = sqlite3.connect("file:%s?mode=ro" % caminho.as_posix(), uri=True)
    except sqlite3.Error as exc:
        raise ErroDeInstalacao(
            "O banco em %s não pôde ser aberto (%s)." % (caminho, exc))
    try:
        # `sqlite3.connect` NAO le o arquivo — abrir um .txt como banco passa
        # sem reclamar. O erro so aparece na primeira consulta, e ate a Fase 10
        # ele escapava daqui como `sqlite3.DatabaseError: file is not a
        # database`, em rastreamento de pilha cru, na tela de um farmaceutico.
        try:
            tabelas = {n for (n,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError as exc:
            raise ErroDeInstalacao(
                "O arquivo abaixo não é um banco de dados válido, ou está "
                "corrompido:\n  %s\n\n(detalhe técnico: %s)\n\n"
                "Se você tem uma cópia de segurança, restaure-a de:\n  %s"
                % (caminho, exc, caminhos.backups()))
        faltando = [t for t in ESSENCIAIS if t not in tabelas]
        if faltando:
            raise ErroDeInstalacao(
                "O arquivo em %s não é um banco do Conciliador: faltam as "
                "tabelas %s." % (caminho, ", ".join(faltando)))
        try:
            integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise ErroDeInstalacao(
                "O banco em %s não pôde ser verificado (%s). Restaure uma "
                "cópia de segurança de %s." % (caminho, exc, caminhos.backups()))
        if integridade != "ok":
            raise ErroDeInstalacao(
                "O banco em %s está corrompido (integrity_check: %s). "
                "Restaure um backup de %s."
                % (caminho, integridade, caminhos.backups()))
        prop = {}
        if "propriedade" in tabelas:
            prop = dict(con.execute("SELECT chave, valor FROM propriedade"))
        return {
            "caminho": str(caminho),
            "tabelas": len(tabelas),
            "substancias": con.execute(
                "SELECT COUNT(*) FROM substancia").fetchone()[0],
            "interacoes": con.execute(
                "SELECT COUNT(*) FROM interacao_substancia").fetchone()[0],
            "atendimentos": con.execute(
                "SELECT COUNT(*) FROM atendimento").fetchone()[0],
            "modelos_ativos": con.execute(
                "SELECT COUNT(*) FROM modelo WHERE ativo=1").fetchone()[0]
            if "modelo" in tabelas else 0,
            "conhecimento_versao": prop.get("conhecimento.versao"),
            "conhecimento_digital": prop.get("conhecimento.digital"),
            "esquema_versao": prop.get("esquema.versao"),
            "integridade": integridade,
        }
    finally:
        con.close()


# =================================================================== preparar
def preparar(verboso: bool = False) -> dict:
    """Deixa a instalacao pronta para uso. Idempotente: rodar de novo nao
    muda nada quando ja esta pronta."""
    passos = []
    dados = caminhos.base_dados()
    if not caminhos.gravavel(dados):
        raise ErroDeInstalacao(
            "A pasta de dados não aceita gravação:\n  %s\n\n"
            "O programa precisa gravar os atendimentos. Escolha outra pasta "
            "definindo a variável de ambiente CONCILIADOR_DADOS, ou instale "
            "o programa fora de uma pasta protegida do Windows." % dados)
    passos.append(("pasta de dados gravável", str(dados)))

    for sub in ("database", "data", "backups", "config"):
        (dados / sub).mkdir(parents=True, exist_ok=True)

    banco = caminhos.banco()
    semente = caminhos.conhecimento_semente()
    if not banco.exists():
        if not semente.exists():
            raise ErroDeInstalacao(
                "Esta é a primeira execução e o conhecimento que deveria vir "
                "com o programa não foi encontrado em:\n  %s\n\n"
                "A instalação está incompleta. Reinstale o programa — o "
                "sistema NÃO cria um banco vazio, porque um banco vazio "
                "responderia 'nenhuma interação conhecida' para tudo."
                % semente)
        shutil.copy2(semente, banco)
        passos.append(("conhecimento instalado (primeira execução)",
                       "%s → %s" % (semente.name, banco)))
    else:
        passos.append(("banco já existia — preservado", str(banco)))

    estado = conferir_banco(banco)
    passos.append(("banco conferido",
                   "%d tabelas, %d substâncias, %d atendimento(s)"
                   % (estado["tabelas"], estado["substancias"],
                      estado["atendimentos"])))
    if estado["modelos_ativos"]:
        passos.append(("ATENÇÃO: há modelo de ML ativo",
                       "%d" % estado["modelos_ativos"]))
    else:
        passos.append(("ML desligado, como esperado", "0 modelos ativos"))

    if verboso:
        print("PREPARAÇÃO DA INSTALAÇÃO\n")
        for nome, detalhe in passos:
            print("  %-44s %s" % (nome, detalhe))
    return {"passos": passos, "banco": estado}


if __name__ == "__main__":
    try:
        preparar(verboso=True)
        print("\nInstalação pronta.")
    except ErroDeInstalacao as exc:
        print("INSTALAÇÃO INCOMPLETA\n\n%s" % exc)
        sys.exit(1)
