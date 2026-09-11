# -*- coding: utf-8 -*-
"""
PONTO DE ENTRADA DO PROGRAMA — e o que o `.exe` executa.

O QUE ELE FAZ, NESTA ORDEM
--------------------------
  1. descobre onde ficam os recursos e os dados      (app/caminhos.py)
  2. prepara a instalacao, se for a primeira vez     (app/instalacao.py)
  3. escolhe uma porta livre
  4. sobe o servidor local e abre o navegador
  5. em qualquer falha, EXPLICA e nao some da tela

O ITEM 5 E O MOTIVO DE ESTE ARQUIVO EXISTIR. Um `.exe` que fecha sozinho
quando da erro nao e diagnosticavel por quem o recebeu: a janela pisca e
desaparece. Aqui toda falha vira uma mensagem escrita para ser lida por um
farmaceutico, o detalhe tecnico vai para o log, e a janela ESPERA.

Uso:
    SistemaConciliador.exe
    SistemaConciliador.exe --diagnostico   # so imprime o estado e sai
    SistemaConciliador.exe --porta 5001
    SistemaConciliador.exe --atualizar-conhecimento <arquivo.db>
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _preparar_console() -> None:
    """O console do Windows abre em cp1252, que nao tem 'a', '~', nem '->'.

    A primeira execucao do `.exe` morreu aqui: `UnicodeEncodeError` ao
    imprimir a seta da mensagem "conhecimento instalado". Um programa cuja
    razao de existir e EXPLICAR o que deu errado nao pode morrer ao escrever
    uma mensagem — e o pior e que morre justamente quando tem algo a dizer.

    Duas travas, independentes: o console passa para UTF-8 quando o Windows
    deixa, e a saida usa `errors="replace"` para que, mesmo quando nao deixar,
    um caractere vire '?' em vez de derrubar o programa.
    """
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:                                   # noqa: BLE001
            pass
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


_preparar_console()

import caminhos                                            # noqa: E402
import instalacao                                          # noqa: E402
import versao as ver                                       # noqa: E402

PORTA_PADRAO = 5000
TENTATIVAS_DE_PORTA = 20


def porta_livre(inicial: int) -> int:
    """A primeira porta livre a partir de `inicial`.

    Um segundo duplo-clique no icone nao pode derrubar o programa que ja esta
    aberto com um atendimento em andamento: se a porta esta ocupada, sobe na
    seguinte e avisa.
    """
    for porta in range(inicial, inicial + TENTATIVAS_DE_PORTA):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", porta))
                return porta
            except OSError:
                continue
    raise instalacao.ErroDeInstalacao(
        "Nenhuma porta livre entre %d e %d. Feche outros programas que usem "
        "essas portas e tente de novo."
        % (inicial, inicial + TENTATIVAS_DE_PORTA - 1))


def esperar_tecla(codigo: int) -> int:
    """Segura a janela aberta para que a mensagem possa ser lida."""
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\nPressione ENTER para fechar. ")
    except (EOFError, OSError, RuntimeError):
        pass
    return codigo


def cabecalho(porta: int, estado: dict) -> None:
    b = estado["banco"]
    print("=" * 70)
    print(ver.completa())
    print(ver.INSTITUICAO)
    print("=" * 70)
    print("  conhecimento  versão %s · impressão digital %s"
          % (b.get("conhecimento_versao") or "não declarada",
             b.get("conhecimento_digital") or "não declarada"))
    print("  banco         %s" % b["caminho"])
    print("  atendimentos  %d gravado(s)" % b["atendimentos"])
    print("  modelo de ML  %s"
          % ("DESLIGADO (nenhum modelo ativo)" if not b["modelos_ativos"]
             else "ATIVO — %d" % b["modelos_ativos"]))
    print("  log           %s" % caminhos.log())
    print("-" * 70)
    print("  ABRA NO NAVEGADOR:  http://127.0.0.1:%d" % porta)
    print("  (feche esta janela ou pressione Ctrl+C para encerrar)")
    print("=" * 70)
    print("\n  %s\n" % ver.LIMITACAO_CLINICA)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    porta_pedida = PORTA_PADRAO
    if "--porta" in argv:
        try:
            porta_pedida = int(argv[argv.index("--porta") + 1])
        except (IndexError, ValueError):
            print("--porta precisa de um número. Ex.: --porta 5001")
            return esperar_tecla(2)

    # ------------------------------------------------ 1 e 2: preparar
    try:
        estado = instalacao.preparar()
    except instalacao.ErroDeInstalacao as exc:
        print("=" * 70)
        print("O PROGRAMA NÃO PÔDE INICIAR")
        print("=" * 70)
        print("\n%s\n" % exc)
        print("Nenhum dado foi alterado.")
        return esperar_tecla(1)
    except Exception:                                       # noqa: BLE001
        print("=" * 70)
        print("O PROGRAMA NÃO PÔDE INICIAR — falha inesperada")
        print("=" * 70)
        print("\n%s" % traceback.format_exc())
        return esperar_tecla(1)

    # ------------------------------------- atualizacao do conhecimento
    if "--atualizar-conhecimento" in argv:
        try:
            origem = Path(argv[argv.index("--atualizar-conhecimento") + 1])
        except IndexError:
            print("--atualizar-conhecimento precisa do caminho do arquivo "
                  "conhecimento.db")
            return esperar_tecla(2)
        import atualizacao
        print("=" * 70)
        print("ATUALIZAÇÃO DO CONHECIMENTO")
        print("=" * 70)
        print("Os seus atendimentos são preservados. Um backup é feito "
              "antes.\n")
        try:
            atualizacao.atualizar(origem.resolve())
        except (atualizacao.ErroDeAtualizacao,
                instalacao.ErroDeInstalacao) as exc:
            print("\n%s" % exc)
            return esperar_tecla(1)
        return esperar_tecla(0)

    if "--diagnostico" in argv:
        print("DIAGNÓSTICO\n")
        for k, v in caminhos.resumo().items():
            print("  %-26s %s" % (k, v))
        print("")
        for nome, detalhe in estado["passos"]:
            print("  %-44s %s" % (nome, detalhe))
        print("\n  %s" % ver.completa())
        return 0

    # ------------------------------------------------ 3: porta
    try:
        porta = porta_livre(porta_pedida)
    except instalacao.ErroDeInstalacao as exc:
        print("\n%s" % exc)
        return esperar_tecla(1)
    if porta != porta_pedida:
        print("A porta %d estava ocupada — usando a %d.\n"
              % (porta_pedida, porta))

    # ------------------------------------------------ 4: subir
    try:
        import web
    except Exception:                                       # noqa: BLE001
        print("=" * 70)
        print("O PROGRAMA NÃO PÔDE INICIAR — a interface não carregou")
        print("=" * 70)
        print("\n%s" % traceback.format_exc())
        return esperar_tecla(1)

    web.log.info("início: %s, porta %d, banco %s",
                 ver.completa(), porta, caminhos.banco())
    cabecalho(porta, estado)

    if "--sem-navegador" not in argv:
        threading.Thread(
            target=lambda: (time.sleep(1.2),
                            webbrowser.open("http://127.0.0.1:%d" % porta)),
            daemon=True).start()

    try:
        web.app.run(host="127.0.0.1", port=porta, debug=False,
                    use_reloader=False)
    except KeyboardInterrupt:
        print("\nEncerrado. Os atendimentos continuam gravados em:\n  %s"
              % caminhos.banco())
        return 0
    except Exception:                                       # noqa: BLE001
        logging.getLogger("conciliador").error(
            "falha ao servir\n%s", traceback.format_exc())
        print("=" * 70)
        print("O SERVIDOR PAROU COM ERRO")
        print("=" * 70)
        print("\nO detalhe técnico foi registrado em:\n  %s" % caminhos.log())
        print("\nOs atendimentos já gravados NÃO foram perdidos.")
        return esperar_tecla(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
