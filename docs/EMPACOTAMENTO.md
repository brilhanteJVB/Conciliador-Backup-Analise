# O que o `.exe` vai precisar carregar — auditoria da Fase 9

**Data:** 10/09/2026 · levantamento, não implementação
**Estado:** a Fase 10 ainda não começou. Este documento é o inventário que ela
vai consumir.

---

## 1. A boa notícia, medida

O caminho determinístico do produto — `app/` + `rules/` — importa **três**
bibliotecas externas, e uma delas vem junto com a outra:

| | |
|---|---|
| `flask` | 3.1.3 |
| `werkzeug` | 3.1.8 (dependência do Flask) |
| `jinja2` · `click` · `itsdangerous` · `blinker` · `markupsafe` | dependências do Flask |

**`openpyxl` aparece uma vez só, em `pipeline/20_substancias.py`** — que lê a
planilha da DCB. O `.exe` distribui o banco **já construído**: não roda ETL, não
abre planilha, não toca no acervo. `openpyxl` fica fora.

**`numpy`, `scikit-learn` e `scipy` estão apenas em `ml/`.** O motor lê a view
`vw_predicao_liberada`, não carrega modelo. Isso foi decidido na Fase 8 e é
verificado por teste em três lugares (`teste_ml.py`, `fase9_v2_independente.py`
caminho F, `teste_regressao.py`). É a razão de o `.exe` poder ser leve — e a
razão de não se dever "só importar sklearn ali" em nenhuma alteração futura.

Medido também: **nenhum caminho absoluto** em `app/`, `rules/` ou `pipeline/`.
Tudo pende de `RAIZ = Path(__file__).resolve().parent.parent`. E **nenhum
arquivo de `app/` ou `rules/` lê o acervo**.

---

## 2. O que entra no pacote

| Item | Tamanho | Observação |
|---|---:|---|
| `database/conciliador.db` | **73,3 MB** | é o produto; 44 tabelas, 15 views |
| `rules/` | 0,29 MB | três módulos |
| `app/*.py` | 0,10 MB | cinco módulos |
| `app/templates/` | 0,08 MB | 13 arquivos |
| `app/static/estilo.css` | 0,01 MB | folha única, sem CDN |
| **Total de conteúdo** | **~73,8 MB** | mais o runtime Python + Flask |

**Não entram:**

- `pipeline/` — reconstrói o banco a partir do acervo, que não é distribuído;
- `ml/` — treino e medição; o `.exe` não treina nada;
- `models/*.pkl` (1,03 MB) — o motor não abre artefato de modelo;
- `data/training/dataset_m1.npz` (0,68 MB), `auditoria/`, `tests/`, `docs/`.

`models/*.json` (15 KB) só faria sentido se algum dia o `.exe` for pontuar
pares sob demanda. Hoje não é o caso; ver §6.

---

## 3. O banco precisa ser gravável — e isto decide a instalação

A aplicação **escreve** no banco: paciente, atendimento, medicamento,
posologia, conciliação, achado, anotação do profissional. `sqlite3.connect`
com `timeout=15`.

Consequência prática: **o `.exe` não pode instalar o banco em
`C:\Program Files`** e abri-lo de lá. Windows recusa escrita ali para usuário
sem elevação, e o sintoma seria `database is locked` ou `readonly database` no
meio de um atendimento.

Três caminhos possíveis, a decidir na Fase 10:

1. **Instalar tudo em `%LOCALAPPDATA%\Conciliador`** — simples, sem elevação,
   um banco por usuário do Windows.
2. **Programa em `Program Files`, banco copiado para `%LOCALAPPDATA%`** na
   primeira execução — separa binário de dado, e é o que permite atualizar o
   programa sem tocar nos atendimentos.
3. **Pasta portátil** (pendrive) — tudo junto, sem instalação.

A opção 2 é a que combina com §5 (atualização). Nenhuma delas está
implementada; hoje o caminho é fixo em `app/servicos.py:BANCO`.

Também escrevem em disco: `data/aplicacao.log` (criado por `web.py` na
importação, com `mkdir(parents=True, exist_ok=True)`). Mesmo problema, mesma
solução.

---

## 4. Configuração — a superfície inteira são duas variáveis

