# -*- coding: utf-8 -*-
"""
MANIFESTO DO BACKUP — o que foi preservado, o que ficou de fora, e por quê.

Gera `docs/MANIFESTO_BACKUP.md` e `docs/manifesto_backup.json` a partir do
estado REAL do diretorio, nunca de uma lista escrita a mao. Um manifesto
digitado envelhece na primeira vez que alguem acrescenta um arquivo.

O QUE ELE REGISTRA
------------------
  - data, hora e estado declarado do projeto;
  - quantidade de arquivos e tamanho total, dentro e fora do backup;
  - sha256 de cada arquivo critico, um a um;
  - impressao digital do BANCO (a mesma que o ML usa para dizer sobre qual
    dado um modelo foi treinado) — nao o hash do arquivo .db, que muda a cada
    atendimento gravado sem que um unico dado de conhecimento tenha mudado;
  - modelo, versao, semente e status do ML;
  - versao do esquema;
  - TUDO o que ficou de fora, com motivo, alternativa e impacto na
    capacidade de reconstrucao.

A ultima linha e a que importa: nenhum arquivo sai do backup em silencio.

Uso: python scripts/gerar_manifesto_backup.py [--estado "TEXTO"]
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ml"))

BANCO = RAIZ / "database" / "conciliador.db"
SAIDA_MD = RAIZ / "docs" / "MANIFESTO_BACKUP.md"
SAIDA_JSON = RAIZ / "docs" / "manifesto_backup.json"

IGNORAR_DIR = {"__pycache__", ".git", ".idea", ".venv", "venv", "node_modules"}

# Os arquivos que, se divergirem, invalidam o backup. Conferidos um a um.
CRITICOS = [
    "database/schema.sql",
    "database/conciliador.db",
    "pipeline/executar_tudo.py",
    "pipeline/_comum.py",
    "pipeline/normalizacao.py",
    "rules/motor_conciliacao.py",
    "rules/motor_horarios.py",
    "rules/_prioridade.py",
    "app/web.py",
    "app/servicos.py",
    "app/busca.py",
    "app/relatorio.py",
    "app/rotulos.py",
    "ml/_features.py",
    "ml/_comum.py",
    "ml/70_predizer.py",
    "models/espaco_features.json",
    "models/calibrador_m1.json",
    "models/m1_1_0-boosting.json",
    "tests/teste_regressao.py",
    "tests/fase9_v1_sistema.py",
    "tests/fase9_v2_independente.py",
    "tests/fase9_cenarios.py",
    "tests/fase9_convergencia.py",
    "auditoria/05_integridade_acervo.py",
    "auditoria/saida/acervo_sha256.json",
    "docs/STATUS.md",
    "docs/ARQUITETURA.md",
    "docs/DECISIONS.md",
    "docs/ML_FASE7.md",
    "docs/FASE9_VALIDACAO.md",
    "docs/EMPACOTAMENTO.md",
    "CLAUDE.md",
    "README.md",
    # Fase 10
    "app/caminhos.py",
    "app/instalacao.py",
    "app/atualizacao.py",
    "app/principal.py",
    "app/versao.py",
    "pipeline/80_identidade.py",
    "scripts/build_exe.py",
    "scripts/preparar_conhecimento.py",
    "tests/fase10_empacotamento.py",
    "tests/fase10_v2_independente.py",
    "docs/GUIA_INSTALACAO.md",
]


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def versionado() -> set:
    """O que o Git de fato vai guardar — perguntado ao Git, nao deduzido do
    .gitignore por conta propria."""
    try:
        r = subprocess.run(["git", "ls-files", "--cached", "--others",
                            "--exclude-standard"],
                           cwd=str(RAIZ), capture_output=True, text=True,
                           encoding="utf-8")
        if r.returncode == 0:
            return {l.strip() for l in r.stdout.splitlines() if l.strip()}
    except OSError:
        pass
    return set()


def percorrer():
    for raiz, dirs, arqs in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIR]
        for a in arqs:
            p = Path(raiz) / a
            try:
                yield p.relative_to(RAIZ).as_posix(), p, p.stat().st_size
            except OSError:
                continue


def estado_do_banco() -> dict:
    if not BANCO.exists():
        return {"erro": "banco ausente"}
    con = sqlite3.connect(BANCO)
    try:
        q = lambda s: con.execute(s).fetchone()[0]
        try:
            import _comum as mlc
            digital = mlc.versao_dados(con)["impressao"]
        except Exception as exc:                          # noqa: BLE001
            digital = "não calculada (%s)" % type(exc).__name__
        modelos = [dict(zip(("nome", "versao", "algoritmo", "status", "ativo",
                             "semente", "versao_dados", "limiar"), r))
                   for r in con.execute(
                       "SELECT nome, versao, algoritmo, status, ativo, semente,"
                       " versao_dados, limiar_alerta FROM modelo ORDER BY id")]
        return {
            "impressao_digital": digital,
            "tabelas": q("SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                         " AND name NOT LIKE 'sqlite_%'"),
            "views": q("SELECT COUNT(*) FROM sqlite_master WHERE type='view'"),
            "substancias": q("SELECT COUNT(*) FROM substancia"),
            "substancias_com_atc": q("SELECT COUNT(*) FROM substancia "
                                     "WHERE atc_codigo IS NOT NULL"),
            "interacoes": q("SELECT COUNT(*) FROM interacao_substancia"),
            "evidencias": q("SELECT COUNT(*) FROM evidencia"),
            "cargas": q("SELECT COUNT(*) FROM carga"),
            "modelos": modelos,
            "modelos_ativos": q("SELECT COUNT(*) FROM modelo WHERE ativo=1"),
            "predicoes": q("SELECT COUNT(*) FROM predicao"),
            "atendimentos": q("SELECT COUNT(*) FROM atendimento"),
            "pacientes": q("SELECT COUNT(*) FROM paciente"),
            "integridade": q("PRAGMA integrity_check"),
        }
    finally:
        con.close()


# Cada exclusao precisa de motivo, alternativa e impacto. Sem isso a linha nao
# entra no manifesto — e sem entrar no manifesto o arquivo nao e excluido.
def fora_do_backup(dentro: set) -> list:
    justificativas = {
        "database/conciliador_backup_": (
            "fotografia de uma fase já superada (5 ou 7)",
            "permanece no disco local, em `database/`, intocada",
            "NENHUM — o que restaura a Fase 9 é `database/conciliador.db`, "
            "que está versionado"),
        "data/aplicacao.log": (
            "log de execução: é da máquina, não do projeto",
            "recriado sozinho por `app/web.py` na importação",
            "NENHUM"),
        "data/preview/": (
            "página capturada por teste para inspeção visual",
            "recriada por `tests/verificacao_aplicacao.py`",
            "NENHUM"),
        "__pycache__": ("cache do interpretador", "recriado no próximo import",
                        "NENHUM"),
        "dist/": ("executável gerado pelo build (Fase 10)",
                  "recriado por `scripts/build_exe.py` em ~17 s",
                  "NENHUM — é artefato, não fonte"),
        "build/": ("arquivos intermediários do PyInstaller",
                   "recriados por `scripts/build_exe.py`", "NENHUM"),
        "conhecimento/": ("banco distribuível, cópia do banco em uso com o "
                          "atendimento esvaziado",
                          "recriado por `scripts/preparar_conhecimento.py`",
                          "NENHUM — `database/conciliador.db` está no backup"),
        "config/sessao.chave": ("SEGREDO por instalação — assina o cookie de "
                                "sessão", "regenerado sozinho na próxima "
                                "execução", "NENHUM — e nunca deve ser "
                                "versionado"),
        "backups/": ("cópias de segurança feitas antes de atualizar o "
                     "conhecimento", "permanecem no disco local",
                     "NENHUM"),
    }
    saida = []
    for rel, p, tam in percorrer():
        if rel in dentro or "__pycache__" in rel:
            if "__pycache__" not in rel:
                continue
        if rel in dentro:
            continue
        motivo = alternativa = impacto = "NÃO JUSTIFICADO — investigar"
        for chave, (m, a, i) in justificativas.items():
            if chave in rel:
                motivo, alternativa, impacto = m, a, i
                break
        saida.append({"arquivo": rel, "bytes": tam, "motivo": motivo,
                      "alternativa": alternativa, "impacto": impacto})
    return sorted(saida, key=lambda x: -x["bytes"])


def main() -> int:
    estado = "FASE 9 — CONCLUÍDA / APTO PARA EMPACOTAMENTO"
    if "--estado" in sys.argv:
        estado = sys.argv[sys.argv.index("--estado") + 1]
    # A declaracao acompanha o estado. Escrita a mao, ela diria "anterior a
    # Fase 10" num manifesto gerado depois da Fase 10.
    declaracao = ("Este backup corresponde ao estado imediatamente anterior à "
                  "Fase 10.")
    if "--declaracao" in sys.argv:
        declaracao = sys.argv[sys.argv.index("--declaracao") + 1]

    agora = datetime.now()
    dentro = versionado()
    if not dentro:
        print("AVISO: `git ls-files` não respondeu — o manifesto não sabe o "
              "que o Git vai guardar. Rode `git init` antes.")
        return 1

    n_dentro = tam_dentro = 0
    por_dir = {}
    for rel in sorted(dentro):
        p = RAIZ / rel
        if not p.exists():
            continue
        t = p.stat().st_size
        n_dentro += 1
        tam_dentro += t
        topo = rel.split("/")[0] if "/" in rel else "(raiz)"
        por_dir.setdefault(topo, [0, 0])
        por_dir[topo][0] += 1
        por_dir[topo][1] += t

    print("calculando sha256 dos %d arquivo(s) críticos..." % len(CRITICOS),
          flush=True)
    hashes, ausentes = {}, []
    for rel in CRITICOS:
        p = RAIZ / rel
        if not p.exists():
            ausentes.append(rel)
            continue
        hashes[rel] = {"sha256": sha256(p), "bytes": p.stat().st_size}

    banco = estado_do_banco()
    excluidos = fora_do_backup(dentro)
    nao_justificados = [e for e in excluidos if "NÃO JUSTIFICADO" in e["motivo"]]

    dados = {
        "gerado_em": agora.isoformat(timespec="seconds"),
        "estado_do_projeto": estado,
        "declaracao": declaracao,
        "raiz": str(RAIZ),
        "no_backup": {"arquivos": n_dentro, "bytes": tam_dentro,
                      "por_diretorio": {k: {"arquivos": v[0], "bytes": v[1]}
                                        for k, v in sorted(por_dir.items())}},
        "fora_do_backup": {"arquivos": len(excluidos),
                           "bytes": sum(e["bytes"] for e in excluidos),
                           "itens": excluidos},
        "arquivos_criticos": hashes,
        "criticos_ausentes": ausentes,
        "banco": banco,
    }
    SAIDA_JSON.write_text(json.dumps(dados, ensure_ascii=False, indent=1),
                          encoding="utf-8")

    L = []
    w = L.append
    w("# Manifesto do backup — %s\n" % estado)
    w("> **%s**\n" % declaracao)
    w("| | |")
    w("|---|---|")
    w("| Gerado em | %s |" % agora.strftime("%d/%m/%Y %H:%M:%S"))
    w("| Estado do projeto | **%s** |" % estado)
    w("| Arquivos no backup | **%d** |" % n_dentro)
    w("| Tamanho no backup | **%.2f MB** |" % (tam_dentro / 1024 ** 2))
    w("| Arquivos fora do backup | %d (%.2f MB) |"
      % (len(excluidos), sum(e["bytes"] for e in excluidos) / 1024 ** 2))
    w("| Gerado por | `scripts/gerar_manifesto_backup.py` |")
    w("")
    w("## 1. O que entrou, por diretório\n")
    w("| Diretório | Arquivos | Tamanho |")
    w("|---|---:|---:|")
    for k, (n, b) in sorted(por_dir.items(), key=lambda x: -x[1][1]):
        w("| `%s` | %d | %.2f MB |" % (k, n, b / 1024 ** 2))
    w("| **total** | **%d** | **%.2f MB** |" % (n_dentro, tam_dentro / 1024 ** 2))
    w("")
    w("## 2. Estado do banco\n")
    if "erro" in banco:
        w("**%s**\n" % banco["erro"])
    else:
        w("A identidade do banco **não** é o hash do arquivo `.db`: aquele muda "
          "a cada atendimento gravado, sem que um único dado de conhecimento "
          "tenha mudado. A identidade é a **impressão digital** — contagens "
          "mais o conteúdo das colunas que viram atributo, mais o hash dos "
          "arquivos de origem. É a mesma que o ML usa para dizer sobre qual "
          "dado um modelo foi treinado.\n")
        w("| | |")
        w("|---|---|")
        w("| **Impressão digital dos dados** | `%s` |" % banco["impressao_digital"])
        w("| Esquema | %d tabelas, %d views |" % (banco["tabelas"], banco["views"]))
        w("| Substâncias | %s (%s com ATC) |"
          % (banco["substancias"], banco["substancias_com_atc"]))
        w("| Interações fármaco × fármaco | %s |" % banco["interacoes"])
        w("| Registros de evidência | %s |" % banco["evidencias"])
        w("| Lotes de carga | %s |" % banco["cargas"])
        w("| Previsões gravadas | %s |" % banco["predicoes"])
        w("| **Modelos ativos** | **%s** |" % banco["modelos_ativos"])
        w("| Atendimentos · pacientes | %s · %s |"
          % (banco["atendimentos"], banco["pacientes"]))
        w("| `PRAGMA integrity_check` | **%s** |" % banco["integridade"])
        w("")
        w("### Modelos registrados\n")
        w("| Nome | Versão | Algoritmo | Status | Ativo | Semente | Versão dos dados | Limiar |")
        w("|---|---|---|---|---:|---:|---|---|")
        for m in banco["modelos"]:
            w("| %s | %s | %s | %s | %s | %s | `%s` | %s |"
              % (m["nome"], m["versao"], m["algoritmo"], m["status"],
                 m["ativo"], m["semente"], m["versao_dados"],
                 m["limiar"] if m["limiar"] is not None else "**NULL**"))
        w("")
        w("Limiar `NULL` e `ativo = 0` são o estado correto: a view de previsão "
          "é *fail-closed*, então o sistema restaurado a partir deste backup "
          "emite **zero** achados previstos, como a Fase 7 decidiu (D-041).\n")
    w("## 3. Hash dos arquivos críticos\n")
    w("sha256 do conteúdo inteiro. São os arquivos que, se divergirem, "
      "invalidam o backup.\n")
    w("| Arquivo | Bytes | sha256 |")
    w("|---|---:|---|")
    for rel, d in hashes.items():
        w("| `%s` | %s | `%s` |" % (rel, d["bytes"], d["sha256"]))
    if ausentes:
        w("")
        w("**AUSENTES:** %s" % ", ".join("`%s`" % a for a in ausentes))
    w("")
    w("## 4. O que ficou de fora — e por quê\n")
    w("Nenhum arquivo foi descartado em silêncio.\n")
    w("| Arquivo | Tamanho | Motivo | Alternativa | Impacto na reconstrução |")
    w("|---|---:|---|---|---|")
    agrupado = {}
    for e in excluidos:
        chave = ("database/conciliador_backup_*.db"
                 if "conciliador_backup_" in e["arquivo"]
                 else "`__pycache__/` (cache)" if "__pycache__" in e["arquivo"]
                 else "data/preview/*.html" if "data/preview/" in e["arquivo"]
                 else "dist/ (executável gerado)" if e["arquivo"].startswith("dist/")
                 else "build/ (intermediários do build)"
                 if e["arquivo"].startswith("build/")
                 else "conhecimento/ (banco distribuível)"
                 if e["arquivo"].startswith("conhecimento/")
                 else "backups/ (cópias do usuário)"
                 if e["arquivo"].startswith("backups/")
                 else e["arquivo"])
        g = agrupado.setdefault(chave, {"bytes": 0, "n": 0, "e": e})
        g["bytes"] += e["bytes"]
        g["n"] += 1
    for chave, g in sorted(agrupado.items(), key=lambda x: -x[1]["bytes"]):
        e = g["e"]
        nome = chave if g["n"] == 1 else "%s (%d arquivos)" % (chave, g["n"])
        w("| %s | %.2f MB | %s | %s | %s |"
          % (nome, g["bytes"] / 1024 ** 2, e["motivo"], e["alternativa"],
             e["impacto"]))
    w("")
    if nao_justificados:
        w("> **ATENÇÃO: %d arquivo(s) fora do backup SEM justificativa "
          "registrada.** O manifesto não deve ser aceito assim — acrescente a "
          "justificativa em `scripts/gerar_manifesto_backup.py` ou inclua o "
          "arquivo no backup.\n" % len(nao_justificados))
        for e in nao_justificados[:10]:
            w("> - `%s` (%.2f MB)" % (e["arquivo"], e["bytes"] / 1024 ** 2))
        w("")
    w("## 5. Como restaurar a partir daqui\n")
    w("```bash")
    w("git clone https://github.com/brilhanteJVB/Conciliador-Backup-Analise.git")
    w("cd Conciliador-Backup-Analise")
    w('PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"')
    w('PYTHONIOENCODING=utf-8 "$PY" pipeline/executar_tudo.py   # incremental: confere')
    w("```")
    w("")
    w("A carga incremental **não muda nada** se o banco restaurado estiver "
      "íntegro — é a própria definição de idempotência do projeto (D-045). "
      "Se a bateria fechar em 972 conferências com exit 0, a restauração está "
      "correta.\n")
    w("**Não rode `--recriar` para conferir:** ele apaga `modelo` e `predicao`, "
      "e as 600 previsões levaram vinte minutos de treino para existir. O "
      "conhecimento é reconstruível a partir do acervo; as previsões, não.\n")

    SAIDA_MD.write_text("\n".join(L), encoding="utf-8")
    print("\nmanifesto: %s" % SAIDA_MD.relative_to(RAIZ).as_posix())
    print("json:      %s" % SAIDA_JSON.relative_to(RAIZ).as_posix())
    print("\n%d arquivo(s) no backup, %.2f MB" % (n_dentro, tam_dentro / 1024 ** 2))
    print("%d arquivo(s) fora, %.2f MB"
          % (len(excluidos), sum(e["bytes"] for e in excluidos) / 1024 ** 2))
    if ausentes:
        print("CRITICOS AUSENTES: %s" % ausentes)
        return 1
    if nao_justificados:
        print("FORA DO BACKUP SEM JUSTIFICATIVA: %d" % len(nao_justificados))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
