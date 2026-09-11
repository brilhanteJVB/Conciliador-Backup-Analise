# Sistema Conciliador de Medicamentos

Sistema de conciliação farmacêutica para uso no balcão, durante o atendimento —
TCC de Farmácia, Centro Universitário Fametro.

Arquitetura própria, escrita do zero. O sistema anterior (dentro do acervo) é
**fonte de dados, referência de resultado e teste de regressão** — não base
estrutural (ver [DECISIONS.md](docs/DECISIONS.md) D-011).

**Estado: Fase 10 concluída.** O sistema é um programa Windows que instala
copiando uma pasta, roda **sem Python na máquina do usuário** e conduz um
atendimento inteiro, do primeiro dado ao relatório.

> **Empacotado e operacional não é clinicamente validado.** Nenhum
> farmacêutico avaliou nenhum achado deste sistema, e nenhum modelo preditivo
> está homologado. O que as Fases 9 e 10 mediram é que o software faz o que
> promete — não que o que ele promete seja clinicamente suficiente. Ver
> [FASE9_VALIDACAO.md](docs/FASE9_VALIDACAO.md) §9.

---

## O que o sistema faz

Recebe a ficha de um paciente — quem é, o que toma, como toma, a que horas, o
que come, que doença tem, a que é alérgico — e devolve **achados priorizados,
cada um com a fonte atrás e a incerteza declarada**.

Treze módulos determinísticos: fármaco × fármaco · doença · alergia · alimento ·
planta · suplemento · CYP · duplicidade terapêutica · reação adversa · regra de
administração · posologia · divergência de conciliação · e **fármaco × fármaco
previsto por modelo**, que existe, está costurado e está **desligado**.

---

## Estado por fase

| Fase | | Estado |
|---|---|---|
| 1 | Auditoria, modelo de dados, esquema | Concluída |
| 2 | Pipeline de carga e normalização | Concluída |
| 3 | Regras de administração e separação | Concluída |
| 4 | Motor de horários | Concluída |
| 5 | Motor de conciliação + interações | Concluída |
| 6 | Aplicação do farmacêutico | Concluída |
| 7 | Machine Learning | Concluída |
| 8 | Testes integrados + integração do modelo | Concluída |
| 9 | Validação do sistema inteiro | Concluída — apto para empacotamento |
| 10 | **Empacotamento `.exe`** | **Concluída** |

Carregado: **2.094 substâncias** · 8.935 produtos · 25.702 apresentações ·
26.889 códigos de barras · 6.996 classes ATC · 723 regras de administração ·
59 de separação · **112.520 interações fármaco × fármaco (94.770 pares)** ·
182 contraindicações de bula · 28 papéis farmacocinéticos ·
153.647 registros de evidência. **45 tabelas, 15 views, 73 MB.**

Verificação: **1.123 conferências na bateria completa**, em 26 arquivos de
teste, exit 0.

Produto: `SistemaConciliador.exe` — 5,0 MB, pasta de 93,2 MB, uma dependência
(Flask), zero caminhos absolutos.

---

## Documentos

| Documento | Responde |
|---|---|
| [STATUS.md](docs/STATUS.md) | O que cada fase entregou, medido — comece por aqui |
| [ARQUITETURA.md](docs/ARQUITETURA.md) | Camadas, pipeline, os treze módulos, estratégia de ML |
| [APLICACAO.md](docs/APLICACAO.md) | As quatro camadas da aplicação e por que nenhuma pula outra |
| [DECISIONS.md](docs/DECISIONS.md) | **52 decisões** com motivo e alternativas rejeitadas |
| [ML_FASE7.md](docs/ML_FASE7.md) | O relatório de ML — e por que a conclusão é uma recusa |
| [ML_COMPARACAO.md](docs/ML_COMPARACAO.md) | As 40 execuções comparadas, família por família |
| [INTEGRACAO_ML.md](docs/INTEGRACAO_ML.md) | Como uma previsão chega — ou não chega — ao farmacêutico |
| [FASE9_VALIDACAO.md](docs/FASE9_VALIDACAO.md) | A validação do sistema inteiro, e os quatro defeitos que ela achou |
| [EMPACOTAMENTO.md](docs/EMPACOTAMENTO.md) | O executável: método, estrutura, atualização do conhecimento |
| [GUIA_INSTALACAO.md](docs/GUIA_INSTALACAO.md) | **Para quem vai usar** — instalar, fazer backup, resolver problemas |
| [ATENDIMENTO_EXEMPLO.md](docs/ATENDIMENTO_EXEMPLO.md) | Saída real do sistema, gerada por teste |
| [LACUNAS.md](docs/LACUNAS.md) | O que os requisitos exigem e o acervo não tem |
| [auditoria_acervo.md](docs/auditoria_acervo.md) · [MAPA_ACERVO.md](docs/MAPA_ACERVO.md) | O que existe no acervo e como se liga |
| [REVISAO_SCHEMA.md](docs/REVISAO_SCHEMA.md) · [novas_fontes.md](docs/novas_fontes.md) | Revisão do esquema · fontes candidatas |

---

## Os dois diretórios

```
C:\Conteudos banco de dados tcc      ACERVO — somente leitura, nunca alterado
C:\Sistema Conciliador projeto       este repositório
```

Tratamento de arquivo é sempre `original → cópia → tratado`, com o tratado aqui.
A integridade do acervo é reconferida por script: **689 arquivos, 0 modificados**.

---

## Estrutura

