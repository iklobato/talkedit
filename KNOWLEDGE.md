# KNOWLEDGE: talkedit

Estado vivo do projeto para qualquer agente ou pessoa que continue o trabalho.
Atualizado em 2026-10-29. Leia este arquivo antes de mexer no código.

- O que o produto faz: `SPEC.md` (resumo fiel do documento do dono do produto).
- Decisões técnicas curtas e comandos de desenvolvimento: `README.md`.
- Este arquivo: o que existe, o que foi descoberto, o que falta e o que vigiar.

---

## 1. Resumo em 5 linhas

1. CLI em Python (`talkedit`) que edita vídeo bruto de uma pessoa falando para a câmera, em português, num Mac Intel.
2. Etapa 1 de 7 pronta: limpeza de áudio, transcrição, IA editora, IA revisora, corte de pausas e render do vídeo do YouTube.
3. Modo de teste (`--teste`) roda tudo sem IA e sem custo.
4. A aprovação ainda é pela linha de comando (`talkedit aprovar`). A página no navegador é a etapa 2.
5. Ninguém rodou ainda com um vídeo real do dono. Só com vídeos sintéticos.

## 2. Estado do repositório

| Item | Valor |
|---|---|
| Pasta | `/Users/iklo/editor` |
| Branch | `etapa-1-video-longo`, que também é o branch padrão no GitHub (não existe `main` ainda) |
| Commit da etapa 1 | `f189747 Edit long talking-head video: clean audio, transcribe, AI cut plan, render` |
| Remoto | `origin` = https://github.com/iklobato/talkedit (público, conta pessoal `iklobato`, publicado em 2026-10-29 a pedido do dono) |
| Testes | 50 passando (`uv run pytest`), ruff e mypy limpos |
| Python | 3.11 (`.venv` criado por `uv`) |

Regra combinada com o dono: um branch e um commit por etapa entregue.

## 3. Ambiente e instalação

- Máquina alvo: Mac Intel (`x86_64`, i9-9980HK, 16 núcleos lógicos, 64 GB), sem GPU dedicada.
- Dependência de runtime: só `pydantic`. Dependências de desenvolvimento: `pytest`, `mypy`.
- Já aprovado pelo dono (2026-10-29), mas ainda não instalado: `opencv-python`, para seguir o rosto na etapa 4.
- Qualquer outra dependência nova precisa de aprovação do dono antes.

### Binários em `tools/` (fora do git)

`.gitignore` ignora `tools/ffmpeg`, `tools/ffprobe` e `tools/sh.rnnn`. Num clone novo, baixe:

```
mkdir -p tools && cd tools
curl -sL -o ffmpeg.zip https://evermeet.cx/ffmpeg/ffmpeg-9.0.2.zip
curl -sL -o ffprobe.zip https://evermeet.cx/ffmpeg/ffprobe-9.0.2.zip
unzip -o ffmpeg.zip && unzip -o ffprobe.zip && rm *.zip
xattr -d com.apple.quarantine ffmpeg ffprobe
curl -sfL -o sh.rnnn https://raw.githubusercontent.com/GregorR/rnnoise-models/master/somnolent-hogwash-2018-09-01/sh.rnnn
shasum -a 256 ffmpeg ffprobe sh.rnnn
```

O `sh.rnnn` não vai no git porque o repositório de origem (GregorR/rnnoise-models) não declara licença
(a API do GitHub responde `license: None`, conferido em 2026-10-29). Baixar é permitido; redistribuir não está claro.

| Arquivo | sha256 conferido em 2026-10-29 | No git? |
|---|---|---|
| `tools/ffmpeg` (9.0.2-tessus, x86_64) | `a45b462cf91ed89148ae218c4577e30896485d7a6792c3673bcf5f823fa01b63` | não |
| `tools/ffprobe` | `a29f8c2e03553223a8b480b1a1f04c42f680c138fa952c20086718a075db38cb` | não |
| `tools/sh.rnnn` (RNNoise de voz, GregorR/rnnoise-models, somnolent-hogwash) | `70bb6685eb0c2a1d18e2918dca3fbfbd39317010b1802eb1b6ea73a92f3fdec0` | não |

- Por que um ffmpeg próprio: o ffmpeg do brew (`/usr/local/bin/ffmpeg` 9.0.1) não tem os filtros `ass`, `subtitles` e `drawtext`. A legenda animada (etapa 4) precisa de libass.
- O link genérico `https://evermeet.cx/ffmpeg/getrelease/zip` foi desligado (HTTP 410). Use o link com a versão.

