# A aplicação do farmacêutico — arquitetura da Fase 6

**Data:** 09/09/2026

Este documento é a análise arquitetural exigida antes de escrever a aplicação,
e depois vira a referência de como ela funciona.

---

## 1. Análise do que já existe

Levantado antes de criar qualquer arquivo.

| | |
|---|---|
| **Linguagem** | Python 3.12.10, sem framework de teste (todo teste é `python arquivo.py`) |
| **Dependências** | `flask 3.1.3`, `chardet`, `pypdf`, `openpyxl`, `numpy` — já instaladas |
| **Banco** | SQLite, `database/conciliador.db`, 43 tabelas, 14 views, 76 MB |
| **Execução** | `pipeline/executar_tudo.py` reconstrói tudo e roda as verificações em ~33 s |
| **`app/`** | **vazio** — a Fase 6 é a primeira a escrever aqui |

### 1.1 Funções públicas já validadas

```
rules/motor_horarios.montar_agenda(con, atendimento_id)         -> Agenda
rules/motor_conciliacao.conciliar_atendimento(con, aid, persistir=False)
                                                                -> ResultadoConciliacao
```

`Agenda` → `.eventos` · `.conflitos` · `.nao_avaliado` · `.rotina`
`ResultadoConciliacao` → `.resumo` · `.achados` · `.achados_agrupados` ·
`.divergencias` · `.conciliados` · `.nao_conciliados` · `.conflitos` ·
`.nao_avaliado` · `.limitacoes` · `.indicadores` · `.agenda`

### 1.2 O serviço que **faltava**

`docs/ARQUITETURA.md` §7.3 previa três serviços — `buscar_medicamento`,
`montar_agenda`, `conciliar`. Os dois últimos existiam; **`buscar_medicamento`
não existia**. Sem ele, a interface teria de montar consultas SQL nas telas,
que é exatamente o que a especificação proíbe. Foi construído nesta fase, como
serviço testável fora do Flask.

---

## 2. Decisão: o que reutilizar, criar e adaptar

### Reutilizado sem tocar

- os dois motores e seus contratos (nenhuma assinatura mudou);
- `rules/_prioridade.py` — a aplicação **lê** a escala e os rótulos, e nunca
  calcula prioridade;
- `pipeline/_comum.conectar()` e `BANCO`;
- `pipeline/normalizacao.skeleton` — o mesmo esqueleto fonético que uniu as
  fontes une agora o que o farmacêutico digita;
- o esquema inteiro e as 14 views.

### Criado

| Arquivo | Camada | O que faz |
|---|---|---|
| `app/busca.py` | serviço | o terceiro ponto de entrada: `buscar_medicamento`, `buscar_condicao`, `buscar_item`, `buscar_substancia` |
| `app/servicos.py` | serviço | tudo que **escreve** no atendimento, e a orquestração da análise |
| `app/relatorio.py` | serviço | monta o relatório estruturado a partir do resultado do motor |
| `app/web.py` | interface | Flask: rotas, validação de entrada, render |
| `app/templates/` | interface | as telas |
| `app/static/estilo.css` | interface | folha de estilo única |

### Adaptado

- `pipeline/executar_tudo.py` — os testes novos entraram na lista;
- `docs/STATUS.md`, `CLAUDE.md`, `docs/ARQUITETURA.md`.

### Contratos que **não** mudam

1. A interface não reimplementa regra farmacológica nenhuma.
2. Prioridade vem do motor. A tela escolhe a cor, nunca o nível.
3. A tela nunca preenche gravidade, confiança ou intencionalidade.
4. Ausência de dado é exibida como ausência, nunca preenchida com um padrão.

---

## 3. As quatro camadas

```
INTERFACE   app/web.py + templates      rotas, formulários, render
    ↓
SERVIÇOS    app/servicos.py             escreve o atendimento, orquestra
            app/busca.py                busca tolerante
            app/relatorio.py            monta o relatório
    ↓
MOTORES     rules/motor_horarios.py     agenda e conflitos de horário
            rules/motor_conciliacao.py  os 12 módulos, achados, prioridade
    ↓
BANCO       database/conciliador.db
```

**Nenhuma camada pula outra.** `web.py` não tem uma linha de SQL clínico: todo
`SELECT` sobre conhecimento farmacológico está em `busca.py` ou dentro dos
motores. `web.py` só faz `INSERT`/`UPDATE` através de `servicos.py`.

**Regra de ouro da fase, verificada por teste:** o resultado exibido na tela é
byte a byte o mesmo que `conciliar_atendimento` devolve quando chamado
diretamente. A verificação independente compara os dois.

---

## 4. Fluxo do usuário

