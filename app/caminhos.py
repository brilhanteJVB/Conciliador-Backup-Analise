# -*- coding: utf-8 -*-
"""
ONDE CADA COISA VIVE — em desenvolvimento e dentro do `.exe`.

O PROBLEMA QUE ESTE ARQUIVO RESOLVE
-----------------------------------
Em desenvolvimento tudo mora ao lado do codigo: o banco em `database/`, o log
em `data/`. Num `.exe` isso nao funciona, por dois motivos independentes:

1. O codigo fica DENTRO do pacote. `Path(__file__).parent.parent` aponta para
   uma pasta temporaria de extracao (`sys._MEIPASS`), que some quando o
   programa fecha.
2. O programa pode estar instalado em `C:\\Program Files`, onde o Windows
   RECUSA escrita a usuario sem elevacao. Um banco que precisa gravar
   atendimento nao pode viver la — o sintoma seria `readonly database` no meio
   de um atendimento, que e o pior momento possivel.

Por isso ha DOIS lugares, e eles nao se misturam:

    RECURSOS   somente leitura, vem com o programa
               templates, CSS, conhecimento.db (a semente), modelos
    DADOS      gravavel, e do usuario, sobrevive a reinstalacao
               conciliador.db (o banco em uso), logs, backups

EM DESENVOLVIMENTO OS DOIS APONTAM PARA A RAIZ DO REPOSITORIO. Isso e
deliberado: as 972 conferencias da bateria rodam sobre os mesmos caminhos de
sempre, e empacotar nao pode mudar o que elas medem.

VARIAVEL DE ESCAPE
------------------
`CONCILIADOR_DADOS` redefine a pasta de dados. Serve para a instalacao
portatil (pendrive), para teste, e para o farmaceutico que quer os
atendimentos num disco especifico. E lida uma vez, na importacao.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Nome usado na pasta de dados do usuario. Nao mude sem migrar: e onde os
# atendimentos ja gravados estao.
APLICACAO = "ConciliadorMedicamentos"


def empacotado() -> bool:
    """Verdadeiro quando rodando de dentro de um `.exe` do PyInstaller."""
    return getattr(sys, "frozen", False)


def base_recursos() -> Path:
    """Raiz do que veio COM o programa. Trate como somente leitura.

    Sob PyInstaller `--onedir`, `sys._MEIPASS` e a pasta `_internal` ao lado do
    executavel; sob `--onefile`, e uma pasta temporaria que some ao fechar.
    """
    if empacotado():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def base_dados() -> Path:
    """Raiz do que o USUARIO grava. Precisa ser gravavel, sempre."""
    escolhido = os.environ.get("CONCILIADOR_DADOS")
    if escolhido:
        return Path(escolhido).expanduser().resolve()
    if not empacotado():
        # Desenvolvimento: exatamente como sempre foi.
        return Path(__file__).resolve().parent.parent
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APLICACAO
    return Path.home() / ("." + APLICACAO)


# ------------------------------------------------------------------ arquivos
def banco() -> Path:
    """O banco EM USO. Um arquivo so: conhecimento e atendimento juntos.

    A separacao entre os dois acontece na ATUALIZACAO, nao no disco — ver
    `docs/DECISIONS.md` D-051. Resumo do motivo: oito chaves estrangeiras
    ligam atendimento a conhecimento, e o SQLite nao aplica chave estrangeira
    entre arquivos diferentes. Separar os arquivos desligaria justamente a
    protecao que a atualizacao precisa ter.
    """
    return base_dados() / "database" / "conciliador.db"


def conhecimento_semente() -> Path:
    """O conhecimento que veio com o programa, intocado. E a semente do banco
    do usuario na primeira execucao, e a origem de qualquer atualizacao."""
    return base_recursos() / "conhecimento" / "conhecimento.db"


def manifesto_conhecimento() -> Path:
    return base_recursos() / "conhecimento" / "conhecimento.json"


def modelos() -> Path:
    return base_recursos() / "models"


def templates() -> Path:
    return base_recursos() / "app" / "templates"


def estaticos() -> Path:
    return base_recursos() / "app" / "static"


def log() -> Path:
    """Mesmo caminho RELATIVO nos dois modos — em desenvolvimento continua
    sendo `data/aplicacao.log`, como a documentacao sempre disse; no `.exe`
    vira `<dados do usuario>/data/aplicacao.log`."""
    return base_dados() / "data" / "aplicacao.log"


def backups() -> Path:
    return base_dados() / "backups"


def gravavel(pasta: Path) -> bool:
    """Testa a escrita DE VERDADE, criando e apagando um arquivo.

    `os.access(W_OK)` mente no Windows: devolve verdadeiro para pastas em que
    a escrita e barrada por ACL. A unica resposta confiavel e tentar.
    """
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        alvo = pasta / ".escrita_conciliador"
        alvo.write_text("ok", encoding="utf-8")
        alvo.unlink()
        return True
    except OSError:
        return False


def resumo() -> dict:
    """Tudo que o diagnostico precisa saber, numa chamada."""
    return {
        "empacotado": empacotado(),
        "base_recursos": str(base_recursos()),
        "base_dados": str(base_dados()),
        "banco": str(banco()),
        "banco_existe": banco().exists(),
        "conhecimento_semente": str(conhecimento_semente()),
        "semente_existe": conhecimento_semente().exists(),
        "log": str(log()),
        "backups": str(backups()),
        "dados_gravavel": gravavel(base_dados()),
        "variavel_CONCILIADOR_DADOS": os.environ.get("CONCILIADOR_DADOS"),
    }


if __name__ == "__main__":
    print("CAMINHOS DO CONCILIADOR\n")
    for k, v in resumo().items():
        print("  %-26s %s" % (k, v))