### Chave e configuração do usuário

- Chave do OpenRouter: variável `OPENROUTER_API_KEY`, ou o arquivo `~/.talkedit/chave_openrouter.txt`. Nunca imprimir o valor.
- Configuração do usuário: `~/.talkedit/config.toml`, criada por `talkedit config` a partir de `src/talkedit/config_modelo.toml`.
- Estilos do usuário: `~/.talkedit/estilos/<nome>.toml`. Os estilos que vêm prontos estão em `src/talkedit/estilos/`.
- `talkedit verificar` confere ffmpeg, filtros, modelo RNNoise, chave e se cada modelo existe no OpenRouter.

## 4. Como usar (estado atual)

O passo a passo para quem não programa está no `README.md`. Instalação como comando global, testada em clone novo em 2026-10-29: `uv tool install --editable .` (o `ToolPaths` acha `tools/` pelo caminho do código, então precisa ser `--editable`).

```
uv run talkedit verificar
uv run talkedit editar video.mp4 [--teste] [--set ritmo.ritmo=acelerado]
uv run talkedit editar "https://drive.google.com/file/d/<ID>/view?usp=sharing" [--pasta ~/Desktop]
uv run talkedit previa  <pasta ou vídeo>
uv run talkedit aprovar <pasta ou vídeo>
uv run talkedit continuar <pasta ou vídeo>
uv run talkedit refazer <pasta> <audio|transcricao|proxy|plano|revisao> [--set ...]
uv run talkedit config
```

- O projeto de cada vídeo fica em `<pasta do vídeo>/<nome>_talkedit/`. O vídeo original só é lido, nunca alterado.
- `editar` roda até a revisora e para. `aprovar` faz o render final.
- `--set` vale só para aquele projeto e fica salvo em `estado.json` (`overrides`), para `continuar` usar o mesmo valor.
- `--detalhes` mostra cada comando do ffmpeg.

### Vídeo pelo Google Drive (`src/talkedit/drive.py`)

- `editar` aceita o link de compartilhar do Drive. Os formatos aceitos são `/file/d/<ID>/...`, `open?id=<ID>`, `uc?id=<ID>` e `drive.usercontent.google.com/download?id=<ID>`. Um link de pasta (`/folders/`) é recusado com instrução.
- O arquivo precisa estar como "Qualquer pessoa com o link". Arquivo privado não é suportado: não existe login com o Google.
- O vídeo vai para `<--pasta ou ~/Movies/talkedit>/<ID>/<nome no Drive>`, e o projeto fica ao lado dele, como num vídeo local. Rodar o mesmo link de novo reaproveita o arquivo e não baixa de novo.
- Como baixa: `https://drive.usercontent.google.com/download?id=<ID>&export=download&confirm=t`. Se o Drive devolver a página "Virus scan warning", o programa lê o formulário `download-form` e segue o botão. O nome do arquivo vem do `Content-Disposition`.
- O download é por streaming (1 MB por vez) para `download.parcial` e só ganha o nome final no fim. Se o Drive recusar, o `.parcial` é apagado.
- Só stdlib (`urllib`, `html.parser`, `email.message`). Sem `gdown` e sem dependência nova.
- Link de outro site (Dropbox, YouTube) é recusado com mensagem.

### Pasta do projeto

```
<nome>_talkedit/
  estado.json            etapas feitas, modo (real/teste), overrides, aprovado
  trabalho/
    audio_limpo.wav      48 kHz mono, já no volume final (-14 LUFS)
    transcricao.json     palavras com início e fim (Transcript)
    proxy.mp4            360p, 1 quadro por segundo, sem som (vai para a IA editora)
    plano.json           cortes de conteúdo, ênfases, pausas protegidas, observações (EditPlan)
    custos.json          US$ gasto por função, informado pelo OpenRouter
    pedacos_audio/       mp3 de ~2 min enviados para a transcrição
    segmentos/           um mp4 por trecho mantido (final_*/previa_*), reaproveitados
    logs/                saída de cada comando externo
    previa.mp4
  entrega/
    youtube.mp4
    relatorio.md
```

## 5. Arquitetura

Fluxo (`src/talkedit/pipeline.py`, ordem em `workspace.STAGE_ORDER`):

