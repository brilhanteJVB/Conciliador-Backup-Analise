# Fase 7 — Machine Learning: dataset, treinamento e validação

**Data:** 09/09/2026 · **Remedido em 10/09/2026** · **Semente:** 20260909
**Versão dos dados:** `9e9c85ee3ffea5e0`
**Reprodução:** `python ml/executar_tudo.py` (≈ 20 min)

> **Nota de correção (10/09/2026).** Todos os números deste documento foram
> **remedidos** depois de um defeito de pipeline corrigido na Fase 8: o passo
> `40_atc.py` casava substância com código ATC usando um índice que inclui os
> sinônimos INN — que só são criados depois, por `60_interacoes_substancia.py`.
> A primeira passada perdia **6 vínculos**, e a cobertura de ATC ficava em
> 1.153 em vez de 1.159. O passo `68_vincular_atc_pendente.py` fecha isso, e a
> impressão digital dos dados passou de `59d4915db0a349e3` para
> `9e9c85ee3ffea5e0`. **Nenhuma conclusão mudou** — os deslocamentos são da
> ordem de 0,001 de AUC. A impressão digital agora inclui o *conteúdo* das
> colunas que viram atributo, e não apenas a contagem de linhas, para que uma
> mudança dessas não volte a passar em silêncio. Ver D-048.

---

## Resumo em uma página

O objetivo da fase não era treinar uma IA. Era descobrir **qual problema
preditivo este banco realmente sustenta**, e se o ganho justifica usar
aprendizado de máquina dentro do Conciliador.

A resposta tem três partes.

**Primeira: dos sete alvos possíveis, só dois têm rótulo suficiente.** A
existência de interação documentada (94.770 pares) e o tipo farmacocinético ×
farmacodinâmico (52.261 pares, rótulo fraco). Os outros cinco foram recusados
**com número ao lado** — inclusive o mais desejado, a relevância do alerta, que
depende de avaliação de farmacêutico e hoje tem **zero** registros.

**Segunda: o modelo funciona, e funciona menos do que a literatura sugere.** No
protocolo otimista (o mesmo que produz as AUC de 0,97 dos artigos) chegamos a
**0,9442**. No protocolo honesto — fármacos que o modelo nunca viu — o número é
**0,7392**. A diferença não é detalhe metodológico: os atributos derivados do
grafo de interações levam a AUC a 0,944 quando o fármaco é conhecido e a
**0,3416, pior que o acaso**, quando é novo.

**Terceira, e é a conclusão da fase: o modelo não vai virar alerta.** No regime
realista ele tem recall 0,56 e precisão 0,39 — deixaria passar quase metade das
interações e erraria seis em cada dez avisos. Levar isso ao balcão aumentaria a
fadiga de alerta sem aumentar a segurança. Mas a precisão **no topo** da lista é
de 0,80 no primeiro 1%, contra 0,20 de linha de base, e é isso que o modelo passa a fazer:
**priorizar uma fila de curadoria** de pares sem documentação, para verificação
humana. Os dois modelos ficam registrados como `EXPERIMENTAL`, `ativo = 0`, e o
banco recusa ativá-los.

Esse é um resultado válido pelo critério da própria especificação (§26): o
dataset atual **ainda não** sustenta ML clinicamente útil como gerador de
alerta, e sustenta como priorizador de trabalho humano.

---

## Legenda técnica

Só os termos que podem não ser imediatamente claros. Termos clínicos ficam como
estão.

| Termo | O que é |
|---|---|
| **ML** | aprendizado de máquina: o programa ajusta uma regra a partir de exemplos, em vez de a regra ser escrita à mão |
| **alvo** (*target*) | o que o modelo tenta prever. Aqui: "existe interação documentada entre A e B?" |
| **atributo** (*feature*) | cada informação que entra no modelo. Aqui: classe ATC, tarja, nº de apresentações, papel CYP… |
| **rótulo** (*label*) | a resposta certa conhecida para um exemplo |
| **split** | como os dados são separados em treino / validação / teste |
| **vazamento** (*leakage*) | quando a resposta entra disfarçada de atributo e a métrica fica boa por motivo errado |
| **linha de base** (*baseline*) | o modelo mais burro possível; qualquer coisa que não o supere não existe |
| **recall** / sensibilidade | dos casos que existiam, quantos o modelo encontrou |
| **precisão** | dos avisos que o modelo deu, quantos estavam certos |
| **especificidade** | dos casos que não existiam, quantos o modelo corretamente deixou quietos |
| **F1** | média harmônica de precisão e recall; um número só para os dois |
| **ROC-AUC** | probabilidade de o modelo dar nota maior a um caso positivo que a um negativo. 0,5 = acaso; 1,0 = perfeito |
| **PR-AUC** | área sob precisão × recall. **O piso não é 0,5, é a prevalência** — por isso vai sempre com o piso ao lado |
| **calibração** | se o modelo diz 80%, isso acontece mesmo em 80% das vezes? |
| **ECE** | erro de calibração esperado: distância média entre a probabilidade dita e a frequência real |
| **Brier** | erro quadrático médio da probabilidade; junta acerto e calibração num número |
| **bootstrap** | reamostrar os dados muitas vezes para saber quanta incerteza há numa métrica |
| **aprendizado PU** | aprender só com positivos e não-rotulados, quando não existe negativo confirmado |
| **embedding** | representar cada item por um vetor de números aprendido |
| **GNN** | rede neural sobre grafo: propaga informação pelas ligações entre nós |
| **SHAP** | método de atribuir a cada atributo sua parcela numa previsão específica. **Não foi usado aqui** — ver §7 |

---

## 1. Auditoria do dataset

`ml/01_auditoria_dataset.py` → `ml/saida/01_auditoria_dataset.json`

### 1.1 Linha não é observação

| | |
|---|---:|
| linhas em `interacao_substancia` | 112.520 |
| pares distintos (a < b) | **94.770** |
| linhas por par | 1,19 |
| pares afirmados por **1** fonte | 77.020 (81,3%) |
| pares afirmados por **2** fontes | 17.750 (18,7%) |
| duplicata exata (mesmo par, mesma fonte) | **0** |
| pares invertidos (A-B e B-A como registros diferentes) | **0** |

