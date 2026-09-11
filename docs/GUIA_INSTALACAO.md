# Guia de instalação — Conciliador de Medicamentos

Para quem vai **usar** o programa. Não é preciso saber programar, e não é
preciso instalar Python.

---

## Antes de tudo

> Este sistema **apoia** a conciliação medicamentosa; não a substitui.
> Nenhum achado dele foi revisado por farmacêutico e nenhum modelo preditivo
> está homologado. A decisão clínica permanece do profissional.

---

## 1. Instalar

1. Copie a pasta **`SistemaConciliador`** inteira para o computador.
   Um bom lugar é `C:\SistemaConciliador` ou a sua pasta de Documentos.
2. Abra a pasta e dê dois cliques em **`SistemaConciliador.exe`**.

Pronto. Não há instalador, não há "próximo, próximo, concluir".

**Não coloque a pasta dentro de `C:\Arquivos de Programas`.** O Windows não
deixa programas comuns gravarem ali, e o programa precisa gravar os
atendimentos. Se você fizer isso, ele avisa e não abre — em vez de abrir e
perder o atendimento no meio.

### O que acontece na primeira vez

Uma janela preta abre e mostra o endereço do programa. Em seguida o navegador
abre sozinho. Se não abrir, copie o endereço que aparece na janela preta —
algo como `http://127.0.0.1:5000` — e cole no navegador.

**Não feche a janela preta enquanto estiver usando.** Ela é o programa. Fechá-la
encerra o sistema (os atendimentos já gravados continuam salvos).

---

## 2. Onde ficam os seus dados

Os atendimentos **não** ficam na pasta do programa. Ficam em:

```
C:\Users\<seu usuário>\AppData\Local\ConciliadorMedicamentos
```

Dentro dela:

| Pasta | O que tem |
|---|---|
| `database\conciliador.db` | **os seus atendimentos e o conhecimento em uso** |
| `backups\` | cópias de segurança |
| `data\aplicacao.log` | registro do que o programa fez, para diagnóstico |
| `config\` | configuração da instalação |

Isso é de propósito: você pode apagar e reinstalar a pasta do programa que
**os atendimentos continuam lá**.

### Quero guardar os dados em outro lugar

Crie um atalho e acrescente a variável `CONCILIADOR_DADOS`. Exemplo, para
usar um pendrive:

```
set CONCILIADOR_DADOS=E:\ConciliadorDados
SistemaConciliador.exe
```

---

## 3. Fazer backup

O arquivo que importa é um só:

```
C:\Users\<seu usuário>\AppData\Local\ConciliadorMedicamentos\database\conciliador.db
```

Copie-o para onde quiser (pendrive, nuvem, outra pasta). **Feche o programa
antes de copiar** — copiar um banco aberto pode gravar uma cópia pela metade.

Para restaurar: feche o programa e coloque o arquivo de volta, com o mesmo
nome, no mesmo lugar.

O programa também guarda uma cópia automática em `backups\` antes de qualquer
atualização do conhecimento.

---

## 4. Atualizar o conhecimento

Quando houver uma versão nova da base (medicamentos, interações, regras), você
recebe um arquivo `conhecimento.db`. **Não troque o arquivo à mão** — isso
apagaria os seus atendimentos.

Use o utilitário de atualização, que faz backup antes, confere se a versão
nova é compatível e **preserva todos os atendimentos**:

```
SistemaConciliador.exe --atualizar-conhecimento caminho\para\conhecimento.db
```

Se a versão nova for incompatível ou o arquivo estiver corrompido, a
atualização é **recusada** e nada muda.

---

## 5. Quando alguma coisa dá errado

O programa foi feito para **explicar** em vez de sumir. A janela preta mostra
a mensagem e espera você ler.

| O que aparece | O que fazer |
|---|---|
| "A pasta de dados não aceita gravação" | Mova a pasta do programa para fora de `Arquivos de Programas` |
| "O banco de dados não foi encontrado" | A instalação está incompleta — copie a pasta do programa de novo |
| "O banco está corrompido" | Restaure uma cópia da pasta `backups\` |
| "A porta 5000 estava ocupada" | Nada a fazer: ele já usou outra e avisou qual |
| O navegador não abriu | Copie o endereço da janela preta e cole no navegador |

Para um diagnóstico completo, abra o Prompt de Comando na pasta do programa e
rode:

```
SistemaConciliador.exe --diagnostico
```

Ele imprime onde cada coisa está, se o banco abre e qual a versão do
conhecimento — e sai sem iniciar o servidor.

---

## 6. Desinstalar

Apague a pasta do programa.

**Os seus atendimentos continuam** em
`C:\Users\<seu usuário>\AppData\Local\ConciliadorMedicamentos`. Se quiser
apagá-los também, apague essa pasta — mas ela é a única cópia, então faça um
backup antes se houver qualquer dúvida.

---

## 7. O que o programa precisa

| | |
|---|---|
| Sistema | Windows 10 ou 11, 64 bits |
| Python | **não é necessário** — já vem embutido |
| Internet | **não é necessária** — tudo funciona offline |
| Espaço | cerca de 100 MB |
| Permissão de administrador | **não é necessária** |

Nenhum dado sai do computador. O programa não envia nada para lugar nenhum.