```
audio -> transcricao -> proxy -> plano (IA editora) -> revisao (IA revisora) -> [aprovação] -> render
```

Cada etapa grava o resultado e marca `estado.json`. Se algo falha ou o terminal fecha, `continuar` retoma da etapa pendente.
`refazer X` apaga a marca de X e de todas as etapas seguintes, e também tira a aprovação.

| Módulo | Papel |
|---|---|
| `cli.py` | comandos em português, `CommandLine.entry` é o ponto de entrada |
| `app.py` | raiz de composição: `ProjectAssembler` monta tudo; `RunMode.TEST` usa fakes |
| `pipeline.py` | etapas (`*Step.produce`) e `Pipeline.run_until` |
| `rendering.py` | `RenderStep`, `EditRenderer` (plano -> linha do tempo -> render), `ProjectReport` |
| `settings.py`, `settings_loader.py` | config em pydantic com chaves em português; camadas: estilo < config do usuário < `--set` |
| `workspace.py` | caminhos da pasta do projeto, `ProjectState`, `Stage`, `RunMode` |
| `media.py` | `CommandRunner` (os.system + log), `MediaProbe` (ffprobe), `ToolPaths` |
| `audio.py` | cadeias de limpeza por intensidade e loudnorm em 2 passadas |
| `transcription.py` | detecção de silêncio, pedaços de ~2 min, Scribe via OpenRouter, `FakeTranscriber` |
| `openrouter.py` | cliente HTTP (urllib, 3 tentativas), chat com JSON estrito, `CostLedger` |
| `editor.py` | prompt, esquema e leitura da resposta da IA editora; `FakeEditor` |
| `reviewer.py` | texto editado com marcadores `[corte cN]`, IA revisora; `FakeReviewer` |
| `resolver.py` | `LaughterGuard` (corte com risada volta) e `PlanResolver` (pausas sobre as palavras que ficam) |
| `pacing.py` | `PauseCutter` e os perfis natural / dinâmico / acelerado |
| `timeline.py` | trechos mantidos em quadros inteiros (`FrameGrid`, `TimelineBuilder`) |
| `render.py` | segmentos em paralelo, emenda do áudio em Python, concat do ffmpeg |
| `proxy.py`, `phrases.py`, `plan.py`, `transcript.py`, `report.py`, `stores.py`, `schema.py`, `progress.py`, `doctor.py`, `errors.py` | peças de apoio |

### Decisões que não são óbvias

- **Pausas não ficam salvas no plano.** `PlanResolver.all_cuts` recalcula as pausas sobre as palavras que sobraram depois dos cortes de conteúdo. Assim um take removido não deixa duas pausas curtas coladas numa longa. Devolver ou tirar um corte na página (etapa 2) muda as pausas sozinho.
- **A IA aponta índice de palavra, não tempo.** O tempo vem da transcrição. Corte visual vem em segundos e cresce até a borda das palavras que toca. Índice inválido: o trecho fica no vídeo e entra uma observação.
- **Risada nunca sai.** `LaughterGuard` roda depois da editora e da revisora; qualquer corte que encoste num evento de risada volta com status `devolvido`.
- **Sugestão da revisora não é aplicada.** Ela pode devolver cortes (aplicado), mas o que ela sugere cortar a mais fica como `sugerido`.
- **Sincronia por quadros.** Cada trecho mantido é arredondado para quadros inteiros (`FrameGrid`), e o áudio é fatiado na amostra que corresponde àquele quadro. Trecho com menos de 3 quadros é descartado.
- **Emendas de áudio:** fade de saída e de entrada de 6 ms em cada emenda (`render.FADE_SECONDS`), sem sobreposição, para não mudar a duração.
- **Render por segmentos:** um mp4 por trecho (libx264, 2 threads cada, `cpu_count // 2` em paralelo), nome com quadro inicial, quantidade e perfil. Render de novo reaproveita os trechos que não mudaram. Junta com o concat do ffmpeg (`-c:v copy`) e codifica o áudio uma vez só (AAC; evita o problema do priming do AAC por segmento).
- **Proxy da IA:** `-skip_frame nokey` (decodifica só keyframes) + `fps=1` + 360p + crf 34, sem som.
- **Transcrição em pedaços:** cerca de 120 s, com o corte movido para o meio do silêncio mais próximo (até 20 s de distância). Até 4 pedaços em paralelo. Motivo: a doc do OpenRouter diz que o provedor desiste depois de 60 s por pedido.

