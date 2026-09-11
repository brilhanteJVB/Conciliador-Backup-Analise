# Arquitetura

**Data:** 09/09/2026 · Arquitetura própria, escrita do zero.

---

## 1. Camadas

Cada camada só conhece a de baixo. Nenhuma consulta pula uma camada.

| # | Camada | Onde | Responsabilidade |
|---|---|---|---|
| 1 | Interface | `app/` | Coleta guiada, checklist, autocomplete, relatório |
| 2 | Paciente | `database/` (tabelas `paciente*`, `atendimento*`) | Anamnese, farmacoterapia, posologia, horários |
| 3 | Base farmacológica | `database/` (tabelas de conhecimento) | Substância, produto, interação, regra, reação |
| 4 | Motor de regras | `rules/` | 12 módulos determinísticos |
| 5 | Machine Learning | `ml/` · `models/` | Priorização de curadoria; nunca decisão, nunca alerta (Fase 7, D-041) |
| 6 | Evidência | tabelas `fonte`, `evidencia` | Rastreabilidade de toda afirmação |
| 7 | Relatório | `reports/` | Saída priorizada e explicável |
| 8 | Persistência | SQLite local | Offline, arquivo único |

**Escolha do banco: SQLite.** DuckDB é melhor em análise colunar, mas aqui a carga é transacional (uma sessão de atendimento por vez, dezenas de linhas), o requisito é arquivo único embutido no `.exe`, e SQLite tem `CHECK` e `FOREIGN KEY` maduros — que é onde as invariantes vivem. DuckDB fica disponível para o ETL, se a carga de 1 milhão de linhas do VigiMed pedir.

---

## 2. Pipeline

```
fontes_novas/ · DDInter · DrugBank · VigiMed · bulas   (acervo, somente leitura)
        │
        ▼  pipeline/10_* extração — copia e converte, nunca altera a origem
   data/raw/
        │
        ▼  pipeline/20_* normalização — lib_norm, esqueleto fonético PT↔EN
   data/normalized/
        │
        ▼  pipeline/30_* carga — com origem e evidência em toda linha
   database/conciliador.db
        │
        ▼  pipeline/90_validacao.py — falha ruidosamente se invariante quebrar
```

Numeração dita a ordem. Cada script é idempotente ou declara por que não é.

---

## 3. Motor de regras — 12 módulos

Determinístico, sem ML. Entrada: um `atendimento`. Saída: linhas em `achado` e em `nao_avaliado`.

| # | Módulo | Fonte da regra |
|---|---|---|
| 1 | Fármaco × Fármaco | `vw_interacao_liberada` |
| 2 | Fármaco × Doença | `interacao_doenca` (com campo `relacao`) |
| 3 | Fármaco × Alergia | `paciente_alergia` + classe ATC |
| 4 | Fármaco × Alimento | `interacao_item` |
| 5 | Fármaco × Planta/chá | `interacao_item` tipo planta |
| 6 | Fármaco × Suplemento | `interacao_item` tipo suplemento/mineral |
| 7b | **Fármaco × CYP** | `papel_farmacocinetico` (FDA) — **inferência mecanística**, nunca documento |
| 7 | Fármaco × Hábito | `interacao_habito` (tabaco, álcool, cafeína) |
| 8 | Duplicidade terapêutica | ATC **4º nível** igual (o 5º *é* a substância — D-028) |
| 9 | Reação adversa | `substancia_reacao_adversa` com sinal |
| 10 | **Regra de administração** | `vw_regra_administracao_liberada` |
| 11 | **Conflito de horário** | `vw_regra_separacao_liberada` + `horario_administracao` |
| 12 | Complexidade do esquema | contagem de horários distintos |
| 13 | **Fármaco × Fármaco PREVISTO** | `vw_predicao_liberada` — **previsão de modelo, nunca documento** (Fase 8, D-046) |

**Toda mensagem de estado da interface é presa ao atendimento que a gerou**
(`web.avisar` / `mensagens_da_tela`, Fase 9, D-049). A fila do Flask é da
sessão do navegador: sem isso, a confirmação de um paciente aparecia na tela de
outro. **E a probabilidade de uma previsão é escrita por um formatador único**
(`rules/_prioridade.percentual_previsao`, D-050) — nenhum template, relatório ou
módulo formata percentual por conta própria, e probabilidade calibrada saturada
nunca sai como "100%".

Os módulos 10 e 11 são o que o sistema anterior não tinha.

### 3.0 O módulo 13 não é como os outros

Os módulos 1 a 12 afirmam o que uma fonte afirma. O 13 afirma o que um **modelo
estima**, e por isso está separado em tudo: lê `vw_predicao_liberada` (que já
aplica as quatro travas de D-046), não gera evidência, tem teto de prioridade
`INFORMATIVO`, e **não importa nada de `ml/`** — o modelo escreve em `predicao`,
o motor lê uma view, e a camada de regras continua sem dependência de
scikit-learn. Com nenhum modelo ativo, o módulo não produz nada.

