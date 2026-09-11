# -*- coding: utf-8 -*-
"""
FASE 9 — CONVERGENCIA E REPRODUTIBILIDADE DO PIPELINE.

A Fase 8 mostrou que este e o ponto critico: o pipeline dava resultados
diferentes conforme o numero de vezes que tinha rodado (1.153 substancias com
ATC numa passada, 1.159 em duas), e a impressao digital dos dados nao via a
diferenca. Corrigido pelo passo 68 e pela impressao digital de conteudo
(D-048). Este teste existe para que isso nao volte em silencio.

O QUE ELE FAZ, nesta ordem
--------------------------
  0  guarda uma copia intacta do banco atual
  1  reconstroi do ZERO  (--recriar)                 -> fotografia F1
  2  roda de novo, incremental                        -> fotografia F2
  3  roda mais uma vez, incremental                   -> fotografia F3
  4  F1 == F2 == F3        convergencia numa passada
  5  F1 == estado anterior reproducao a partir do mesmo corpus
  6  a impressao digital reproduzida e a que os modelos gravaram
  7  devolve o banco guardado no passo 0

O passo 7 nao e cosmetico: `--recriar` apaga `modelo` e `predicao`, e o
projeto tem dois modelos registrados e 600 previsoes que levaram vinte
minutos para existir. A reconstrucao acontece, e conferida, e desfeita.

COLUNAS VOLATEIS. `carga.data_importacao`, `substancia.criado_em` e
`auditoria_conflito.registrado_em` mudam a cada carga por definicao — sao a
hora em que a linha entrou, nao o dado. Ficam de fora da comparacao, uma a
uma e declaradas, nunca por "ignorar o que nao bate".

Leva ~2 minutos. NAO entra em `pipeline/executar_tudo.py` (seria recursao).

Uso: python tests/fase9_convergencia.py
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "pipeline"))
sys.path.insert(0, str(RAIZ / "ml"))

BANCO = RAIZ / "database" / "conciliador.db"

ETAPAS = ["10_fontes.py", "20_substancias.py", "30_produtos.py", "40_atc.py",
          "50_regras_administracao.py", "55_regras_bula.py",
          "58_conflitos_administracao.py", "60_interacoes_substancia.py",
          "62_papel_farmacocinetico.py", "64_contraindicacoes_bula.py",
          "65_habitos_bula.py", "68_vincular_atc_pendente.py"]

# Hora de entrada da linha, nao o dado. Cada exclusao esta justificada.
VOLATEIS = {
    "carga": {"data_importacao"},            # quando o lote foi lido
    "substancia": {"criado_em"},             # quando a linha entrou
    "auditoria_conflito": {"registrado_em"},  # quando o conflito foi visto
}
# Nao fazem parte da carga: sao o atendimento e a camada de ML.
FORA_DA_CARGA = {"paciente", "atendimento", "atendimento_medicamento",
                 "atendimento_item", "posologia", "horario_administracao",
                 "rotina_paciente", "paciente_alergia", "paciente_condicao",
                 "paciente_habito", "conciliacao", "conciliacao_par",
                 "achado", "achado_evidencia", "nao_avaliado",
                 "anotacao_profissional", "modelo", "predicao"}

PASSOS, FALHAS = [], []


def checa(nome, ok, detalhe=""):
    PASSOS.append((nome, ok, detalhe))
    if not ok:
        FALHAS.append((nome, detalhe))
    print("   %s %-54s %s" % ("OK  " if ok else "ERRO", nome[:54],
                              str(detalhe)[:58]))


def tabelas(con):
    return [n for (n,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def fotografia(caminho: Path) -> dict:
    """Contagem e hash do conteudo de cada tabela da CARGA, sem as colunas
    de hora de entrada."""
    con = sqlite3.connect(caminho)
    foto = {}
    try:
        for t in tabelas(con):
            if t in FORA_DA_CARGA:
                continue
            colunas = [d[1] for d in con.execute(
                "PRAGMA table_info(%s)" % t)]
            usar = [c for c in colunas if c not in VOLATEIS.get(t, ())]
            h, n = hashlib.sha256(), 0
            for linha in con.execute(
                    "SELECT %s FROM %s ORDER BY rowid"
                    % (", ".join(usar), t)):
                h.update(repr(linha).encode("utf-8"))
                n += 1
            foto[t] = (n, h.hexdigest()[:16])
    finally:
        con.close()
    return foto


def diferenca(a: dict, b: dict) -> list:
    saida = []
    for t in sorted(set(a) | set(b)):
        if a.get(t) != b.get(t):
            saida.append((t, a.get(t), b.get(t)))
    return saida


def impressao(caminho: Path) -> str:
    import _comum as mlc
    con = sqlite3.connect(caminho)
    try:
        return mlc.versao_dados(con)["impressao"]
    finally:
        con.close()


def detalhes(caminho: Path) -> dict:
    """Os numeros que o item 12 pede, um a um."""
    con = sqlite3.connect(caminho)
    try:
        q = lambda sql: con.execute(sql).fetchone()[0]
        return {
            "substâncias": q("SELECT COUNT(*) FROM substancia"),
            "com ATC": q("SELECT COUNT(*) FROM substancia "
                         "WHERE atc_codigo IS NOT NULL"),
            "sinônimos": q("SELECT COUNT(*) FROM substancia_sinonimo"),
            "sinônimos INN": q("SELECT COUNT(*) FROM substancia_sinonimo "
                               "WHERE tipo='INN'"),
            "produtos": q("SELECT COUNT(*) FROM produto"),
            "apresentações": q("SELECT COUNT(*) FROM apresentacao"),
            "interações f×f": q("SELECT COUNT(*) FROM interacao_substancia"),
            "pares distintos": q("SELECT COUNT(*) FROM (SELECT DISTINCT "
                                 "substancia_a_id, substancia_b_id "
                                 "FROM interacao_substancia)"),
            "regras de administração": q("SELECT COUNT(*) FROM "
                                         "regra_administracao"),
            "regras de separação": q("SELECT COUNT(*) FROM regra_separacao"),
            "papéis PK": q("SELECT COUNT(*) FROM papel_farmacocinetico"),
            "contraindicações": q("SELECT COUNT(*) FROM interacao_doenca"),
            "evidências": q("SELECT COUNT(*) FROM evidencia"),
            "lotes de carga": q("SELECT COUNT(*) FROM carga"),
            "conflitos de auditoria": q("SELECT COUNT(*) FROM "
                                        "auditoria_conflito"),
        }
    finally:
        con.close()


def rodar(etapas, recriar=False) -> bool:
    for i, etapa in enumerate(etapas):
        extra = ["--recriar"] if (recriar and i == 0) else []
        r = subprocess.run(
            [sys.executable, str(RAIZ / "pipeline" / etapa), *extra],
            cwd=str(RAIZ), capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if r.returncode != 0:
            print("      PIPELINE FALHOU em %s:" % etapa)
            print("      " + (r.stderr or r.stdout or "")[-600:])
            return False
    return True


def main() -> int:
    print("=" * 78)
    print("FASE 9 — CONVERGENCIA E REPRODUTIBILIDADE DO PIPELINE")
    print("=" * 78)
    t0 = time.time()
    if not BANCO.exists():
        checa("o banco existe para ser conferido", False, str(BANCO))
        return 1

    tmp = Path(tempfile.mkdtemp())
    guardado = tmp / "conciliador_antes.db"
    shutil.copy(BANCO, guardado)
    print("banco guardado em %s\n" % guardado)

    antes = fotografia(guardado)
    antes_det = detalhes(guardado)
    antes_digital = impressao(guardado)
    con = sqlite3.connect(guardado)
    modelos_antes = list(con.execute(
        "SELECT versao, versao_dados FROM modelo ORDER BY id"))
    n_predicao = con.execute("SELECT COUNT(*) FROM predicao").fetchone()[0]
    con.close()
    print("estado anterior: impressão digital %s · %d modelo(s) · %d previsões"
          % (antes_digital, len(modelos_antes), n_predicao))

    try:
        print("\n1. RECONSTRUCAO DO ZERO (--recriar)")
        t = time.time()
        ok1 = rodar(ETAPAS, recriar=True)
        checa("o pipeline reconstrói do zero sem erro", ok1,
              "%.0fs" % (time.time() - t))
        if not ok1:
            return 1
        f1, d1, i1 = fotografia(BANCO), detalhes(BANCO), impressao(BANCO)

        print("\n2. SEGUNDA PASSADA (incremental)")
        t = time.time()
        ok2 = rodar(ETAPAS)
        checa("o pipeline roda de novo sem erro", ok2, "%.0fs" % (time.time() - t))
        f2, d2, i2 = fotografia(BANCO), detalhes(BANCO), impressao(BANCO)

        print("\n3. TERCEIRA PASSADA (incremental)")
        ok3 = rodar(ETAPAS)
        checa("o pipeline roda uma terceira vez sem erro", ok3)
        f3, d3, i3 = fotografia(BANCO), detalhes(BANCO), impressao(BANCO)

        print("\n4. CONVERGENCIA — a primeira passada ja e o ponto fixo\n")
        dif12 = diferenca(f1, f2)
        checa("a 2ª passada não muda uma linha da 1ª", not dif12,
              "%d tabela(s) diferente(s): %s" % (len(dif12),
                                                 [t for t, _a, _b in dif12][:3]))
        dif23 = diferenca(f2, f3)
        checa("a 3ª passada não muda uma linha da 2ª", not dif23,
              "%d tabela(s) diferente(s)" % len(dif23))
        checa("a impressão digital é a mesma nas três passadas",
              i1 == i2 == i3, "%s · %s · %s" % (i1, i2, i3))

        print("\n   número a número, o que o item 12 pede:\n")
        for chave in d1:
            iguais = d1[chave] == d2[chave] == d3[chave]
            checa("%s: igual nas três passadas" % chave, iguais,
                  "%s · %s · %s" % (d1[chave], d2[chave], d3[chave]))

        print("\n5. REPRODUTIBILIDADE — mesmo corpus, mesmo resultado\n")
        dif_antes = diferenca(antes, f1)
        checa("reconstruir do zero reproduz o banco anterior, tabela a tabela",
              not dif_antes,
              "%d tabela(s) diferente(s): %s"
              % (len(dif_antes), [t for t, _a, _b in dif_antes][:3]))
        for chave in d1:
            checa("%s reproduzido" % chave, antes_det[chave] == d1[chave],
                  "antes %s · agora %s" % (antes_det[chave], d1[chave]))
        checa("a impressão digital reproduzida é idêntica",
              antes_digital == i1, "%s vs %s" % (antes_digital, i1))

        print("\n6. O MODELO CONTINUA VALIDO SOBRE ESTE BANCO\n")
        for versao, vdados in modelos_antes:
            checa("[%s] treinado sobre a impressão digital reproduzida"
                  % versao, vdados == i1, "%s vs %s" % (vdados, i1))
    finally:
        print("\n7. DEVOLVENDO O BANCO GUARDADO")
        shutil.copy(guardado, BANCO)
        con = sqlite3.connect(BANCO)
        try:
            n_mod = con.execute("SELECT COUNT(*) FROM modelo").fetchone()[0]
            n_pred = con.execute("SELECT COUNT(*) FROM predicao").fetchone()[0]
            integ = con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
        checa("os modelos voltaram", n_mod == len(modelos_antes),
              "%d modelo(s)" % n_mod)
        checa("as previsões voltaram", n_pred == n_predicao,
              "%d previsão(ões)" % n_pred)
        checa("o banco devolvido está íntegro", integ == "ok", integ)
        depois = fotografia(BANCO)
        checa("o banco devolvido é idêntico ao guardado",
              not diferenca(antes, depois),
              "%d diferença(s)" % len(diferenca(antes, depois)))
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 78)
    print("%d conferência(s) · %d ok · %d falha(s) · %.0fs"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS),
             time.time() - t0))
    for nome, det in FALHAS:
        print("  FALHA: %s — %s" % (nome, det))
    if not FALHAS:
        print("\nO PIPELINE CONVERGE NUMA PASSADA E REPRODUZ O MESMO BANCO.")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