### Modelos padrão (escolhidos em 2026-10-29 pela lista `/api/v1/models`)

| Função | Modelo | Preço na lista |
|---|---|---|
| transcrição | `elevenlabs/scribe-v2` | 0.0000611 por segundo de áudio (conferido: 33.8 s custaram US$ 0.00198) |
| editora | `google/gemini-4-argon` (vídeo + JSON estrito) | US$ 2 / 10 por milhão de tokens (entrada / saída) |
| revisora | `google/gemini-3.5-flash-lite` (só texto) | US$ 0.30 / 2.50 por milhão de tokens |

Formatos usados (da doc atual do OpenRouter, não inventados):
- Transcrição: `POST /api/v1/audio/transcriptions` com `input_audio {data, format}`, `language`, `response_format: verbose_json`, `timestamp_granularities: ["word"]`, `keyterms` (palavras difíceis). As palavras vêm com `type: word | audio_event`.
- Chat: `POST /api/v1/chat/completions` com `video_url` em data URL base64 e `response_format` `json_schema` `strict: true`. O custo vem em `usage.cost`.
- Para listar modelos de transcrição: `/api/v1/models?output_modalities=all`. Sem esse parâmetro, o Scribe não aparece.

## 6. Descobertas (com prova)

1. **O ffmpeg 9.0.2 trava com `arnndn` seguido de `speechnorm`**: CPU em 100 % parada no fim do arquivo, e não morre com SIGTERM. Prova (2026-10-29, vídeo de 33 s, `timeout -s KILL 8`):
   ```
   rc=0 1s :: arnndn=m=M,afftdn=nr=8:nf=-50
   rc=137 8s :: arnndn=m=M,speechnorm=e=4:r=0.0001:l=1
   ```
   Pôr `asetnsamples` entre os dois não resolveu. Trocamos por `dynaudnorm`, que roda em 1 s. Não volte para `speechnorm` depois de `arnndn`.
2. **Todo comando externo roda com `< /dev/null`** (`CommandRunner`), para o ffmpeg nunca esperar teclado.
3. **IA real acertou o vídeo sintético de teste** (`say -v Luciana` com take abandonado e "corta isso"): 3 cortes, os 3 certos. Custo total de US$ 0.0121 (transcrição 0.0020, editora 0.0098, revisora 0.0003).
4. **Nenhuma palavra cortada nesse teste**: transcrevi o `youtube.mp4` final de novo e saiu completo, "Hoje eu vou falar sobre como economizar dinheiro. ... Era isso, valeu".
5. **Sincronia:** vídeo com 14.247567 s e áudio com 14.247542 s. Volume final de -13.6 LUFS (meta -14).
6. **Tempo num vídeo sintético de 15 min em 1080p** (modo de teste, sem IA, 2026-10-29):
   - limpeza de áudio: 46 s em cada uma das 2 passadas (19.6x tempo real), 92 s no total
   - proxy: 3 s
   - plano completo sem IA: 96 s
   - render final (11:10 de saída, crf 18, preset medium, 235 trechos): 1413 s (23.5 min). Meta: 30 min.
   - Atenção: `testsrc2` é difícil de codificar e tem keyframes regulares. Vídeo de câmera real pode ser mais rápido ou mais lento. Não medido.
7. **Download real do Drive testado em 2026-10-29** com um arquivo público grande (498 MB, `1l_5RK28JRL19wpT22B-DY9We3TVXnnQQ`, um `.npz` de exemplo do gdown, não é vídeo):
   - O Drive entregou o arquivo direto com `confirm=t` (`206 application/octet-stream`, `content-disposition: attachment; filename="fcn8s_from_caffe.npz"`). Sem `confirm=t`, veio a página `Google Drive - Virus scan warning`.
   - Chegaram 498881336 bytes, igual ao `content-range: bytes 0-2047/498881336`. O comando inteiro levou 68 s (cerca de 4.5 MB/s nesta rede).
   - Link inexistente: o Drive responde `404 text/html`, e o programa mostra "respondeu erro 404" com a instrução de compartilhar.
   - Dois bugs achados e corrigidos com teste: um `editar` que falhava ao abrir o vídeo deixava `estado.json` para trás e travava a nova tentativa; e a busca de "já baixado" podia pegar a pasta `<nome>_talkedit/` em vez do vídeo.
   - Ainda não testado com um vídeo real no Drive nem com arquivo privado (o esperado é a página de login cair na mensagem "não está público").