### 3.1 Motor de horários

Único módulo com lógica temporal própria:

1. Monta a linha do dia a partir de `horario_administracao` e `rotina_refeicao`.
2. Para cada medicamento com `regra_administracao`, verifica se o horário respeita a relação com a refeição mais próxima.
3. Para cada par com `regra_separacao`, calcula a distância entre horários.
4. Emite `CONFLITO_HORARIO` quando a distância é menor que `intervalo_horas`.
5. **Quando `intervalo_horas` é NULL**, emite achado `POSSIVEL` dizendo que há necessidade de separação com intervalo não estabelecido — e registra em `nao_avaliado` com motivo `REGRA_SEM_INTERVALO_ESTABELECIDO`.

O motor **nunca reescreve o horário do paciente**. Sugere, e a sugestão é marcada `definido_por='SUGERIDO_PELO_SISTEMA'`.

### 3.2 Do módulo ao achado

Todo módulo termina no mesmo lugar: uma linha de `achado`. Nenhum deles fala com
a interface, e a interface não fala com nenhum deles.

```
paciente → contexto → 12 módulos → achados → agrupamento → prioridade → interface
```

`rules/motor_conciliacao.py` expõe **uma** função pública,
`conciliar_atendimento(con, atendimento_id)`, no mesmo padrão de
`montar_agenda`. Ele **consome** o motor de horários da Fase 4 em vez de
reimplementá-lo: regra temporal continua pertencendo àquele motor;
classificação, contexto, agrupamento e prioridade pertencem a este.

O achado tem **seis eixos que não se fundem**: `gravidade_fonte` (o que a fonte
diz), `confianca_sistema` (o quanto o sistema confia), `prioridade` (em que
ordem mostrar), `natureza` (epistemologia da afirmação), `classificacao`
(detecção neste paciente) e `status_informacao` (procedência e revisão). Os
`CHECK` do esquema impedem que previsão se disfarce de fato e que extração
automática se apresente como revisada.

**Agrupamento preserva evidência.** Achados que compartilham `grupo_chave` viram
um alerta só; o representante recebe as evidências dos absorvidos, e os
absorvidos continuam gravados com `status='AGRUPADO'`. A view
`vw_achado_clinico` expõe só os representantes — a tabela guarda tudo.

**Conflito entre fontes não é resolvido em silêncio.** Duas fontes graduando o
mesmo par de forma diferente produzem `natureza='CONFLITANTE'`, as duas
evidências marcadas `DIVERGE`, e a ordenação pela mais grave — a única escolha
cujo risco não é assimétrico.

### 3.3 Prioridade ≠ gravidade

`gravidade_fonte` é propriedade farmacológica do par e vem da fonte. `prioridade` (CRÍTICO → INFORMATIVO) é de exibição e combina gravidade, evidência e contexto do paciente. São colunas separadas porque respondem perguntas diferentes.

**A fórmula foi escrita na Fase 5 e vive em `rules/_prioridade.py`**: uma tabela `(módulo, chave) → (prioridade, por quê)`, 33 linhas, cada uma com a justificativa ao lado — texto que vai para o campo `justificativa_prioridade` do achado, de modo que o farmacêutico leia o motivo e não só o rótulo. Três modificadores, e só três: anafilaxia declarada força CRÍTICO; informação insuficiente limita a INFORMATIVO; confiança baixa rebaixa um degrau (exceto na alergia, que não depende de fonte externa).

**Idade não entra na fórmula.** Sem Beers ou STOPP/START carregados não há base para afirmar inadequação em idoso; a idade é exibida no contexto do achado e o motor declara a limitação. Ver D-027.

---

## 4. Machine Learning

**Fase 7 executada em 09/09/2026. Relatório completo em [ML_FASE7.md](ML_FASE7.md);
tabela de comparação em [ML_COMPARACAO.md](ML_COMPARACAO.md).** O que segue é o
resumo arquitetural — os números, o porquê de cada corte e onde o ML encosta no
resto do sistema.

### 4.1 O que foi medido antes de escolher o alvo

A avaliação preliminar da tabela abaixo era uma previsão. A auditoria da Fase 7
confirmou quatro linhas e mudou uma.

| Modelo | Alvo | Origem do alvo | Medido | Viável? |
|---|---|---|---|---|
| **M1 — existe interação?** | binário | DDInter + `db_drug_interactions` | 94.770 pares · prevalência 20,7% | **Sim — treinado** |
| M2 — tipo de interação | PK/PD | regex sobre a descrição | 52.261 pares, uma fonte só | **Secundário, declarado** |
| M3 — gravidade | ordinal | DDInter `Level` | 38.459 de 94.770 graduados; **um único graduador**, logo consistência imensurável | **Não** — D-015 mantida |
| M4 — reação adversa | binário | VigiMed | 0 (fonte não carregada) | Não, nesta fase |
| M5 — relevância do alerta | binário | avaliação de farmacêutico | **0 anotações** | **Não** — a tabela existe e está vazia |