As 112.520 linhas são 94.770 observações. A inflação vem de as duas bases
afirmarem o mesmo par. Treinar por linha daria peso 2 a 18,7% dos pares — o
modelo aprenderia "este par aparece em duas compilações", que é propriedade do
processo de compilação, não farmacologia. Ver **D-039**.

### 1.2 Simetria e direção

| Relação | Simétrica? | Consequência |
|---|---|---|
| fármaco × fármaco | **sim** | par canônico, uma linha; atributos obrigatoriamente simétricos |
| papel farmacocinético | não | "A inibe a CYP3A4" ≠ "B é substrato da CYP3A4" — vira **atributo do lado**, não rótulo |
| regra de separação | não | tem um lado que deve ser adiado |
| fármaco × doença | não | a direção é sempre fármaco → doença |

O `CHECK (substancia_a_id < substancia_b_id)` do esquema já impedia par
invertido; a auditoria **confirmou** zero. O autoteste de `ml/_features.py`
verifica, par por par, que `construir(a,b) == construir(b,a)`.

### 1.3 O grafo — a medição que decide sobre GNN

Feita **antes** de qualquer treino, como a especificação §14 exige.

| | |
|---|---:|
| substâncias com **grau zero** | **1.137 de 2.094 (54,3%)** |
| substâncias com ≥ 1 interação | 957 (45,7%) |
| grau médio (só as conectadas) | 198,1 |
| grau mediano | 178 |
| pares possíveis entre as conectadas | 457.446 |
| pares observados | 94.770 |
| **densidade do subgrafo conectado** | **20,72%** |
| componentes conexas | **1** |

O grafo é dois objetos colados. Entre as 957 conectadas ele é **denso** — um em
cada cinco pares possíveis já é aresta — e tem uma componente única: há pouca
estrutura de vizinhança a explorar, porque quase todo mundo é vizinho de quase
todo mundo. E há 1.137 substâncias sem nenhuma aresta, onde um modelo que
propaga por ligação não tem o que propagar. São exatamente as que motivam o
projeto: o farmacêutico consulta o sistema justamente sobre o que não está na
base.

### 1.4 Cobertura de atributo — o teto do que se pode aprender

| Atributo | Das 2.094 | Das 957 conectadas |
|---|---:|---:|
| código ATC | 55,3% | **95,0%** |
| canal de dispensação (tarja) | 69,2% | 84,7% |
| CAS | 71,9% | 98,7% |
| regra de administração | 29,6% | 55,8% |
| interação com item | 9,4% | 19,5% |
| **papel farmacocinético (CYP)** | **1,1% (22)** | 2,3% |
| **alvo molecular** | **0** | 0 |
| índice terapêutico estreito · RENAME · reação adversa | **0** | 0 |

O que sobra como atributo real é a hierarquia ATC, a tarja e o número de
apresentações no mercado. **Estrutura química não existe no acervo**: há CAS,
que é identificador, não estrutura — não há como calcular *fingerprint* ou
similaridade estrutural sem carregar fonte nova. A camada IUPHAR de alvo
molecular, que existia no sistema anterior, não foi carregada neste projeto.

### 1.5 O 5º nível do ATC não pode ser atributo

Todos os 1.159 códigos gravados são de 5º nível, e **nenhum é compartilhado por
duas substâncias**. O 5º nível *é* a substância; usá-lo como categoria seria
entregar o identificador ao modelo. Entram os níveis 1 a 4 (14, 83, 181 e 445
classes). Mesmo motivo de **D-028** para duplicidade terapêutica.

**Limitação:** a coluna guarda **um** código ATC por substância. Fármaco com
mais de uma indicação perde as outras — e isso aparece na explicação de uma
previsão real (§7.3).

### 1.6 Split temporal: impossível

Todas as 11 cargas são de 09/09/2026 e **nenhuma das duas fontes publica a data
em que a interação foi documentada**. Split temporal fica declarado como
impossível com os dados atuais, e **não** foi substituído por proxy.

### 1.7 Colunas que não podem ser atributo

| Coluna | Por quê |
|---|---|
| `interacao_substancia.tipo` | sai de regex sobre a descrição da própria interação |
| `.gravidade` | graduação da própria afirmação |
| `.mecanismo` · `.efeito_esperado` · `.descricao_original` | são o texto do rótulo |
| `achado.prioridade` | calculada pelas nossas regras a partir do rótulo |

**Registro importante.** No sistema anterior o vetor farmacodinâmico era
extraído de `db_drug_interactions.csv` — o mesmo arquivo que dava o rótulo; a
ablação "SEM PD" custava 0,0428 de AUC. **Neste projeto essa coluna não
existe**: os atributos vêm da OMS (ATC), da CMED e da FDA, fontes que não
afirmam interação nenhuma. A circularidade foi resolvida por construção. A
ablação foi feita mesmo assim, sobre os atributos de **grafo**, que têm o mesmo
problema por outro caminho (§5.2).

---

## 2. Auditoria dos rótulos

`ml/02_auditoria_rotulos.py` → `ml/saida/02_auditoria_rotulos.json`

Três origens de rótulo, nunca misturadas: **FONTE** (base externa), **SISTEMA**
(derivado pelas nossas regras) e **HUMANO** (farmacêutico assinou).

| Alvo | Origem | Rótulos | Veredito |
|---|---|---:|---|
| **A — existe interação documentada** | FONTE | 94.770 positivos | **treinado** |
| **C2 — tipo PK × PD** | SISTEMA (regex) | 52.261 | **treinado**, secundário, declarado |
| B — relevância do alerta | HUMANO | **0** | recusado |
| C1 — gravidade | FONTE | 38.459 de 94.770 | recusado |
| prioridade | SISTEMA | — | recusado (circular) |
| mecanismo · efeito clínico | FONTE (texto livre) | — | recusado (sem classes) |
| necessidade de revisão | SISTEMA | 0 | recusado (alvo sem variação) |
| reação adversa | VigiMed | 0 | recusado (fonte não carregada) |

### 2.1 Relevância do alerta: a tabela existe e está vazia

`anotacao_profissional` tem chave estável, assinatura e `CHECK` de
intencionalidade — e **zero linhas**. Zero farmacêuticos distintos. Zero achados
com anotação. Zero com consenso.