8. **Regras de código aplicadas por hook** (`~/.claude/hooks/immutable-rules-check.py`) em todo `.py`, inclusive testes: toda função dentro de classe, `__init__` só atribui, no máximo 3 parâmetros, métodos com até 20 linhas, sem `elif`, sem número solto (só 0 e 1), sem nome vago (`result`, `run`, `data`, uma letra), sem estado global mutável (use `MappingProxyType` como atributo de classe), sem `print`, sem `subprocess`. Os testes usam classes com constantes nomeadas por isso. Arquivos de código devem ser escritos com Write/Edit, não por redirecionamento do shell (outro hook bloqueia).

## 7. O que foi feito (etapa 1)

- [x] 5.1 Limpeza de áudio grátis com 4 intensidades (`desligado`, `leve`, `normal`, `forte`) e loudnorm em 2 passadas
- [x] 5.2 Transcrição com tempo por palavra, eventos de som e palavras difíceis (`keyterms`)
- [x] 5.3 Ritmo natural / dinâmico / acelerado, sem cortar palavra, pausa protegida pela editora
- [x] 5.4 IA editora com vídeo leve, motivo em português, regras do usuário, postura por estilo
- [x] 5.5 IA revisora só de texto: devolve cortes, sugere mais, deixa observações
- [x] 5.14 (parte) CLI em português, retomar, refazer parte, `verificar`, erros com "O que fazer"
- [x] 5.15 (parte) config comentada em português, `--set`, estilos `dinamico` e `natural`, modelo por função
- [x] 5.16 Modo de teste com fakes
- [x] 5.17 (parte) custo real por função e relatório em markdown
- [x] Render do YouTube na resolução original, com emendas suaves e prévia em 360p
- [x] Entrada por link público do Google Drive (`editar <link>`, `--pasta`), fora da spec, pedida pelo dono em 2026-10-29

## 8. O que falta

### Pendências da etapa 1

- [ ] Rodar com um vídeo real do dono (de 2 a 5 min) e medir custo, tempo e qualidade das emendas de ouvido.
- [ ] Estimativa de custo antes de começar (5.17): usar a duração do vídeo e os preços de `/api/v1/models`.
- [ ] Tempo restante do fluxo inteiro antes de começar (5.14). Hoje só existe por tarefa (render).
- [ ] Opção paga Auphonic (5.1).
- [ ] `continuar` num projeto já aprovado e renderizado não mostra nada; deveria dizer onde está a entrega.
- [ ] Download do Drive interrompido recomeça do zero (não usa `Range`). Só importa com vídeo de vários GB.
- [ ] Testar com um vídeo real no Drive e com um link privado.

### Próximas etapas (ordem de `SPEC.md` seção 7)

2. **Página de revisão, aba Edição** (5.6): servidor local feito só com Python (`http.server`) + HTML/JS puro, offline, estado em disco. Usar `PlanResolver` e `EditRenderer.render(..., RenderProfile.preview())` para a prévia. Os cortes já têm `status` (`aplicado`, `devolvido`, `sugerido`) e `source` (`voce` para corte manual). "Refazer o plano com pedido em texto" precisa de um campo novo no prompt da editora.
3. **Estilo dinâmico** (5.7): disfarce de jump cut (alternar enquadramento por segmento) e zoom de ênfase (`EditPlan.emphasis` já vem da editora, ainda sem uso). O render por segmento facilita: o `crop`/`scale` entra no `-vf` de cada trecho. Também a legenda `.srt` do YouTube: precisa de uma função que leve o tempo original para o tempo editado (`Timeline`).
4. **Cortes verticais** (5.8, 5.9, 5.10): instalar `opencv-python` (já aprovado), detector de rosto YuNet em resolução baixa, legenda ASS karaokê queimada com o filtro `ass` do `tools/ffmpeg`, área segura comum de Shorts, Reels e TikTok, aba Cortes. Modelo de cortes barato com vídeo.
5. **Textos e thumbnail** (5.11, 5.12), aba Textos.
6. **Página de publicação** (5.13).
7. **`GUIA.md`** para quem não programa: instalação no Mac Intel, chave, uso, config, custo.

## 9. O que vigiar