### 4.2 Protocolo — e por que ele muda tudo

**Split por fármaco, não por par**, estratificado por decil de grau. O split por
fármaco parte o teste em três regimes, e o que decide é o mais duro:

| Regime | Pares | AUC do modelo escolhido |
|---|---:|---:|
| POR_PAR (protocolo da literatura) | 68.617 | **0,9442** |
| POR_FARMACO — um lado inédito | 116.402 | 0,7887 |
| POR_FARMACO — **FRIO_FRIO**, dois lados inéditos | 10.153 | **0,7392** |

A diferença entre 0,944 e 0,738 é **inteira de protocolo**. Reportar só a
primeira seria comparável à literatura e falso sobre o uso real.

### 4.3 O grafo saiu do modelo, e isso foi medido

Os atributos derivados do grafo de interações (grau, vizinhos comuns, Jaccard,
Adamic-Adar) são contagem de arestas — ou seja, de rótulos positivos —
disfarçada de atributo. Com eles:

- fármaco conhecido: AUC 0,944;
- fármaco inédito: AUC **0,3416, pior que o acaso**;
- heurística de grafo pura em FRIO_FRIO: AUC **0,5000 exata** — não existe um
  único vizinho em comum a explorar.

**Sobre GNN, a pergunta obrigatória foi respondida antes de qualquer treino:**
1.137 das 2.094 substâncias têm grau zero, e entre as 957 conectadas o grafo é
denso (20,7% dos pares possíveis já são aresta) com componente única. Onde há
estrutura, quase todos são vizinhos de quase todos; onde o projeto é cego, não
há aresta para propagar. Ver **D-038**.

O espaço publicado tem **130 atributos** (ATC 102 · REG 10 · ADM 11 · PK 7), e
`tests/teste_ml.py` reprova se algum atributo de grafo voltar.

### 4.4 O modelo escolhido, e por que ele não vira alerta

`HistGradientBoostingClassifier`, 130 atributos, AUC FRIO_FRIO **0,7392**
[0,7270 ; 0,7504], calibração isotônica (ECE 0,0223 → 0,0118).

No ponto de F1 máximo desse regime: **precisão 0,392, recall 0,556**. Quase
metade das interações documentadas passaria batido e seis em cada dez avisos
seriam falsos — o que a especificação §19 proíbe. Mas a precisão no topo 1% da
lista é **0,80** contra 0,204 de linha de base.

Daí a decisão da fase (**D-041**): o modelo **não gera achado**; ele **prioriza
uma fila de curadoria** (`reports/fila_curadoria_m1.csv`, 581.201 pares
pontuados). Os dois modelos registrados — `1.0-boosting` e a referência
interpretável `1.0-logistica` — ficam `EXPERIMENTAL` e `ativo = 0`.

### 4.5 Onde o ML encosta no resto do sistema

```
rules/  e  app/   NÃO importam nada de ml/         (verificado no código-fonte)
ml/70_predizer.py  é a porta única:
      prever(con, pares)        -> Previsao (probabilidade + explicação)
      contrato_achado(previsao) -> campos de `achado`, ou ModeloNaoHomologado
      gravar_predicoes(...)     -> escreve em `predicao`, nunca em `achado`
```

Quatro travas estruturais, todas no esquema e todas testadas:

- `predicao.gravidade_sugerida` tem `CHECK (... IS NULL)` — **ML nunca gradua**;
- `achado.natureza='PREVISTO'` exige `probabilidade_modelo` **e**
  `origem_afirmacao LIKE 'predicao.%'` — previsão é rastreável até o modelo;
- `PREVISTO` não aceita nível de evidência de publicação;
- índice único parcial de **um modelo ativo por problema**, mais
  `CHECK (ativo = 0 OR status = 'HOMOLOGADO')` — modelo não é trocado em
  silêncio, e homologar é ato humano.

`modelo` guarda semente, versão dos dados, espaço de atributos e limitações em
português — o que um terceiro precisa para repetir o experimento (**D-042**).

### 4.6 A limitação que ordena todas as outras

O rótulo negativo é **presumido**: as fontes listam o que afirmam e nunca
afirmam ausência. O modelo estima a probabilidade de o par **estar documentado**
nas bases carregadas, não de o par ser perigoso — e a explicabilidade confirma:
o atributo mais importante é "este fármaco tem regra de administração
cadastrada", isto é, *quão estudado ele é*. Ver **D-040** e ML_FASE7.md §10.