Não há o que treinar e não há extrapolação honesta a partir de zero exemplos. A
análise de poder indica **97 avaliações** para estimar uma taxa de relevância
com ±10 pontos de precisão (43 para ±15 pontos, 81 se a taxa for de 30%); com
validação cruzada por avaliador, algo entre **400 e 1.000**, de dois
farmacêuticos independentes.

**O que não foi feito, e por quê:** usar `prioridade` como proxy mediria
fidelidade a `rules/_prioridade.py`, não utilidade clínica (§3 da especificação
proíbe); marcar como relevante o que tem gravidade MAIOR é a mesma
circularidade com outro nome; simular anotações inventaria evidência clínica.

### 2.2 Gravidade: o rótulo não existe na fonte

| Fonte | MODERADA | MAIOR | MENOR | NÃO DETERMINADA |
|---|---:|---:|---:|---:|
| DDInter | 28.027 | 8.106 | 2.326 | 19.864 |
| `db_drug_interactions` | 0 | 0 | 0 | **54.197** |

Pares com alguma graduação: **38.459 (40,6%)**. Pares graduados por **duas**
fontes: **0**. Linhas em `vw_conflito_gravidade`: **0** — e não por concordância
entre as bases, mas por existir **um único graduador**.

Um alvo ordinal cuja consistência é estruturalmente imensurável não tem como ser
validado. **D-015 mantida**, agora com medição própria.

### 2.3 Tipo PK × PD: treinável e de segunda ordem

52.261 pares (55,1%) têm tipo determinado, e **todos** vêm de
`db_drug_interactions` — o DDInter não publica descrição nenhuma, logo não há
texto de onde extrair tipo. Zero divergência entre fontes, porque só uma opina.

É um alvo tecnicamente treinável e clinicamente de segunda ordem: saber que a
interação é farmacocinética não muda a conduta de balcão tanto quanto saber que
ela existe. Fica registrado como alvo secundário, com o rótulo marcado
`EXTRAIDO_AUTOMATICAMENTE`.

---

## 3. O dataset

`ml/10_dataset.py` → `data/training/dataset_m1.npz`

**Unidade:** o par canônico de substâncias (`a < b`), uma linha por par
(**D-039**).

**Universo:** todos os pares das 957 substâncias com pelo menos uma interação
afirmada — **457.446 pares**, 94.770 positivos, **prevalência 20,7%**.

Não há amostragem de negativo: o universo entra inteiro, com a prevalência real.
Amostrar introduziria uma escolha a defender; usar tudo não introduz nenhuma.
Balanceamento, quando usado, é **peso de classe dentro do treino** (família
`LOGISTICA_PESO_BALANCEADO`) — nunca removendo ou replicando linha, e nunca
tocando validação ou teste.

Pares que envolvem as 1.137 substâncias de grau zero ficam **fora**: ali a
ausência de linha é falta de cobertura da fonte, não ausência de interação.
Chamar aquilo de negativo seria fabricar rótulo.

### 3.1 O negativo é presumido — a limitação central

Nenhuma das bases publica "estes dois não interagem": elas listam o que afirmam.
Ausência de linha significa uma de três coisas que o dado não distingue:

1. as duas foram estudadas juntas e não interagem;
2. nunca foram estudadas juntas;
3. interagem e a base ainda não registrou.

Isto é **aprendizado PU**. A consequência prática, escrita em todo lugar onde o
número aparece: **o modelo estima a probabilidade de o par ESTAR DOCUMENTADO nas
bases carregadas, não de o par ser perigoso.** Ver **D-040**.

### 3.2 Quatro splits, porque medem coisas diferentes

| Split | O que mede |
|---|---|
| **POR_PAR** | pares sorteados; ambos os fármacos aparecem no treino. É o protocolo da literatura, e o mais otimista |
| **POR_FARMACO** | fármacos sorteados; o treino usa só pares cujos **dois** lados são de treino |
| **PAREADO_GRAU** | subconjunto em que cada negativo tem grau parecido com o do positivo |
| **ALEATÓRIO** | controle negativo: pares sorteados sem critério nenhum |

O split por fármaco parte o teste em três regimes:

| Regime | Pares | Positivos | Prevalência |
|---|---:|---:|---:|
| treino (os dois lados de treino) | 223.446 | 46.480 | 20,8% |
| validação | 107.445 | 22.286 | 20,7% |
| teste — total | 126.555 | 26.004 | 20,5% |
| teste — **QUENTE_FRIO** (um lado inédito) | 116.402 | 23.936 | 20,6% |
| teste — **FRIO_FRIO** (dois lados inéditos) | **10.153** | 2.068 | 20,4% |

O sorteio de fármacos é **estratificado por decil de grau**. Um sorteio simples
deixava a prevalência diferente entre os regimes (medido: 19,3% no treino contra
23,4% no frio-frio), e parte da variação de métrica viria da prevalência, não do
regime. Estratificar remove esse confundidor sem tocar no rótulo. Os grupos
ficaram com grau médio 199 / 197 / 196.

**FRIO_FRIO é o análogo mensurável do ponto cego real** e é o regime que decide
esta fase.

---

## 4. Os atributos

`ml/_features.py` — definido **aqui e em lugar nenhum mais**. Treino e predição
importam a mesma função; `70_predizer.py` aborta se o espaço divergir do gravado
em `models/espaco_features.json`. Foi assim que o sistema anterior quebrou em
silêncio ao acrescentar o ATC.

| Bloco | Atributos | Origem | No modelo publicado? |
|---|---:|---|---|
| **ATC** | 102 | WHO ATC | sim |
| **REG** | 10 | CMED, ANVISA, DCB | sim |
| **ADM** | 11 | DrugBank + bulas ANVISA | sim |
| **PK** | 7 | tabela de fármacos-índice da FDA | sim |
| **GRAFO** | 7 | o próprio rótulo | **não** — ver §5.2 |
| | **130 publicados** (137 com grafo) | | |

Três regras que os atributos obedecem, verificadas por autoteste:

1. **Simetria.** Contagem de lados, soma, mín/máx, ou-lógico. Nunca "valor de A"
   numa coluna e "valor de B" em outra — isso ensinaria a ordem do id.