| Variável | Padrão | Para quê |
|---|---|---|
| `PORT` | `5000` | porta do servidor local |
| `CONCILIADOR_SECRET` | `"conciliador-local-fase6"` | assina o cookie de sessão |

**`CONCILIADOR_SECRET` tem um valor padrão fixo no código.** Numa aplicação
local, de um usuário, o cookie guarda apenas a fila de mensagens de estado — não
guarda identidade nem dado de paciente. Ainda assim, embutir um segredo
constante num binário distribuído é hábito ruim: a Fase 10 deve gerar um
segredo por instalação, na primeira execução, e guardá-lo junto do banco.

Não há arquivo de configuração. `config/` existe e está vazia.

---

## 5. Atualização — o problema real, e ele é de dados

Atualizar o programa é trivial: trocar arquivos. **Atualizar o banco não é**,
porque o mesmo arquivo guarda duas coisas de naturezas diferentes:

```
conhecimento    substancia, produto, interacao, regra, classe_atc, evidencia…
                vem do acervo, é igual para todo mundo, é substituível
atendimento     paciente, atendimento, conciliacao, achado, anotacao…
                é do usuário, é único, NÃO pode ser substituído
```

Uma versão nova do conhecimento não pode chegar sobrescrevendo o arquivo
inteiro — levaria junto os atendimentos do farmacêutico. A Fase 10 vai precisar
de um dos dois:

- **dois arquivos** (`conhecimento.db` + `atendimentos.db`, com `ATTACH`), ou
- **migração**: importar as tabelas de conhecimento novas para dentro do banco
  existente, preservando as de atendimento.

A separação já existe conceitualmente e está escrita em código: a lista
`FORA_DA_CARGA` de `tests/fase9_convergencia.py` nomeia exatamente as 17
tabelas de atendimento e ML. É o ponto de partida da migração.

Nada disso está implementado. É a maior pendência de engenharia da Fase 10 — e
é maior do que empacotar.

---

## 6. Modelo: hoje o `.exe` não carrega nenhum

Estado atual, conferido: **2 modelos registrados, 0 ativos, 0 homologados,
`limiar_alerta` NULL nos dois.** A view é fail-closed, então a aplicação
empacotada hoje produz **zero** achados previstos, e o `.exe` não precisa de
scikit-learn, de `.pkl` nem de `.json` de modelo.

Se algum dia um modelo for homologado — o que exige os rótulos humanos que a
Fase 7 mostrou faltarem —, duas coisas mudam:

1. as previsões precisam estar **gravadas em `predicao`** no banco distribuído
   (hoje há 600, de 581.201 pares pontuados: cobertura parcial, declarada);
2. **ou** o `.exe` passa a pontuar sob demanda, e aí carrega numpy + sklearn
   1.9.0 — e o manifesto do artefato já avisa que o `.pkl` está amarrado a essa
   versão exata (`models/m1_1_0-boosting.json`, campo `aviso`).

A segunda opção multiplica o tamanho e a fragilidade do pacote. A primeira
mantém o `.exe` leve. A decisão não é urgente porque não há modelo homologado.

---

## 7. Lista de verificação para a Fase 10

- [ ] escolher o local de instalação (§3) e tirar `BANCO` de caminho fixo
- [ ] separar conhecimento de atendimento, ou escrever a migração (§5)
- [ ] gerar `CONCILIADOR_SECRET` por instalação (§4)
- [ ] mover `data/aplicacao.log` para local gravável, com rotação
- [ ] congelar as versões: Python 3.12.10, Flask 3.1.3, Werkzeug 3.1.8
- [ ] decidir empacotador (PyInstaller `--onedir` é o que combina com um banco
      de 73 MB; `--onefile` extrai tudo a cada execução)
- [ ] abrir o navegador do usuário na porta escolhida, e tratar porta ocupada
- [ ] desligar o modo de depuração e o autoreload (já estão desligados)
- [ ] script de verificação pós-instalação: `90_validacao.py` roda sem o
      acervo? (**hoje não roda** — precisa ser conferido)
- [ ] o que fazer quando o banco não abre: hoje a tela mostra 503 com a
      mensagem certa (`com_banco`), mas ela manda rodar o pipeline, que o
      usuário do `.exe` não tem

O último item é o exemplo do tipo de coisa que esta auditoria existe para
achar: uma mensagem de erro correta para o desenvolvedor e inútil para quem
recebe o programa pronto.
