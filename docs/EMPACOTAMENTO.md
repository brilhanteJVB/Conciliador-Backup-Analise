# Empacotamento — Fase 10

**Data:** 10/09/2026 · Decisões **D-051** e **D-052**
**Estado:** o executável existe, foi testado fora do ambiente de
desenvolvimento e **não** exige Python na máquina do usuário.

Este documento nasceu na Fase 9 como *inventário do que seria preciso*. Agora
descreve **o que foi construído**. O guia para quem vai instalar é outro:
[GUIA_INSTALACAO.md](GUIA_INSTALACAO.md).

---

## 1. O produto

| | |
|---|---|
| Executável | `dist/SistemaConciliador/SistemaConciliador.exe` — **5,0 MB** |
| Pasta distribuível | **84 arquivos, 93,2 MB** |
| Modo | PyInstaller **`--onedir --console`** |
| Tempo de build | ~17 s |
| Python na máquina do usuário | **não é necessário** |
| Internet | **não é necessária** |
| Permissão de administrador | **não é necessária** |
| Versão | aplicação 1.0.0 · esquema 1.0 · conhecimento 2026.09.10 |

### Por que `--onedir`, e não `--onefile`

`--onefile` extrai o conteúdo inteiro para uma pasta temporária **a cada
execução**. Com 70 MB de banco, isso é copiar 70 MB toda vez que o
farmacêutico abre o programa — segundos de espera no balcão, por nada. Além
disso:

| | `--onedir` | `--onefile` |
|---|---|---|
| trocar o conhecimento sem regerar o `.exe` | **sim** | não |
| diagnosticar quando falha | arquivos estão lá | temporário já sumiu |
| tempo de partida | imediato | extrai 93 MB antes |
| falso positivo de antivírus | menor | auto-extrator de 70 MB é o perfil clássico |

A capacidade de trocar `conhecimento/conhecimento.db` sem reconstruir o
programa é **requisito da fase**, não conveniência. Isso decidiu sozinho.

### Por que console, e não janela

`--console`. Um programa local de apoio clínico precisa poder dizer o que deu
errado; `--noconsole` engole toda a saída e um erro de partida vira uma janela
que pisca e some. O console também mostra, a cada abertura, o endereço, a
versão do conhecimento, o estado do ML e a limitação clínica.

---

## 2. Onde cada coisa vive

Dois lugares, e eles não se misturam — `app/caminhos.py` é o único módulo que
decide isso.

```
RECURSOS  (somente leitura, vem com o programa)
SistemaConciliador/
├── SistemaConciliador.exe
└── _internal/
    ├── conhecimento/conhecimento.db      70,1 MB — a semente
    ├── conhecimento/conhecimento.json    manifesto: sha256, versão, conteúdo
    ├── app/templates/  ·  app/static/
    ├── models/*.json                     manifestos, para rastreabilidade
    ├── docs/GUIA_INSTALACAO.md
    └── (runtime Python + Flask)

DADOS  (gravável, do usuário, sobrevive à reinstalação)
%LOCALAPPDATA%\ConciliadorMedicamentos\
├── database/conciliador.db               o banco EM USO
├── data/aplicacao.log
├── backups/conciliador_AAAAMMDD_HHMMSS.db
└── config/sessao.chave
```

`CONCILIADOR_DADOS` redefine a pasta de dados — instalação portátil, teste, ou
um disco escolhido pelo farmacêutico.

**Em desenvolvimento os dois apontam para a raiz do repositório.** Deliberado:
as conferências da bateria rodam sobre os mesmos caminhos de sempre, e
empacotar não pode mudar o que elas medem.

### A pendência da Fase 9, resolvida

O banco **não** vive mais junto do programa. Se a pasta de dados não aceitar
gravação, o programa **recusa abrir** com uma mensagem que diz o que fazer —
em vez de abrir e falhar no meio de um atendimento com `readonly database`.

---

## 3. A arquitetura de dados — um arquivo, e o porquê

A Fase 9 apontou: conhecimento e atendimento no mesmo arquivo impediriam
atualizar um sem destruir o outro. A solução **não** foi separar os arquivos.
Foi medir primeiro:

| | |
|---|---:|
| chaves estrangeiras que cruzam a fronteira | **8** |
| direção | todas atendimento → conhecimento |
| views que cruzam | **0** |

**O SQLite não aplica chave estrangeira entre arquivos diferentes.** Separar
desligaria as oito — e justamente a que a atualização mais precisa: saber que
um atendimento antigo aponta para uma substância que a versão nova não tem
mais. Ver **D-051**.

Então: um arquivo em uso, e a separação acontece na **atualização**.

```
conhecimento novo (intocado)  +  atendimento do usuário  →  banco novo
```

`app/atualizacao.py`, cinco passos, nessa ordem:

1. **conferir o arquivo novo** — corrompido, incompatível ou com dados de
   paciente dentro para aqui;
2. **backup** — antes de qualquer escrita, sempre;
3. **montar num arquivo temporário** — o banco em uso não é tocado;
4. **conferir o resultado** — `foreign_key_check`, `integrity_check`, e
   contagem linha a linha das 16 tabelas de atendimento;
5. **trocar** — só depois de tudo conferido.

Falhou em qualquer passo, o banco em uso continua exatamente como estava.

---

## 4. A identidade do banco (D-052)

Tabela `propriedade`, preenchida por `pipeline/80_identidade.py`:

| Chave | Valor hoje |
|---|---|
| `conhecimento.versao` | `2026.09.10` |
| `conhecimento.digital` | `9e9c85ee3ffea5e0` |
| `conhecimento.gerado_em` | carimbo da carga |
| `esquema.versao` | `1.0` |