2. **Nenhum atributo sai da fonte do rótulo.** ATC é da OMS, tarja e mercado são
   da CMED, papel CYP é da FDA, regra de administração é do DrugBank/bulas.
   Nenhuma delas afirma interação fármaco × fármaco.
3. **O bloco GRAFO é declaradamente derivado do rótulo**, fica separado, é
   calculado só com as arestas de treino, e existe ablação sem ele.

O único atributo que carrega **mecanismo**, e não apenas associação, é
`pk_inibidor_x_substrato`: um dos fármacos inibe a enzima da qual o outro é
substrato. Com 22 substâncias cobertas, ele é quase sempre zero — e a
importância por permutação confirma: o bloco PK inteiro vale 0,0055 de AUC.

---

## 5. Comparação das famílias

`ml/20_treinar.py` → 40 execuções · `docs/ML_COMPARACAO.md` tem a tabela completa

Nenhuma família foi escolhida antes de medir. O limiar de decisão é escolhido
**sempre na validação** e aplicado ao teste.

### 5.1 O quadro geral

**Split POR_PAR (otimista) — teste, atributos COMPLETO:**

| Família | ROC-AUC | PR-AUC (piso 0,205) |
|---|---:|---:|
| FLORESTA | **0,9442** | 0,8425 |
| GRADIENT_BOOSTING | 0,9385 | 0,8289 |
| LOGISTICA_PESO_BALANCEADO | 0,9251 | 0,7905 |
| LOGISTICA | 0,9238 | 0,7921 |
| SVM_LINEAR | 0,9233 | 0,7923 |
| ARVORE | 0,9175 | 0,7745 |
| GRAFO_ADAMIC_ADAR | 0,9074 | 0,7593 |
| TABELA_CLASSE_×_CLASSE | 0,7337 | 0,4532 |
| REGRA_ATC_N2 | 0,5177 | 0,2164 |
| PREVALENCIA (linha de base) | 0,5000 | 0,2054 |

**Split POR_FARMACO (honesto) — atributos SEM_GRAFO:**

| Família | AUC teste | AUC **FRIO_FRIO** | PR-AUC ff (piso 0,204) | Treino |
|---|---:|---:|---:|---:|
| **GRADIENT_BOOSTING** | 0,7887 | **0,7392** | 0,4451 | 26 s |
| FLORESTA | **0,7941** | 0,7344 | 0,4610 | 27 s |
| LOGISTICA_PESO_BALANCEADO | 0,7345 | 0,7153 | 0,4187 | 2,1 s |
| LOGISTICA | 0,7339 | 0,7147 | 0,4192 | 2,0 s |
| ARVORE (profundidade 6) | 0,7153 | 0,7141 | 0,4072 | 2,3 s |
| SVM_LINEAR | 0,7328 | 0,7139 | 0,4142 | 2,8 s |
| TABELA_CLASSE_×_CLASSE | 0,7032 | 0,6856 | 0,4055 | 0,2 s |

Duas leituras importam aqui. A primeira: **a diferença entre 0,944 e 0,738 é
inteira de protocolo**, não de modelo. A segunda: uma **árvore de profundidade
6** — legível inteira numa página — chega a 0,7141, a 0,025 do melhor modelo.

### 5.2 A ablação que decidiu o desenho — o grafo

**Split POR_FARMACO, teste / FRIO_FRIO:**

| Configuração | LOGISTICA | GRADIENT_BOOSTING |
|---|---:|---:|
| **COMPLETO** (com grafo) | 0,3416 / 0,4313 | 0,5460 / 0,5457 |
| **SEM_GRAFO** | 0,7339 / **0,7147** | 0,7887 / **0,7392** |
| SO_ATC | 0,6777 / 0,6668 | 0,7154 / 0,6921 |
| SO_REG (só mercado e tarja) | 0,6258 / 0,5957 | 0,6526 / 0,6218 |
| SEM_POPULARIDADE (ATC+ADM+PK) | 0,7179 / 0,7033 | 0,7608 / 0,7252 |
| SO_GRAFO | 0,3468 / **0,5000** | 0,4501 / **0,5000** |

Com os atributos de grafo e um fármaco inédito, a regressão logística faz
**AUC 0,3416 — pior que o acaso**. Não é bug: para o fármaco novo o grau é zero,
os vizinhos comuns são zero, e os coeficientes aprendidos sobre essas colunas
passam a apontar na direção errada. Em FRIO_FRIO, com `SO_GRAFO`, todos os
atributos são identicamente zero e a AUC é **0,5000 exata**.

A heurística de grafo pura (Adamic-Adar), representante da família de grafo,
faz **0,5000 exata** no regime frio: não existe um único vizinho em comum a
explorar. **Esta é a resposta empírica à pergunta "e uma GNN?"** — feita antes de
treinar qualquer rede, como a especificação exige, e coerente com a medição de
§1.3. Ver **D-038**.

### 5.3 De onde vem o desempenho

Somando as ablações do gradient boosting em FRIO_FRIO:

```
   acaso                                          0,5000
   + classe farmacológica (ATC)          +0,192 → 0,6921
   + regra de administração e CYP        +0,033 → 0,7252   (SEM_POPULARIDADE)
   + mercado e tarja (popularidade)      +0,014 → 0,7392   (SEM_GRAFO, publicado)
   + grafo do rótulo                     −0,194 → 0,5457   (rejeitado)
```

A maior parte do sinal é classe farmacológica. Mas **dois dos três blocos
restantes são medidas de "quão estudado é este fármaco"**, e a explicabilidade
confirma isso de forma incômoda (§7.1).

### 5.4 A diferença entre as famílias é real?

`ml/45_significancia.py` — bootstrap **pareado**, 1.000 reamostragens sobre os
mesmos pares.

**Teste FRIO_FRIO (10.153 pares, 2.068 positivos):**

| Família | AUC | IC 95% |
|---|---:|---|
| GRADIENT_BOOSTING | 0,7392 | [0,7270 ; 0,7504] |
| FLORESTA | 0,7344 | [0,7223 ; 0,7461] |
| LOGISTICA | 0,7147 | [0,7024 ; 0,7266] |
| TABELA_CLASSE_×_CLASSE | 0,6856 | [0,6727 ; 0,6983] |