```
pipeline/      13 ETLs numerados — a ordem importa; convergem numa passada
database/      schema.sql — 45 tabelas, 15 views; conciliador.db
rules/         motores determinísticos: horários e conciliação (13 módulos)
app/           interface Flask + serviços + busca + relatório + rótulos
ml/            dataset, treino, calibração, explicabilidade — FORA do caminho
models/        artefatos e calibrador (JSON; pickle só onde inevitável)
tests/         26 arquivos executáveis, sem framework
scripts/       preparar o conhecimento distribuível · gerar o .exe
auditoria/     Fase 1 + integridade do acervo
docs/          documentação, em português
data/          training · aplicacao.log · preview
```

---

## Comandos

Python não está no PATH; saída com acento quebra no console do Windows:

```bash
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"
```

Reconstruir o banco do zero e rodar a bateria inteira:

```bash
PYTHONIOENCODING=utf-8 "$PY" pipeline/executar_tudo.py --recriar
```

Sem `--recriar`, a carga é incremental — e **incremental aqui significa que
reexecutar não muda nada**. Use assim para revalidar sem perder `modelo` e
`predicao`, que `--recriar` apaga.

Subir a aplicação (`http://127.0.0.1:5000`, respeita `PORT`):

```bash
PYTHONIOENCODING=utf-8 "$PY" app/web.py
```

Um teste isolado — todos são executáveis diretos:

```bash
PYTHONIOENCODING=utf-8 "$PY" tests/teste_ponta_a_ponta.py
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_cenarios.py
```

Fora da bateria, deliberados:

```bash
PYTHONIOENCODING=utf-8 "$PY" tests/fase9_convergencia.py         # ~1 min
PYTHONIOENCODING=utf-8 "$PY" tests/teste_idempotencia.py         # ~20 s
PYTHONIOENCODING=utf-8 "$PY" auditoria/05_integridade_acervo.py  # ~3 min
PYTHONIOENCODING=utf-8 "$PY" ml/executar_tudo.py                 # ~20 min
```

Dependências do produto: **Flask**. `openpyxl` só no ETL de carga; `numpy`,
`scikit-learn` e `scipy` só em `ml/`.

---

## As garantias estruturais

Implementadas no esquema e verificadas por teste, não apenas documentadas.

1. **Posologia é estruturada.** Dose, unidade, frequência, intervalo e horário
   em colunas próprias. Texto livre acompanha, nunca substitui.
2. **Fato e previsão não se misturam.** `interacao_substancia` guarda o que a
   fonte afirma; `predicao`, o que o modelo estima. Um achado `PREVISTO` não
   tem evidência, não tem gravidade, não tem nível de evidência, e sempre
   aponta de volta ao modelo, à versão e à semente.
3. **O que não foi estabelecido fica NULL, com motivo declarado.** Nenhum campo
   clínico recebe valor inventado. **Ausência de alerta nunca é apresentada
   como ausência de risco** — o sistema declara em `nao_avaliado` tudo o que
   não avaliou.
4. **A previsão só sai por uma porta, e ela é fail-closed.**
   `vw_predicao_liberada` exige quatro condições simultâneas: modelo ativo,
   homologado, com limiar declarado e atingido, e **o par sem interação
   documentada**. Sem limiar, nada passa. Onde há documento, a previsão nem
   existe.
5. **O modelo não é trocado em silêncio.** No máximo um modelo ativo por
   problema, e ativar exige estar homologado — ato humano registrado.
6. **A conciliação classifica a situação; nunca a intencionalidade.** Diferença
   entre o prescrito e o relatado não é erro, e só sai de `NAO_DETERMINADA`
   com assinatura de profissional.

---

## O que o sistema não faz

- **Não decide conduta.** Prioriza, explica e mostra a fonte; a decisão clínica
  é do farmacêutico.
- **Não gradua gravidade que a fonte não publicou.** 65,8% das interações estão
  `NAO_DETERMINADA` porque a fonte não gradua — e isso aparece, não é escondido.
- **Não emite previsão.** Nenhum modelo está ativo, por decisão medida (D-041):
  no regime realista o recall é 0,56 e a precisão 0,39. O uso liberado do
  modelo é priorizar fila de curadoria.
- **Não avalia reação adversa nem exame laboratorial.** Declarado, não
  silenciado.

---

## Idioma

Todo o sistema em **português do Brasil** — interface, alertas, mecanismo,
efeito, relatório e documentação.

Nomenclatura científica preservada: `CYP3A4` continua `CYP3A4`. O que a
descreve sai em português: `Inibidor da CYP3A4`, não `CYP3A4 inhibitor`.

---

## Gerar o executável

```bash
PYTHONIOENCODING=utf-8 "$PY" scripts/preparar_conhecimento.py
PYTHONIOENCODING=utf-8 "$PY" scripts/build_exe.py --limpar
```

Produz `dist/SistemaConciliador/`. Instalar é copiar essa pasta — **não** para
dentro de `Arquivos de Programas`, porque o programa precisa gravar. Os
atendimentos ficam em `%LOCALAPPDATA%\ConciliadorMedicamentos` e **sobrevivem à
reinstalação**.

---

## Próximo passo

O código está completo. **A pendência que limita tudo está fora dele: zero
anotações de farmacêutico.** Sem elas não há modelo de relevância, não há
negativo verdadeiro, e nada pode ser homologado. O caminho é o piloto com dois
farmacêuticos independentes sobre os mesmos casos.

Do lado técnico, o que falta é acabamento de distribuição — instalador, ícone,
assinatura digital — listado em [EMPACOTAMENTO.md](docs/EMPACOTAMENTO.md) §10.