---

## 5. NLP

Aplicado às bulas, para extrair regra de administração, contraindicação e reação adversa. Toda extração entra com `metodo_extracao='NLP'` e `status_revisao='PENDENTE'`, e as views não a deixam chegar à tela sem revisão. NLP propõe; pessoa aprova.

---

## 6. Aplicação local e `.exe`

Interface web local (Flask) servida em `127.0.0.1`, empacotada com PyInstaller em `ConciliadorMedicamentos.exe`. Justificativa: o banco é SQLite, os modelos são JSON, e nada depende de rede — a arquitetura já é offline. Electron e Tauri acrescentariam um runtime inteiro para exibir a mesma tela.

**Atualização independente:** banco, regras e modelos ficam fora do executável, em `dados/`, com versão própria. Atualizar a base de interações não exige recompilar o aplicativo.

---

## 7. Ordem de construção

Numeração alinhada com a do plano do projeto. **A aplicação começa na Fase 6.**

| Fase | Entrega | Estado |
|---|---|---|
| 1 | Estrutura, modelo de dados, esquema | **Concluída** |
| 2 | Pipeline de carga e normalização | **Concluída** |
| 3 | Regras de administração e separação | **Concluída** |
| 4 | Motor de horários | **Concluída** |
| 5 | Motor de conciliação (12 módulos) + interações | **Concluída** |
| 6 | **APLICAÇÃO DO FARMACÊUTICO** | **Concluída** |
| 7 | **Machine Learning** | **Concluída** |
| 8 | **Testes integrados + integração do modelo** | **Concluída** |
| 9 | **Validação do sistema inteiro** | **Concluída — APTO PARA EMPACOTAMENTO** |
| 10 | Empacotamento `.exe` | **próxima** |

A Fase 9 auditou o produto inteiro em vez de repetir o teste de cada módulo:
dez cenários clínicos do início ao relatório, isolamento entre pacientes,
persistência conferida por outro processo, recálculo, convergência do pipeline,
integridade do modelo e do acervo, resiliência, interface e desempenho. Bateria
completa: **972 conferências, 0 falhas**. Quatro defeitos reais, todos de
costura entre módulos, corrigidos e travados por regressão — ver
[FASE9_VALIDACAO.md](FASE9_VALIDACAO.md), decisões **D-049** e **D-050**.
O que a Fase 10 vai precisar carregar está inventariado em
[EMPACOTAMENTO.md](EMPACOTAMENTO.md).

### 7.1 O que a Fase 6 entrega

A aplicação inteira de atendimento, não um protótipo:

tela inicial · identificação do paciente · anamnese por checklist · condições
clínicas · alergias · hábitos · busca de medicamento com autocompletar ·
adicionar / editar / remover · posologia estruturada (dose, unidade,
frequência, intervalo, via, duração) · horários · relação com alimentação ·
chás, plantas e suplementos · execução da conciliação · alertas priorizados
com explicação · relatório final.

### 7.2 Por que na 6, e não antes nem depois

A interface é uma casca sobre serviços. Construí-la antes das Fases 3–5
produziria telas que não têm o que mostrar: sem regra de administração não há
o que exibir no campo "tomar em jejum"; sem motor de horários a agenda não
detecta conflito; sem motor de conciliação o botão "Conciliar" não responde.

Ela também **não** vai para o fim: entra imediatamente depois dos três motores
e **antes** do Machine Learning, dos testes integrados e do empacotamento.
Quando a Fase 6 terminar, o sistema já é usável no balcão — o ML da Fase 7
melhora a ordenação dos alertas, não habilita o atendimento.

### 7.3 O que a Fase 6 entregou, medido

Tudo do §7.1, com uma correção de rota: `docs/ARQUITETURA.md` previa três
serviços e só dois existiam — `buscar_medicamento` foi construído nesta fase.

A arquitetura de quatro camadas está descrita em [APLICACAO.md](APLICACAO.md),
e três invariantes dela são **verificadas lendo o código-fonte**: a interface
não contém SQL, nenhum template calcula prioridade ou gravidade, e os serviços
chamam os motores em vez de reimplementá-los. Além disso, o eixo 1 da
verificação independente compara a página exibida com `conciliar_atendimento`
chamado diretamente, achado a achado — se a tela produzisse resultado próprio,
os dois divergiriam.

### 7.4 Como reduzo o risco de a interface ficar para trás

As Fases 3–5 entregam **serviços**, não só tabelas. Cada motor nasce com uma
função de entrada única e testável (`buscar_medicamento`, `montar_agenda`,
`conciliar`), de modo que a Fase 6 seja só a camada de tela chamando serviços
que já funcionam e já têm teste. Isso encurta a Fase 6 e impede que ela vire
"reescrever a lógica dentro da tela".