| Diferença | Média | IC 95% | Conclusão |
|---|---:|---|---|
| FLORESTA − GRADIENT_BOOSTING | −0,0047 | [−0,0117 ; +0,0022] | **empate** (contém zero) |
| LOGISTICA − GRADIENT_BOOSTING | −0,0243 | [−0,0317 ; −0,0168] | diferença estabelecida |
| TABELA − LOGISTICA | −0,0294 | [−0,0428 ; −0,0159] | diferença estabelecida |

A regra de desempate foi fixada **antes** de olhar os números: decide o teste
FRIO_FRIO; diferença menor que 0,02 de AUC é empate; em empate ganha a mais
simples. O bootstrap concorda com a regra e a torna mensurável em vez de
arbitrária.

**Escolhido: `GRADIENT_BOOSTING` com `SEM_GRAFO`.** Empata com a floresta
(dentro do intervalo de confiança) e é preferível por prever mais rápido e
gerar um artefato de 1,08 MB contra uma floresta de 120 árvores.

A regressão logística fica **0,0243 atrás — diferença real, mas pequena** — e
foi registrada junto, como referência interpretável (**D-042**). Se a
interpretabilidade vier a pesar mais que 0,02 de AUC, a troca é uma decisão
com número, não um retreino no escuro.

---

## 6. Robustez, controle negativo e calibração

`ml/25_robustez.py` · `ml/30_calibracao.py`

### 6.1 Quanto do acerto era popularidade?

Subconjunto **pareado por grau**: 67.443 positivos e 67.443 negativos, cada
negativo com grau parecido com o do positivo (grau médio 270 contra 266). Nele,
saber quem é popular deixa de ajudar.

| Família / atributos | AUC no pareado | AUC no universo |
|---|---:|---:|
| GRADIENT_BOOSTING / SEM_GRAFO | **0,7238** | 0,7887 |
| LOGISTICA / SEM_GRAFO | 0,6002 | 0,7339 |
| GRADIENT_BOOSTING / COMPLETO | 0,6061 | 0,5460 |
| LOGISTICA / COMPLETO | **0,5052** | 0,3416 |

A logística com grafo cai a 0,5052 — praticamente acaso. O modelo publicado
mantém **0,7238** com o grau neutralizado: a maior parte do que ele sabe não é
popularidade.

### 6.2 Controle negativo (§20)

5.000 pares sorteados ao acaso entre **todas** as 2.094 substâncias, nenhum
deles positivo, 83,1% envolvendo fármaco de grau zero:

| | |
|---|---:|
| probabilidade média — positivos do teste | 0,371 |
| probabilidade média — negativos do teste | 0,147 |
| probabilidade média — **controle ao acaso** | **0,087** |
| controle acima de 0,5 | 62 (1,2%) |
| controle acima de 0,9 | **0** |

O modelo **não** distribui probabilidade alta indiscriminadamente. O controle
não tem rótulo verdadeiro — são pares não afirmados, não pares provadamente
inertes — e serve só para essa pergunta.

### 6.3 O rótulo mais duro

Repetindo tudo com positivo **só quando as duas bases afirmam** (17.750
positivos, prevalência 3,9%; os 77.020 afirmados por uma fonte só saem do
universo, porque chamá-los de negativo seria afirmar que a outra base os
examinou e recusou):

| Família | AUC | PR-AUC (piso 0,044) |
|---|---:|---:|
| GRADIENT_BOOSTING | **0,8581** | 0,3492 (8× o piso) |
| LOGISTICA | 0,7992 | 0,2166 |

O desempenho **sobe** com o rótulo mais exigente. É evidência de que o sinal é
comum às duas bases, e não o idiossincrático de uma compilação.

### 6.4 Calibração

Ajustada na **validação**, medida no **teste** — ajustar e medir no mesmo
conjunto produz calibração perfeita e falsa.

| Família | ECE cru | ECE isotônica | ECE Platt | Brier cru → isotônica |
|---|---:|---:|---:|---|
| LOGISTICA | 0,0231 | **0,0036** | 0,0154 | 0,1427 → 0,1421 |
| GRADIENT_BOOSTING | 0,0223 | **0,0118** | 0,0328 | 0,1302 → 0,1298 |
| FLORESTA | 0,0115 | 0,0183 | 0,0267 | 0,1285 → 0,1286 |
| TABELA_CLASSE_×_CLASSE | 0,0165 | 0,0157 | 0,0174 | 0,1453 → 0,1448 |

Curva de confiabilidade do modelo escolhido, no teste (antes → depois da
isotônica):

| Faixa | n | prob. média | freq. real | desvio |
|---|---:|---:|---:|---:|
| 0,0–0,1 | 57.296 | 0,046 | 0,067 | −0,021 |
| 0,3–0,4 | 9.107 | 0,347 | 0,342 | +0,005 |
| 0,6–0,7 | 3.451 | 0,646 | 0,608 | +0,039 |
| 0,8–0,9 | 1.532 | 0,844 | 0,851 | −0,007 |
| 0,9–1,0 | 502 | 0,933 | **0,944** | −0,012 |

**Sim: quando o modelo diz 0,93, a frequência real é 0,944.** No regime
FRIO_FRIO o erro é maior e cai de 0,0488 para **0,0361** com a calibração.

A calibração **não muda a ordenação** (isotônica e Platt são monótonas), logo a
AUC não muda. Ela muda o número que apareceria na tela — que é exatamente o que
o farmacêutico leria. Por isso é obrigatória antes de exibir qualquer
probabilidade, e não um refinamento opcional. O calibrador é gravado como
**tabela de pontos em JSON**, nunca pickle (**D-043**).

---

## 7. Explicabilidade

`ml/40_explicabilidade.py`

### 7.1 O que o modelo usa — e o que isso revela

Importância por permutação (embaralha uma coluna e mede quanto a AUC cai),
gradient boosting, validação:

| Atributo | Queda de AUC |
|---|---:|
| `adm_lados_com_regra` — quantos lados têm regra de administração | **0,0564** |
| `produtos_log_min` — apresentações do menos comercializado | 0,0374 |
| `produtos_log_max` — apresentações do mais comercializado | 0,0279 |
| `atc_grupo1_N` — quantos são do grupo Sistema nervoso | 0,0134 |
| `tarja_desconhecida_lados` | 0,0122 |
| `atc_grupo2_A16` | 0,0093 |

Por bloco: **ATC 0,1559** · REG 0,0927 · ADM 0,0640 · **PK 0,0055**.

**Este é o achado mais desconfortável da fase, e ele fica registrado.** O
atributo mais importante não é farmacológico: é "este fármaco tem uma regra de
administração cadastrada?", ou seja, *este fármaco foi bem estudado*. Somando
REG e ADM, cerca de metade da importância do modelo é **propensão a estar
documentado**, não risco farmacológico. Isso é coerente com o alvo — que é
literalmente "está documentado?" — e é exatamente por isso que a conclusão da
fase é a do §9.

Coeficientes da regressão logística (direção e tamanho):

| Atributo | Coef. | Direção |
|---|---:|---|
| `adm_lados_com_regra` | +1,348 | aumenta |
| `adm_tipo_INDIFERENTE_ALIMENTO` | −0,787 | reduz |
| `produtos_log_min` | +0,223 | aumenta |
| `atc_n1_igual` (mesmo grupo anatômico) | +0,200 | aumenta |
| `atc_grupo2_N05` (psicolépticos) | +0,132 | aumenta |

### 7.2 Explicação de uma previsão

Método: **contribuição aproximada por ocultação** — recalcula a previsão com um
atributo por vez no valor de referência e mede a diferença. **Não é SHAP**: o
SHAP exato média todas as ordens de entrada dos atributos, e a biblioteca não
está instalada (**D-044**). O relatório e a interface dizem "contribuição
aproximada", nunca "valor SHAP".

```
fluoxetina  ×  paroxetina          probabilidade 0,991   (afirmado por fonte)
   [+0,031] os dois atuam na mesma enzima CYP
   [+0,011] quantos lados têm regra de administração
   [+0,007] quantidade de apresentações do menos comercializado
   [+0,006] mesmo subgrupo farmacológico
   [+0,005] os dois são do grupo anatômico N (Sistema nervoso)

acetato de glatirâmer × sulfacetamida   probabilidade 0,000   (não afirmado)
   [−0,004] um dos fármacos é do subgrupo D10 (Preparações antiacne)
   [−0,002] quantos lados têm regra de administração
```

### 7.3 O limite que não se atravessa — e um exemplo de por quê

Contribuição estatística **não é** mecanismo farmacológico. "Os dois são do
subgrupo C09" explica o que o **modelo viu**; não afirma que há interação, nem
qual seria. Se houver mecanismo conhecido, ele vem da fonte pelo caminho
determinístico e aparece no achado `DOCUMENTADO` — nunca daqui.

O terceiro exemplo do relatório mostra por que a cautela é necessária:

```
magaldrato × metronidazol           probabilidade 0,500
   [+0,330] um dos fármacos é do subgrupo A01 (Preparações estomatológicas)
```

O metronidazol tem vários códigos ATC; o que o banco guarda é `A01AB17`, o de
uso **odontológico**. A explicação está tecnicamente correta sobre o que o
modelo viu e é farmacologicamente enganosa — porque a limitação "um código ATC
por substância" (§1.5) chegou até aqui. Um farmacêutico que lesse isso como
mecanismo seria induzido ao erro. É mais um motivo para a decisão do §9.

---

## 8. Verificação dupla

### V1 — validação do pipeline (`ml/91_v1_pipeline.py`)

37 conferências, todas passaram: o `.npz` corresponde ao banco par por par; os
positivos são exatamente as linhas de `interacao_substancia`; o split é
completo, disjunto e sem fármaco em dois grupos; os atributos são simétricos e
sem NaN; **dois treinos com a mesma semente dão previsões idênticas** (diferença
máxima 0,00e+00); a AUC gravada em `modelo` bate com o recálculo até a sexta
casa; o artefato recarregado do disco dá a mesma previsão; e o contrato recusa o
modelo experimental.

### V2 — verificação independente (`ml/92_v2_independente.py`)

Seis caminhos que **não repetem** o pipeline (32 conferências):

| Caminho | Resultado |
|---|---|
| **1. Recontagem por SQL próprio**, sem ler o `.npz` | 957 substâncias, 94.770 positivos, 457.446 pares — batem; 301 positivos e 301 negativos conferidos um a um |
| **2. Métricas reimplementadas em numpy puro** (AUC por postos de Mann-Whitney, PR-AUC por trapézio, Brier, ECE) | AUC 0,78787203 nos dois; Brier e ECE idênticos até a 8ª casa; PR-AUC 0,537701 vs 0,537714 (definições diferentes) |
| **3. Confronto com o banco do sistema anterior**, casando por chave normalizada de nome | **98,9%** dos 93.940 pares deste sistema estão nos 108.032 do anterior; 1.040 só aqui, 15.132 só lá |
| **4. Caça ao vazamento por força bruta** | zero pares de teste no treino; zero pares invertidos; zero fármacos de teste no grafo; atributos de grafo zero em 2.000 pares FRIO_FRIO |
| **5. Split conferido por combinatória** | 669+145+143 = 957; C(669,2) = 223.446 = treino; C(143,2) = 10.153 = FRIO_FRIO; 143×814 = 116.402 = QUENTE_FRIO |
| **6. Artefato JSON recalculado à mão**, sem scikit-learn | mesma probabilidade, ordenação idêntica |

**A V2 reprovou na primeira execução** — caminho 6, diferença máxima de
1,21e-07 contra uma tolerância de 1e-9. Investigado: a matriz de atributos é
`float32` (escolha de memória — 457.446 × 130 em `float64` seriam 475 MB) e o
scikit-learn faz a conta inteira em `float32`, enquanto o recálculo à mão promove
para `float64`. A diferença é **exatamente o epsilon do float32 (1,192e-07)**;
refazendo a conta em `float32` ela cai para 5,96e-08. Era a tolerância que estava
errada, não o artefato. Corrigida para 1e-6, com o motivo escrito ao lado, e
acrescentado o teste que de fato importa: **a ordenação das 300 previsões é
idêntica**, logo nenhuma decisão por limiar muda.