A impressão digital é **a mesma que o ML usa** — não o hash do arquivo `.db`,
que muda a cada atendimento gravado sem que um dado de conhecimento mude.
`esquema.versao` é o que a atualização compara para aceitar ou recusar.

Esquema: 44 → **45 tabelas**.

---

## 5. Dependências — e o que ficou de fora

O que o produto importa, medido lendo os `import` de `app/` e `rules/`:

| | |
|---|---|
| `flask` 3.1.3 | e o que vem com ele (werkzeug, jinja2, click, itsdangerous, blinker, markupsafe) |
| Python 3.12.10 | **embutido no pacote** |
| SQLite | da biblioteca padrão |

**Excluído do pacote, explicitamente:** `numpy`, `scipy`, `sklearn`, `pandas`,
`matplotlib`, `PIL`, `tkinter`, `openpyxl`, `PyInstaller`. E as pastas
`pipeline/`, `ml/`, `tests/`, `auditoria/`.

Isso só é possível porque o motor **lê a view `vw_predicao_liberada`**, não
carrega modelo (Fase 8). É a decisão que mantém o pacote em 93 MB em vez de
400 MB — e ela é verificada por teste em três lugares.

Nenhum `.pkl` viaja. Os `*.json` de modelo vão, pequenos, só para
rastreabilidade.

---

## 6. O ML dentro do executável

Estado no banco distribuído, conferido por consulta direta:

| | |
|---|---:|
| modelos registrados | 2 |
| **modelos ativos** | **0** |
| status | ambos `EXPERIMENTAL` |
| `limiar_alerta` | **NULL** nos dois |
| `vw_predicao_liberada` | **0 linhas** |
| achados de origem `MODELO` | **0** |

O `.exe` **não pode** ativar um modelo: a view é *fail-closed* e o `CHECK` do
esquema recusa `ativo=1` sem `status='HOMOLOGADO'`. Homologar continua sendo
ato humano registrado. A instalação funciona normalmente com o ML desligado —
é o estado esperado, não uma limitação temporária.

---

## 7. Verificação

| | Conferências |
|---|---:|
| **V1** `tests/fase10_empacotamento.py` — o `.exe` usado como um usuário o usaria | **85** |
| **V2** `tests/fase10_v2_independente.py` — inspeção por fora | **63** |
| Bateria completa (`pipeline/executar_tudo.py`) | **1.123**, exit 0 |
| Convergência do pipeline | 46, exit 0 |

A V1 **não importa o código da aplicação**: inicia o `.exe` como processo,
conversa por HTTP, encerra, reabre. A V2 não executa o fluxo: olha os
arquivos, o banco por SQLite direto, o processo e o ambiente.

O caminho D da V2 roda o executável com **PATH podado e sem `PYTHONPATH`,
`PYTHONHOME` ou `PYTHONSTARTUP`** — prova de que ele não depende do ambiente
de desenvolvimento.

---

## 8. Backup

Simples de propósito.

- **Onde:** `%LOCALAPPDATA%\ConciliadorMedicamentos\backups\`
- **Quando:** automaticamente, antes de toda atualização de conhecimento;
  manualmente, copiando `database/conciliador.db` com o programa fechado.
- **Como restaurar:** fechar o programa e colocar o arquivo de volta.
- **Contra sobrescrita acidental:** o nome carrega data e hora
  (`conciliador_AAAAMMDD_HHMMSS.db`), então nenhum backup apaga outro; e a
  primeira execução **nunca** sobrescreve um banco existente.

---

## 9. Logs

`%LOCALAPPDATA%\ConciliadorMedicamentos\data\aplicacao.log`. Registra início
(versão, porta, banco), erros técnicos com rastreamento, e falhas ao servir.

**Não registra nome de paciente** — conferido por teste (V1, eixo 6.8c). O
programa nunca fecha em silêncio: toda falha vira mensagem na tela, o detalhe
vai para o log, e a janela espera.

`SistemaConciliador.exe --diagnostico` imprime onde cada coisa está, se o
banco abre e qual a versão do conhecimento, e sai sem subir o servidor.

---

## 10. O que ainda não existe

- **Instalador.** A distribuição é copiar uma pasta. Um `.msi` ou um
  instalador Inno Setup criaria atalho no Menu Iniciar e entrada em
  "Adicionar ou remover programas". Não é necessário para usar.
- **Ícone próprio.** O executável usa o ícone padrão do PyInstaller.
- **Assinatura digital.** Sem ela, o SmartScreen do Windows avisa na primeira
  execução. Assinar exige certificado pago.
- **Atualização automática.** A atualização de conhecimento existe e é
  validada, mas é acionada por comando — **de propósito**: um atualizador
  automático não validado seria pior do que nenhum.
- **Empacotamento para Linux ou macOS.** Fora de escopo.

---

## 11. Como reconstruir

```bash
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"

PYTHONIOENCODING=utf-8 "$PY" scripts/preparar_conhecimento.py   # o banco
PYTHONIOENCODING=utf-8 "$PY" scripts/build_exe.py --limpar      # o .exe
PYTHONIOENCODING=utf-8 "$PY" tests/fase10_empacotamento.py      # V1
PYTHONIOENCODING=utf-8 "$PY" tests/fase10_v2_independente.py    # V2
```

Requer `pyinstaller` (6.22.2). `dist/`, `build/` e `conhecimento/` não vão
para o repositório: são reconstruídos por esses dois scripts.

---

## 12. O que o empacotamento **não** significa

> Um programa empacotado e operacional **não é um sistema clinicamente
> validado**. Nenhum achado deste sistema foi revisado por farmacêutico,
> nenhum modelo preditivo está homologado, e a decisão clínica permanece do
> profissional.

Essa frase está no console a cada abertura, no guia de instalação e na
interface. **Não a remova.**
