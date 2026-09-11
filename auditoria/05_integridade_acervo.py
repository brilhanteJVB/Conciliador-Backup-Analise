# -*- coding: utf-8 -*-
"""
FASE 9 — INTEGRIDADE DO ACERVO ORIGINAL

Reconfere, arquivo por arquivo, que o acervo continua exatamente como estava
quando foi inventariado. NAO e "confiar no relatorio anterior": recalcula.

DUAS CONFERENCIAS, DE PROPOSITO
-------------------------------
1. CONTRA O INVENTARIO de 09/09 (`auditoria/saida/inventario_bruto.json`).
   Aquele inventario gravou `hash_rapido` — sha256 do TAMANHO mais os
   primeiros 8 MB, truncado em 24 hex. Barato e suficiente para achar
   duplicata, mas cego para alteracao depois do 8o megabyte. Aqui ele e
   recalculado com a mesma formula, para que a comparacao seja legitima.

2. MANIFESTO NOVO, DE CONTEUDO INTEIRO (`auditoria/saida/acervo_sha256.json`).
   sha256 do arquivo COMPLETO, sem truncar. E o que faltava: a partir de
   agora existe uma linha de base que enxerga o arquivo todo, e a proxima
   execucao compara contra ela alem do inventario.

A segunda conferencia so tem valor a partir da segunda vez que rodar. Dizer
que ela "confirma que nada mudou" na primeira execucao seria falso — ela
apenas registra o estado de hoje. O texto da saida diz qual das duas coisas
esta acontecendo.

SOMENTE LEITURA. Este script abre arquivos do acervo em modo 'rb' e escreve
apenas dentro de `C:\\Sistema Conciliador projeto\\auditoria\\saida`.

Uso: python auditoria/05_integridade_acervo.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ORIGEM = Path(r"C:\Conteudos banco de dados tcc")
PROJETO = Path(__file__).resolve().parent.parent
SAIDA = PROJETO / "auditoria" / "saida"
INVENTARIO = SAIDA / "inventario_bruto.json"
MANIFESTO = SAIDA / "acervo_sha256.json"

IGNORAR_DIR = {"__pycache__", ".git", ".idea"}
LIMITE_HASH_INVENTARIO = 300 * 1024 * 1024     # o inventario pulou acima disto

FALHAS, PASSOS = [], []


def checa(nome, ok, detalhe=""):
    PASSOS.append((nome, ok, detalhe))
    if not ok:
        FALHAS.append((nome, detalhe))
    print("  %s %-54s %s" % ("OK  " if ok else "ERRO", nome[:54],
                             str(detalhe)[:60]))


def hash_rapido(caminho: Path, limite=8 * 1024 * 1024) -> str:
    """Copia fiel de auditoria/01_inventario.py:244. Nao 'melhore' aqui:
    o valor so serve para comparar com o que aquele script gravou."""
    h = hashlib.sha256()
    h.update(str(caminho.stat().st_size).encode())
    with open(caminho, "rb") as fh:
        h.update(fh.read(limite))
    return h.hexdigest()[:24]


def sha256_inteiro(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def percorrer():
    """Mesma travessia do inventario, para que os conjuntos sejam comparaveis."""
    for raiz, dirs, arquivos in __import__("os").walk(ORIGEM):
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIR]
        for nome in arquivos:
            caminho = Path(raiz) / nome
            try:
                st = caminho.stat()
            except OSError:
                continue
            yield caminho.relative_to(ORIGEM).as_posix(), caminho, st


def main() -> int:
    print("=" * 78)
    print("INTEGRIDADE DO ACERVO ORIGINAL — recalculada, nao herdada")
    print("=" * 78)
    print("origem: %s\n" % ORIGEM)

    if not ORIGEM.exists():
        checa("o acervo esta acessivel", False, str(ORIGEM))
        return 1

    inventario = json.loads(INVENTARIO.read_text(encoding="utf-8"))
    base = {r["caminho_relativo"]: r for r in inventario["arquivos"]}
    print("inventario de %s: %d arquivo(s), %.1f GB\n"
          % (inventario["gerado_em"][:10], inventario["n_arquivos"],
             inventario["bytes_totais"] / 1024 ** 3))

    anterior = {}
    if MANIFESTO.exists():
        anterior = json.loads(MANIFESTO.read_text(encoding="utf-8"))["arquivos"]

    atual, bytes_totais = {}, 0
    divergentes_hash, divergentes_tamanho, sem_hash = [], [], []
    novos, sumidos = [], []
    divergentes_sha, n_conferidos_sha = [], 0

    print("percorrendo e recalculando (leva alguns minutos)...", flush=True)
    for i, (rel, caminho, st) in enumerate(percorrer()):
        bytes_totais += st.st_size
        registro = {"tamanho": st.st_size,
                    "modificado": datetime.fromtimestamp(st.st_mtime)
                    .strftime("%Y-%m-%d %H:%M")}
        ref = base.get(rel)
        if ref is None:
            novos.append(rel)
        else:
            if ref.get("tamanho_bytes") != st.st_size:
                divergentes_tamanho.append(
                    (rel, ref.get("tamanho_bytes"), st.st_size))
            elif ref.get("hash"):
                if hash_rapido(caminho) != ref["hash"]:
                    divergentes_hash.append(rel)
            elif st.st_size and st.st_size < LIMITE_HASH_INVENTARIO:
                sem_hash.append(rel)

        if st.st_size:
            registro["sha256"] = sha256_inteiro(caminho)
            if rel in anterior and anterior[rel].get("sha256"):
                n_conferidos_sha += 1
                if anterior[rel]["sha256"] != registro["sha256"]:
                    divergentes_sha.append(rel)
        atual[rel] = registro
        if (i + 1) % 100 == 0:
            print("  ... %d arquivos" % (i + 1), flush=True)

    sumidos = sorted(set(base) - set(atual))
    print("")

    # ------------------------------------------------ conferencia 1
    print("1. CONTRA O INVENTARIO DE %s (hash do inicio + tamanho)\n"
          % inventario["gerado_em"][:10])
    checa("o numero de arquivos e o mesmo",
          len(atual) == inventario["n_arquivos"],
          "%d agora, %d no inventario" % (len(atual), inventario["n_arquivos"]))
    checa("nenhum arquivo do inventario desapareceu", not sumidos,
          "%d sumido(s)%s" % (len(sumidos),
                              (": " + ", ".join(sumidos[:3])) if sumidos else ""))
    checa("nenhum arquivo novo apareceu no acervo", not novos,
          "%d novo(s)%s" % (len(novos),
                            (": " + ", ".join(novos[:3])) if novos else ""))
    checa("nenhum arquivo mudou de tamanho", not divergentes_tamanho,
          "%d divergente(s)" % len(divergentes_tamanho))
    checa("nenhum hash do inventario divergiu", not divergentes_hash,
          "%d divergente(s)%s" % (len(divergentes_hash),
                                  (": " + divergentes_hash[0])
                                  if divergentes_hash else ""))
    checa("o total de bytes bate com o inventario",
          bytes_totais == inventario["bytes_totais"],
          "%d agora, %d antes" % (bytes_totais, inventario["bytes_totais"]))
    if sem_hash:
        print("     (nota: %d arquivo(s) sem hash no inventario — conferidos "
              "so por tamanho)" % len(sem_hash))

    # ------------------------------------------------ conferencia 2
    print("\n2. MANIFESTO DE CONTEUDO INTEIRO (sha256 sem truncar)\n")
    if anterior:
        checa("nenhum sha256 de conteudo inteiro divergiu",
              not divergentes_sha,
              "%d de %d conferido(s)%s"
              % (len(divergentes_sha), n_conferidos_sha,
                 (": " + divergentes_sha[0]) if divergentes_sha else ""))
        checa("o manifesto cobre todos os arquivos nao vazios",
              n_conferidos_sha >= len([r for r in atual.values()
                                       if r["tamanho"]]) - len(novos),
              "%d conferido(s)" % n_conferidos_sha)
    else:
        print("  --   primeira execucao: nao ha manifesto anterior para")
        print("       comparar. Esta execucao GRAVA a linha de base; ela nao")
        print("       prova que nada mudou, e nao sera contada como prova.")

    MANIFESTO.write_text(json.dumps(
        {"gerado_em": datetime.now(timezone.utc).isoformat(),
         "origem": str(ORIGEM), "algoritmo": "sha256 do conteudo inteiro",
         "n_arquivos": len(atual), "bytes_totais": bytes_totais,
         "arquivos": atual}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n  manifesto gravado: %s (%d arquivos, %.1f GB)"
          % (MANIFESTO.relative_to(PROJETO).as_posix(), len(atual),
             bytes_totais / 1024 ** 3))

    print("\n" + "=" * 78)
    print("%d conferencia(s) · %d ok · %d falha(s)"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS)))
    for nome, det in FALHAS:
        print("  FALHA: %s — %s" % (nome, det))
    if not FALHAS:
        print("\nACERVO INTACTO — %d arquivo(s), 0 modificado(s)." % len(atual))
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