Vale registrar que a V2 fez o que devia: o único defeito da fase foi achado por
ela, e não pelos testes que já passavam.

### Regressão (`tests/teste_ml.py`, 44 verificações)

Nada do que foi construído antes quebrou. `pipeline/executar_tudo.py --recriar`
sai 0, com 265 verificações marcadas OK ao longo de 12 etapas de carga e 16 de
verificação. `pipeline/90_validacao.py` ganhou **9 checagens
novas** e `tests/teste_schema.py` duas seções (invariantes 2d e 2e).

O teste de ML trava, entre outras: nenhum achado com natureza `PREVISTO`;
nenhum achado com origem `MODELO`; `PREVISTO` sempre aponta para uma linha de
`predicao`; nenhum modelo ativo; todo modelo declara semente, versão dos dados e
espaço de atributos; toda previsão nasce `NAO_REVISADA`; o espaço em disco é
igual ao calculado agora; **nenhum atributo de grafo no espaço publicado**;
`rules/` e `app/` não importam nada de `ml/`; e a interface já trata `PREVISTO`.

---

## 9. Resultado e decisão

### 9.1 O modelo escolhido

| | |
|---|---|
| **Problema** | existência de interação fármaco × fármaco documentada |
| **Família** | `HistGradientBoostingClassifier` (boosting por histograma) |
| **Atributos** | 130, blocos ATC + REG + ADM + PK |
| **Protocolo** | split por fármaco, estratificado por decil de grau |
| **AUC teste** | 0,7887 · **AUC FRIO_FRIO 0,7392** [0,7270 ; 0,7504] |
| **PR-AUC FRIO_FRIO** | 0,4451 (piso 0,204) |
| **Calibração** | isotônica; ECE 0,0223 → 0,0118 |
| **Artefato** | 1,08 MB, pickle (dependente do scikit-learn 1.9.0, declarado) |
| **Status** | **EXPERIMENTAL · ativo = 0** |

Registrado junto: `1.0-logistica`, AUC FRIO_FRIO 0,7147, artefato JSON de 10 KB,
como referência interpretável.

### 9.2 Por que ele não vira alerta

No regime FRIO_FRIO, nos dois pontos de operação:

| Ponto | Limiar | Precisão | Recall | Especificidade | Alertas em 10.153 pares |
|---|---:|---:|---:|---:|---:|
| **F1 máximo** | 0,225 | 0,392 | 0,556 | 0,780 | 2.931 |
| **Recall alto (95%)** | 0,052 | 0,257 | 0,905 | 0,331 | 7.283 |

No ponto de F1 máximo, 44% das interações documentadas passariam batido e seis
em cada dez avisos seriam falsos. No ponto de recall alto, o modelo marcaria
**72% de todos os pares**. Nenhum dos dois é um alerta de balcão.

Há ainda uma sutileza que decide a questão. O teste mede "o modelo recupera uma
interação documentada que não lhe foi mostrada?". Em produção ele só seria usado
em pares **sem** documentação — exatamente os que no teste contaram como falso
positivo. Ali não existe verdade conhecida, e é onde a natureza presumida do
negativo (§3.1) cobra o preço.

### 9.3 O que ele passa a fazer

**Precisão no topo da lista, regime FRIO_FRIO** (prevalência 0,204):

| Fatia | Pares | Precisão | Recall | Limiar |
|---|---:|---:|---:|---:|
| top 0,1% | 10 | **0,900** | 0,004 | 0,953 |
| top 0,5% | 50 | 0,780 | 0,019 | 0,877 |
| top 1% | 101 | **0,802** | 0,039 | 0,837 |
| top 5% | 507 | 0,631 | 0,155 | 0,621 |
| top 10% | 1.015 | 0,520 | 0,255 | 0,492 |
| linha de base | — | 0,204 | — | — |

Acertar 4 em 5 nos casos de maior confiança serve para uma coisa concreta:
**dizer a um farmacêutico quais pares valem ser investigados primeiro.**

`ml/80_fila_curadoria.py` pontua os **581.201** pares não documentados entre
substâncias com ATC e produz duas filas (`reports/fila_curadoria_m1.csv`):

| | Candidatos | Substâncias distintas na fila | Prob. do 1º | Prob. do 300º |
|---|---:|---:|---:|---:|
| **A — ponto cego** (um lado sem nenhuma interação conhecida) | 260.240 | 163 | 1,000 | 0,830 |
| **B — lacuna de fonte** (os dois lados cobertos, par não afirmado) | 320.961 | 205 | 0,996 | 0,836 |

Há um teto de 8 pares por substância: sem ele a fila A viria com 300 linhas
sobre **levomepromazina** — que não tem nenhuma interação em nenhuma das duas
bases e cujos pares com antipsicóticos e benzodiazepínicos o modelo marca em
1,000. Um farmacêutico verifica o fármaco uma vez; a fila precisa cobrir vários.

As 600 linhas entram em `predicao` com `status = NAO_REVISADA`. **Nenhum achado
é gerado** — o modelo é experimental e `contrato_achado()` levanta exceção.

Do universo inteiro, 243 pares passam de 0,90 e 21.881 (3,8%) passam de 0,50.

### 9.4 Como a previsão entraria no achado, quando entrar

> **Implementado na Fase 8 (10/09/2026).** O caminho descrito
> abaixo existe inteiro, é testado de ponta a ponta e continua
> desligado: as travas passaram para o banco, em
> `vw_predicao_liberada`. Ver [INTEGRACAO_ML.md](INTEGRACAO_ML.md),
> D-046 e D-047.

`ml/70_predizer.py` expõe o contrato pronto e **desligado**:

```
prever(con, pares)          -> lista de Previsao
contrato_achado(previsao)   -> os campos de `achado`, ou ModeloNaoHomologado
gravar_predicoes(...)       -> escreve em `predicao`, nunca em `achado`
```