Sete etapas, na ordem da anamnese de balcão. O profissional pode ir e voltar
entre elas a qualquer momento; nada se perde.

| # | Etapa | Rota | O que coleta |
|---|---|---|---|
| 1 | Paciente | `/atendimento/<código>/paciente` | nome, nascimento, sexo, peso, altura, observação |
| 2 | Condições e alergias | `/atendimento/<código>/anamnese` | condições clínicas (busca), alergias (busca), hábitos |
| 3 | Medicamentos | `/atendimento/<código>/medicamentos` | busca por nome, princípio ativo, marca ou código de barras; lista de origem |
| 4 | Posologia | `/atendimento/<código>/posologia/<id>` | dose, unidade, frequência, intervalo, via, duração, datas, horários, PRN |
| 5 | Rotina | `/atendimento/<código>/rotina` | acordar, dormir, cinco refeições, trabalho, escola |
| 6 | Alimentos, suplementos e plantas | `/atendimento/<código>/itens` | três seções separadas, cada uma com busca própria |
| 7 | Conciliação | `/atendimento/<código>/conciliacao` | prescrito × relatado, lado a lado |
| — | **Analisar** | `/atendimento/<código>/analisar` | chama `conciliar_atendimento(persistir=True)` |
| — | Resultados | `/atendimento/<código>/resultados` | achados por prioridade, filtros, não avaliados, limitações |
| — | Achado | `/atendimento/<código>/achado/<id>` | os seis eixos, a cadeia de evidência, as fontes |
| — | Relatório | `/atendimento/<código>/relatorio` | documento do atendimento, pronto para imprimir |

O painel lateral mostra sempre o que **falta** para a análise ser útil, sem
bloquear ninguém: um atendimento sem rotina informada roda, e o motor declara
o que não conseguiu avaliar por causa disso.

---

## 5. O serviço de busca

`buscar_medicamento(con, termo)` responde em quatro passes, do mais
determinístico ao mais tolerante — a mesma ordem do reconhecimento do acervo:

1. **Código de barras** — se o termo é só dígito e tem 8, 12, 13 ou 14 deles,
   vai direto em `apresentacao_ean`. Determinístico, confiança ALTA.
2. **Chave normalizada exata** — o esqueleto fonético do termo bate com o de
   uma substância ou sinônimo. Confiança ALTA.
3. **Prefixo da chave normalizada** — para o autocompletar enquanto se digita.
   Confiança MÉDIA.
4. **Nome comercial** — `LIKE` sobre `produto.nome_comercial`, trazendo
   apresentação, concentração, forma e empresa. Confiança MÉDIA.

Cada resultado diz **de onde veio** e **com que confiança**, e a tela mostra
isso. Um medicamento adicionado sem vínculo com substância entra com
`reconhecimento='NAO_RECONHECIDO'`, e o motor o declara em `nao_avaliado` —
nunca é silenciosamente descartado.

---

## 6. Como executar

```bash
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"
PYTHONIOENCODING=utf-8 "$PY" app/web.py
```

Sobe em `http://127.0.0.1:5000` (respeita a variável `PORT`). Offline: o banco
é um arquivo local e nada depende de rede.

**Cuidado com o preview do editor.** O acervo tem um `.claude/launch.json` com
uma configuração chamada `conciliador` que aponta para o sistema **antigo**. A
deste projeto chama-se **`conciliador-fase6`**. Se a tela que abrir tiver
"Avaliação dos casos" e "2097 substâncias", é o sistema antigo — o acervo é
somente leitura e não pode ser alterado para resolver isso.

Testes da aplicação:

```bash
PYTHONIOENCODING=utf-8 "$PY" tests/teste_aplicacao.py        # V1 funcional
PYTHONIOENCODING=utf-8 "$PY" tests/verificacao_aplicacao.py  # V2 independente
PYTHONIOENCODING=utf-8 "$PY" tests/teste_ponta_a_ponta.py    # atendimento completo
```

---

## 7. Limitações da aplicação

Registradas aqui porque a tela não deve escondê-las:

- **Um atendimento por vez, sem autenticação.** É uma aplicação local de balcão,
  servida em `127.0.0.1`. Não há usuários, senhas nem permissões — e não deve
  haver antes de existir requisito real para isso.
- **A revisão do achado é anotação, não assinatura.** O profissional pode
  marcar um achado como revisado e escrever uma observação; isso não é
  assinatura digital nem prescrição.
- **O relatório é HTML pronto para impressão**, não PDF assinado.
- **Nada de ML.** Não há score, porcentagem nem botão de IA. A coluna
  `origem_achado` existe e vale `REGRA` em 100% dos achados.
