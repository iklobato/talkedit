# talkedit

Editor de vídeo com IA para quem grava sozinho falando para a câmera, em português.

Você entrega o vídeo bruto (um arquivo no Mac ou um link do Google Drive). O talkedit limpa o
áudio, transcreve, corta pausas, takes repetidos e erros, mostra o plano para você aprovar e
entrega o vídeo pronto para o YouTube. O vídeo original nunca é alterado.

> **Estado atual: etapa 2 de 7.** Já funciona: limpeza de áudio, transcrição, cortes pela IA,
> revisão por uma segunda IA, prévia, vídeo final do YouTube e uma **página no navegador** para
> mandar o vídeo (arrastando ou por link do Drive), acompanhar, revisar os cortes, aprovar e
> salvar seus padrões. Ainda **não** tem: zoom e troca de enquadramento, legenda do YouTube,
> cortes verticais (Shorts, Reels, TikTok), textos por plataforma e thumbnail. O plano completo
> está em [`SPEC.md`](SPEC.md).

---

## Índice

1. [Instalação (uma vez só)](#1-instalação-uma-vez-só)
2. [Editar um vídeo](#2-editar-um-vídeo)
3. [Comandos](#3-comandos)
4. [O que fica em cada pasta](#4-o-que-fica-em-cada-pasta)
5. [Configuração](#5-configuração)
6. [Custo e tempo](#6-custo-e-tempo)
7. [Problemas comuns](#7-problemas-comuns)
8. [Para quem vai mexer no código](#8-para-quem-vai-mexer-no-código)

---

## 1. Instalação (uma vez só)

Feito para Mac com processador Intel. Abra o app **Terminal** e cole um bloco por vez.

### 1.1 Instale o `uv`

Ele cuida do Python para você.

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Feche e abra o Terminal de novo.

### 1.2 Baixe o talkedit

```
cd ~
git clone https://github.com/iklobato/talkedit.git
cd talkedit
```

### 1.3 Baixe o ffmpeg e o modelo de limpeza de voz

Eles não vão junto no código. Rode isto dentro da pasta `talkedit`:

```
mkdir -p tools && cd tools
curl -sL -o ffmpeg.zip https://evermeet.cx/ffmpeg/ffmpeg-9.0.2.zip
curl -sL -o ffprobe.zip https://evermeet.cx/ffmpeg/ffprobe-9.0.2.zip
unzip -o ffmpeg.zip && unzip -o ffprobe.zip && rm *.zip
xattr -d com.apple.quarantine ffmpeg ffprobe
curl -sfL -o sh.rnnn https://raw.githubusercontent.com/GregorR/rnnoise-models/master/somnolent-hogwash-2018-09-01/sh.rnnn
cd ..
```

Use esse ffmpeg e não o do Homebrew: o do Homebrew não tem o recurso de legenda que as próximas
etapas usam.

### 1.4 Instale o comando `talkedit`

```
uv tool install --editable .
uv tool update-shell
```

Feche e abra o Terminal de novo. A partir daqui, `talkedit` funciona em qualquer pasta.

### 1.5 Coloque a sua chave do OpenRouter

Pegue a chave em https://openrouter.ai/settings/keys e salve num arquivo (troque `sk-or-...`
pela sua chave):

```
mkdir -p ~/.talkedit
echo "sk-or-..." > ~/.talkedit/chave_openrouter.txt
```

Também funciona com a variável `OPENROUTER_API_KEY`, se você já usa ela.

### 1.6 Confira se está tudo certo

```
talkedit verificar
```

O esperado é algo assim:

```
Verificando a instalacao:
  ok   ffmpeg em /Users/voce/talkedit/tools/ffmpeg
  ok   filtros do ffmpeg: ok
  ok   modelo de limpeza de voz em /Users/voce/talkedit/tools/sh.rnnn
  ok   chave do OpenRouter aceita
  ok   modelo de transcricao: elevenlabs/scribe-v2
  ok   modelo de editora: google/gemini-4-argon
  ok   modelo de revisora: google/gemini-3.5-flash-lite

Tudo certo.
```

Se alguma linha mostrar `ERRO`, veja [Problemas comuns](#7-problemas-comuns).

---

## 2. Editar um vídeo

Dois jeitos: pela **página no navegador** (mais fácil) ou pelo **Terminal**. Os dois mexem nos
mesmos projetos.

### Pela página

```
talkedit abrir
```

O navegador abre sozinho. Deixe o Terminal aberto enquanto usa a página; para fechar, `Ctrl+C`
no Terminal.

1. **Novo vídeo:** arraste o vídeo para a área tracejada (ou clique nela para escolher), ou cole
   o link do Google Drive. Escolha o estilo, marque "Modo de teste" se quiser sem custo, e clique
   em **Começar edição**. O vídeo arrastado é copiado para `~/Movies/talkedit/`.
2. **Em andamento:** mostra cada etapa com ✓, o tempo e o custo até agora. Pode fechar a aba; o
   trabalho continua enquanto o Terminal estiver aberto.
3. **Revisão:** quando a IA termina, aparece o vídeo com a linha do tempo (vermelho sai, laranja é
   sugestão da revisora) e a lista de trechos. Em cada trecho: ▶ para ouvir, **Devolver** ou
   **Tirar**. Arraste na linha do tempo para marcar um trecho novo para sair. Dá para pedir à IA
   que refaça o plano escrevendo o que quer ("está cortando demais").
4. **Gerar prévia** para assistir o resultado em baixa qualidade, e **Aprovar e gerar vídeo** para o
   final. Pronto, o botão **Abrir pasta no Finder** mostra a entrega.
5. **Padrões:** estilo, ritmo, limpeza da voz, palavras difíceis, regras para a editora e qualidade.
   **Salvar padrões** grava no `~/.talkedit/config.toml`, que o Terminal também usa.

A página só funciona no próprio Mac: ela usa um endereço com um código secreto que o
`talkedit abrir` cria a cada vez.

### Pelo Terminal

São 3 passos: **editar**, olhar a **prévia** e **aprovar**.

#### Passo 1: editar

Com um arquivo do Mac:

```
talkedit editar ~/Movies/gravacao.mp4
```

Ou com um link do Google Drive:

```
talkedit editar "https://drive.google.com/file/d/XXXX/view?usp=sharing"
```

Para o link funcionar, o vídeo precisa estar compartilhado como "Qualquer pessoa com o link". No
Drive: botão direito no vídeo > **Compartilhar** > Acesso geral: **Qualquer pessoa com o link** >
**Copiar link**. Ponha o link entre aspas. O vídeo é salvo em `~/Movies/talkedit/`; para salvar em
outro lugar, acrescente `--pasta ~/Desktop`.

O talkedit mostra cada etapa e para no fim com o plano:

```
[1/6] Limpando o audio
[2/6] Transcrevendo a fala
[3/6] Fazendo a copia leve do video para a IA
[4/6] Fazendo a copia do video para assistir na revisao
[5/6] IA editora escolhendo o que sai
[6/6] IA revisora conferindo a edicao

00:33 vai ficar com 00:14, 3 trechos removidos

  c1  00:00 a 00:02, 'Oi gente, deixa eu ver se tá gravando.', conversa antes de comecar, ...
  c2  00:09 a 00:13, 'O primeiro ponto é-- não, corta isso.', comando para a edicao, ...
  c3  00:31 a 00:32, 'Pronto, pode parar', conversa depois de terminar, ...
  obs: Os cortes foram bem feitos e o sentido do video esta preservado.

Custo ate agora: US$ 0.0121

Proximo passo:
  talkedit previa /Users/voce/Movies/gravacao_talkedit    (previa rapida em baixa qualidade)
  talkedit aprovar /Users/voce/Movies/gravacao_talkedit   (renderiza o video final)
```

Cada trecho cortado vem com o horário, o que foi falado e o motivo. As pausas longas também são
encurtadas, mas não aparecem nessa lista; o total delas está no relatório final.

#### Passo 2: olhar a prévia (opcional, mas recomendado)

```
talkedit previa /Users/voce/Movies/gravacao_talkedit
```

Gera `trabalho/previa.mp4` em baixa qualidade, bem rápido, para você assistir o resultado antes do
render final.

Não gostou do plano? Refaça a etapa com outra opção (veja [Configuração](#5-configuração)):

```
talkedit refazer /Users/voce/Movies/gravacao_talkedit plano --set estilo=natural
```

#### Passo 3: aprovar

```
talkedit aprovar /Users/voce/Movies/gravacao_talkedit
```

O vídeo final fica em `entrega/youtube.mp4` e o relatório em `entrega/relatorio.md`.

#### Testar sem gastar nada

Acrescente `--teste`: o fluxo inteiro roda com respostas simuladas e sem IA. Serve para conferir a
instalação, o ritmo e o render.

```
talkedit editar ~/Movies/gravacao.mp4 --teste
```

---

## 3. Comandos

Onde está escrito `<pasta>`, você pode passar a pasta do projeto (`..._talkedit`) ou o caminho do
vídeo original.

| Comando | O que faz |
|---|---|
| `talkedit abrir` | Abre a página no navegador (fecha com `Ctrl+C`) |
| `talkedit editar <vídeo ou link>` | Começa um vídeo novo e para no plano para você aprovar |
| `talkedit previa <pasta>` | Gera uma prévia rápida em baixa qualidade |
| `talkedit aprovar <pasta>` | Aprova o plano e gera o vídeo final |
| `talkedit continuar <pasta>` | Retoma de onde parou (terminal fechado, internet caiu, erro) |
| `talkedit refazer <pasta> <etapa>` | Refaz uma etapa e todas as seguintes |
| `talkedit verificar` | Confere instalação, chave e modelos |
| `talkedit config` | Cria e mostra o seu arquivo de configuração |

Opções:

| Opção | Vale para | O que faz |
|---|---|---|
| `--teste` | `editar` | Sem IA e sem custo |
| `--pasta <pasta>` | `editar` com link | Onde salvar o vídeo baixado do Drive |
| `--set secao.opcao=valor` | `editar`, `refazer`, `verificar` | Muda uma opção só neste projeto. Pode repetir. |
| `--porta <número>` / `--sem-navegador` | `abrir` | Escolhe a porta / só mostra o endereço, sem abrir o navegador |
| `--detalhes` | todos (antes do comando) | Mostra cada comando do ffmpeg: `talkedit --detalhes editar ...` |

Etapas que dá para refazer, em ordem: `audio`, `transcricao`, `proxy`, `player`, `plano`, `revisao`. Refazer
uma etapa também refaz as que vêm depois e tira a aprovação.

---

## 4. O que fica em cada pasta

O projeto fica ao lado do vídeo, com o mesmo nome e `_talkedit` no fim:

```
gravacao.mp4                 seu vídeo original, nunca alterado
gravacao_talkedit/
  entrega/
    youtube.mp4              vídeo final (mesma resolução do original)
    relatorio.md             o que saiu e por quê, duração antes e depois, custo
  trabalho/                  arquivos do processo (pode apagar depois de publicar)
    previa.mp4
    player.mp4               cópia leve para o player da página de revisão
    audio_limpo.wav
    transcricao.json
    plano.json
    custos.json
    logs/                    saída de cada comando, útil quando algo dá erro
  estado.json                em que etapa o projeto está
```

---

## 5. Configuração

O jeito mais fácil é a tela **Padrões** da página (`talkedit abrir`). Pelo Terminal, rode
`talkedit config` uma vez. Os dois gravam `~/.talkedit/config.toml`, com uma explicação em
português de cada opção. Para abrir: `open -e ~/.talkedit/config.toml`. O que você muda ali vale
para todos os vídeos.

| Opção | Valores | Padrão |
|---|---|---|
| `estilo` | `dinamico` (ritmo de YouTube atual) ou `natural` (corta só erros e pausas longas) | `dinamico` |
| `audio.limpeza` | `desligado`, `leve`, `normal`, `forte` | `normal` |
| `audio.volume_alvo_lufs` | volume final; -14 é o padrão do YouTube | `-14` |
| `transcricao.palavras_dificeis` | lista de nomes, marcas e termos que a transcrição erra | vazia |
| `editora.regras` | regras suas em português, ex.: `["nunca corte quando eu mostro um produto"]` | vazia |
| `ritmo.ritmo` | `natural`, `dinamico`, `acelerado` | vem do estilo |
| `modelos.transcricao` / `modelos.editora` / `modelos.revisora` | nome do modelo no OpenRouter | ver `talkedit verificar` |
| `render.qualidade_crf` | qualidade da imagem; 18 fica igual ao original a olho | `18` |
| `render.velocidade_x264` | `fast` fica pronto antes, `slow` gera arquivo menor | `medium` |

Para mudar só num vídeo, sem mexer no arquivo, use `--set`:

```
talkedit editar video.mp4 --set ritmo.ritmo=acelerado --set audio.limpeza=forte
```

**Criar o seu estilo:** copie `src/talkedit/estilos/dinamico.toml` para
`~/.talkedit/estilos/meu.toml`, mude o que quiser e ponha `estilo = "meu"` no `config.toml`.

---

## 6. Custo e tempo

Medido em 2026-10-29, neste Mac Intel (i9, 16 núcleos lógicos):

| O que | Resultado | Observação |
|---|---|---|
| Custo de um vídeo de 33 s com IA real | US$ 0.0121 | transcrição 0.0020, editora 0.0098, revisora 0.0003 |
| Plano de um vídeo de 15 min, sem IA (`--teste`) | 96 s | limpeza de áudio, transcrição simulada, cópia leve |
| Render final de 15 min em 1080p | 23.5 min | vídeo sintético; ficou com 11:10 |

Ainda **não medido**: custo e tempo de um vídeo real de 15 min com IA. A meta é menos de US$ 1 por
vídeo de 15 min. O custo real de cada vídeo fica em `trabalho/custos.json` e no relatório.

---

## 7. Problemas comuns

Todo erro aparece em português, com uma linha "O que fazer".

| Mensagem | O que fazer |
|---|---|
| Página: `Acesso negado.` ou `Esta pagina precisa do endereco completo.` | Rode `talkedit abrir` de novo; cada vez ele cria um endereço novo. |
| Página: `Ja tem um video sendo processado.` | O talkedit faz um vídeo por vez. Espere o atual terminar (aba "Em andamento"). |
| Página não abre (`não foi possível conectar`) | O Terminal com `talkedit abrir` foi fechado. Rode de novo. |
| `Nao achei a chave do OpenRouter.` | Faça o passo [1.5](#15-coloque-a-sua-chave-do-openrouter). |
| `O OpenRouter recusou a chave.` | A chave está errada ou foi apagada. Gere outra no site do OpenRouter. |
| `Acabou o credito no OpenRouter.` | Coloque crédito em https://openrouter.ai/settings/credits e rode `talkedit continuar <pasta>`. |
| `O Google Drive respondeu erro 404` ou `mostrou uma pagina em vez do video` | O vídeo não está como "Qualquer pessoa com o link". Arquivo privado não funciona. |
| `Esse link e de uma pasta do Google Drive` | Abra a pasta e copie o link do vídeo, não da pasta. |
| `Nao consegui abrir ... como video.` | O arquivo não é um vídeo ou está corrompido. Teste se ele abre no QuickTime. |
| `Este video ja tem um projeto em ...` | Use `talkedit continuar <pasta>`, ou apague a pasta `_talkedit` para começar do zero. |
| `ffmpeg nao encontrado` (no `talkedit verificar`) | Faça o passo [1.3](#13-baixe-o-ffmpeg-e-o-modelo-de-limpeza-de-voz). |
| `zsh: command not found: talkedit` | Faça o passo [1.4](#14-instale-o-comando-talkedit) e abra um Terminal novo. |
| O Mac diz que o ffmpeg "não pode ser aberto" | Rode `xattr -d com.apple.quarantine tools/ffmpeg tools/ffprobe` dentro da pasta `talkedit`. |

Parou no meio (terminal fechado, `Ctrl+C`, internet caiu)? O que já estava pronto fica salvo.
Rode `talkedit continuar <pasta>`.

---

## 8. Para quem vai mexer no código

- **Leia [`KNOWLEDGE.md`](KNOWLEDGE.md) primeiro**: estado atual, arquitetura, descobertas com
  prova, o que falta e o que vigiar.
- O produto completo está descrito em [`SPEC.md`](SPEC.md).
- Python 3.11 com uma dependência só (`pydantic`). `pytest` e `mypy` só para desenvolvimento.

```
uv sync
uv run pytest
uv run ruff check src tests
uv run mypy src
uv run talkedit editar video.mp4 --teste
```