`contrato_achado` devolveria: `natureza='PREVISTO'`,
`status_informacao='PREVISTO'`, `origem_achado='MODELO'`,
`nivel_evidencia=NULL`, `confianca_sistema='BAIXA'`,
`confianca_extracao='CALCULADO'`, `requer_revisao_profissional=1`,
`probabilidade_modelo=<calibrada>` e
`origem_afirmacao='predicao.<id>'`.

Três travas independentes:

1. **Espaço de atributos.** Se `models/espaco_features.json` divergir do que
   `_features.espaco()` produz hoje, o preditor levanta erro e não prevê.
2. **Modelo não homologado.** `contrato_achado` recusa enquanto o status não for
   `HOMOLOGADO` — e o banco recusa `ativo=1` para quem não é homologado.
3. **Cobertura.** Par cujo lado não tem ATC recebe `cobertura='FRACA'` e o texto
   diz isso na tela.

O texto que iria ao farmacêutico, gerado pelo próprio contrato:

> Não há interação documentada entre X e Y nas fontes carregadas. Esta linha é
> uma PREVISÃO estatística, não uma evidência: probabilidade estimada de N% de
> que exista interação documentada em alguma base. Modelo
> `m1_existencia_interacao` versão 1.0-boosting (GRADIENT_BOOSTING), status
> EXPERIMENTAL. Nenhuma bula, artigo ou base afirmou esta interação. Requer
> verificação por farmacêutico antes de qualquer conduta.

A interface já tem tratamento visual próprio para `PREVISTO` desde a Fase 6
(`achado.html`, `resultados.html`, `rotulos.py`), e `tests/teste_ml.py` verifica
que continua tendo.

---

## 10. Limitações — todas

1. **O negativo é presumido.** O modelo estima probabilidade de o par estar
   documentado, não de ser perigoso. É a limitação que ordena todas as outras.
2. **Cerca de metade da importância do modelo é propensão a documentação**
   (`adm_lados_com_regra`, número de apresentações), não farmacologia.
3. **Aplicabilidade restrita.** Só há atributo com alguma substância nas 1.159
   com código ATC (55,3%). Para as outras 935 o modelo opina com atributos
   fracos, e **887 (42,4%) não têm ATC nem nenhuma interação conhecida** —
   cegueira dupla.
4. **Um código ATC por substância.** Fármaco com várias indicações perde as
   demais, e isso já distorceu uma explicação real (§7.3).
5. **Sem estrutura química.** Não há *fingerprint*, descritor molecular nem
   similaridade estrutural no acervo. Só CAS, que é identificador.
6. **CYP cobre 1,1% das substâncias** (22) e alvo molecular, nenhuma. O único
   atributo com mecanismo é quase sempre zero.
7. **Split temporal impossível**: nenhuma fonte publica data de documentação.
8. **Zero rótulos humanos.** Nenhum farmacêutico avaliou nenhuma previsão deste
   modelo. O modelo de relevância (problema B) permanece impossível.
9. **Gravidade não é prevista** e continua vindo de fonte ou de curadoria.
10. **Validação apenas computacional.** Nada aqui é validação clínica — ver §11.
11. **O artefato do modelo escolhido é pickle**, dependente do scikit-learn
    1.9.0; é uma amarra declarada para o empacotamento da Fase 10.
12. **Duas fontes, não mais.** DDInter e `db_drug_interactions`. Uma terceira
    base mudaria tanto o rótulo quanto a estimativa do que é "não documentado".

---

## 11. Validação computacional ≠ validação clínica

O modelo tem AUC 0,7392, ECE 0,0118 e precisão 0,80 no topo da lista. **Nenhum
desses números diz que ele é clinicamente válido.**

O que foi feito nesta fase é **validação computacional**: o modelo generaliza
para fármacos que não viu, dentro do recorte de dados descrito acima, medido por
dois caminhos independentes.

**Validação clínica** exigiria: farmacêuticos avaliando as previsões; medida de
concordância entre avaliadores; comparação com desfecho ou com literatura
independente; e avaliação do efeito sobre a conduta no balcão. Nada disso
ocorreu, e o sistema não simula nenhuma dessas etapas. É por isso que os dois
modelos estão `EXPERIMENTAL` e o banco recusa ativá-los.

---

## 12. O que reproduzir, e como

```bash
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"
PYTHONIOENCODING=utf-8 "$PY" ml/executar_tudo.py
```

Ordem obrigatória (a numeração dita, e ela importa):

```
_features (autoteste) → 01 auditoria do dataset → 02 auditoria dos rótulos
→ 10 dataset e splits → 20 comparação das famílias → 25 robustez
→ 45 significância → 30 calibração → 40 explicabilidade → 50 comparação
→ 60 registro do modelo → 70 contrato (autoteste) → 91 V1 → 92 V2
→ tests/teste_ml.py
```

Um terceiro consegue repetir porque estão gravados: a **semente** (20260909), a
**versão dos dados** (`9e9c85ee3ffea5e0`, impressão digital do conteúdo do
banco — não da data da carga, para que `--recriar` reproduza a mesma), o
**espaço de atributos** (130 nomes na ordem exata), a **configuração** de cada
família, as **métricas** e o **artefato**. Todos os números deste documento
foram medidos duas vezes, antes e depois de uma reconstrução completa do banco,
e reproduziram idênticos até a quarta casa decimal.

---

## 13. O que a próxima fase precisa saber

**A fila de curadoria é o caminho de saída da limitação central.** Cada linha
verificada por um farmacêutico vira uma `anotacao_profissional`, e é dela que
depende:

- o modelo de **relevância do alerta** (problema B), hoje impossível;
- os **negativos verdadeiros**, que corrigiriam o aprendizado PU;
- a homologação de qualquer modelo, que é ato humano registrado.

Ganhos de dado que mudariam o quadro, em ordem de impacto estimado:

1. **Estrutura química** (fingerprint) — hoje o modelo não tem nenhuma
   informação sobre a molécula;
2. **IUPHAR/BPS** (alvo e ação) — devolveria a camada mecanística que o sistema
   anterior tinha;
3. **Ampliar a tabela de papéis CYP da FDA** — 22 substâncias é pouco demais
   para o único atributo que carrega mecanismo;
4. **Uma terceira base de interações** — mudaria a definição de "não
   documentado";
5. **Múltiplos códigos ATC por substância** — corrigiria a distorção do §7.3.