| Risco | Por quê | Como checar |
|---|---|---|
| Custo da editora em vídeo longo | Gemini cobra cada quadro do vídeo; 15 min ainda não foi medido com IA real. A meta é menos de US$ 1 por vídeo de 15 min no total. | `trabalho/custos.json` depois de um vídeo real de 15 min. Se passar de ~US$ 0.60 só na editora, trocar o vídeo por folhas de quadros (imagens) ou baixar a taxa de quadros. |
| Tamanho do proxy no pedido | O vídeo vai em base64 dentro do JSON; o limite do provedor não foi testado. O proxy sintético de 15 min tinha 704 KB. | Tamanho de `trabalho/proxy.mp4` num vídeo real. Se a editora der erro de tamanho, dividir em partes. |
| Keyframes raros em vídeo de celular | `-skip_frame nokey` usa só keyframes; com GOP longo, a IA vê menos quadros do que 1 por segundo. | `ffprobe -skip_frame nokey -select_streams v -show_entries frame=pts_time` no vídeo real. |
| Fim de palavra comido | A folga em volta das palavras é fixa (`PaceProfiles`), baseada no tempo do Scribe. | Ouvir as emendas e transcrever o `youtube.mp4` de novo. Se acontecer, mover o corte para o ponto mais silencioso da pausa (está marcado com `ponytail:` em `pacing.py`). |
| Risada não reconhecida | `Word.is_laughter` procura "laugh", "ris" ou "gargalh" no texto do evento. O formato real que o Scribe usa para risada em português não foi visto ainda. | Procurar `audio_event` em `transcricao.json` de um vídeo com risada. |
| Modelos com alias que mudam | Nomes de modelo saem e entram no OpenRouter. | `talkedit verificar` antes de cada uso longo. |
| Travamento do ffmpeg | Ver a descoberta 1. Se uma etapa de áudio passar de alguns minutos num vídeo curto, é isso. | `ps aux \| grep tools/ffmpeg` e o tempo no log em `trabalho/logs/`. |
| Mudança no download do Drive | O fluxo depende de `confirm=t` e do formulário `download-form`, que o Google pode mudar sem aviso. Também há limite diário de downloads por arquivo. | Se `editar <link>` disser "mostrou uma pagina em vez do video" para um arquivo público, salve a página baixada e confira o HTML. |
| Tempo de render | 23.5 min para 15 min sintéticos em 1080p, perto da meta de 30. Vídeo 4K vai demorar mais. | Medir com vídeo real. A config `render.velocidade_x264 = "fast"` é a válvula. |

## 10. Testes

- `tests/test_end_to_end.py` gera um vídeo de 12 s (tom de 220 Hz com silêncio), roda `editar --teste` e `aprovar`, e confere a sincronia, o encurtamento e o relatório. Também protege contra a volta do travamento do ffmpeg, porque usa a limpeza `normal`.
- Os testes de unidade cobrem pausas, linha do tempo, emenda de áudio, leitura da resposta da editora e da revisora, trava de risada, config, estado, pedaços de transcrição, cliente OpenRouter (com transporte falso), progresso (com relógio falso) e download do Drive (`tests/test_drive.py`, com `FakeFetcher` no lugar da internet). São 50 testes no total.
- Os vídeos de teste da sessão de 2026-10-29 ficaram no scratchpad temporário do Claude e podem sumir. Para recriar o vídeo falado:
  ```
  say -v Luciana -o fala.aiff "oi gente, deixa eu ver se ta gravando. [[slnc 2000]] Hoje eu vou falar ..."
  tools/ffmpeg -f lavfi -i "testsrc2=size=1280x720:rate=30000/1001" -i fala.aiff \
    -f lavfi -i "anoisesrc=color=brown:amplitude=0.03:sample_rate=48000" \
    -filter_complex "[1:a]aresample=48000[v];[v][2:a]amix=inputs=2:duration=first:normalize=0[a]" \
    -map 0:v -map "[a]" -shortest -c:v libx264 -c:a aac bruto.mp4
  ```

## 11. Regras de trabalho deste projeto

- Fale com o dono em português simples. Código, comentários, commits e identificadores em inglês. Textos que o usuário vê (CLI, config, relatório) em português.
- Não instale dependência nova sem perguntar.
- Não publique nada fora da máquina. A v1 não publica vídeo.
- Ao fim de cada etapa: testes, ruff e mypy passando; um commit no branch da etapa; e diga ao dono o que ele pode testar e como.
- Atualize este arquivo quando algo daqui mudar.
