# KNOWLEDGE: talkedit

Estado vivo do projeto, para qualquer agente ou pessoa que continue o trabalho.
Última atualização: 2026-10-29. Leia este arquivo inteiro antes de mexer no código.

| Arquivo | Para quem | Conteúdo |
|---|---|---|
| `README.md` | o dono (não programa) | instalação, como usar, comandos, config, custo, erros comuns |
| `SPEC.md` | todos | o que o produto deve fazer (resumo fiel do documento do dono) |
| `KNOWLEDGE.md` | agentes e devs | este arquivo: implementação, decisões, descobertas, pendências, riscos |

---

## 1. Resumo

1. CLI em Python (`talkedit`) que edita vídeo bruto de uma pessoa falando para a câmera, em português, num Mac Intel. Todos os modelos de IA passam pelo OpenRouter.
2. **Etapa 1 de 7 entregue**: limpeza de áudio, transcrição, IA editora, IA revisora, corte de pausas, prévia e render do vídeo do YouTube.
3. Extra pedido pelo dono, fora da spec: o vídeo pode vir de um **link público do Google Drive**.
4. A aprovação ainda é pelo Terminal (`talkedit aprovar`). A página no navegador é a etapa 2.
5. Modo de teste (`--teste`) roda tudo sem IA e sem custo.
6. **Ainda ninguém rodou com um vídeo real do dono.** Só com vídeos sintéticos. Esta é a próxima ação.

## 2. Estado do repositório

| Item | Valor |
|---|---|
| Pasta local | `/Users/iklo/editor` |
| Remoto | `origin` = https://github.com/iklobato/talkedit, público, conta pessoal `iklobato` |
| Branch | `etapa-1-video-longo`, também é o branch padrão no GitHub. Não existe `main`. |
| Último commit | `2c98c90 Rewrite README as a step by step guide for the creator`, igual no local e no GitHub |
| Licença | nenhuma (GitHub responde `license=null`). Decisão pendente do dono. |
| Testes | 50 passando (`uv run pytest`), ruff e mypy limpos |
| Python | 3.11 (`.venv` criado por `uv`) |

Histórico, do mais novo para o mais antigo:

| Commit | O que fez |
|---|---|
| `2c98c90` | README virou guia passo a passo para o dono |
| `3716df9` | constantes do download do Drive movidas para as classes donas |
| `c668b9b` | entrada por link público do Google Drive |
| `1c5f821` | KNOWLEDGE aponta para o commit publicado |
| `bc6895a` | modelo RNNoise fora do git (origem sem licença) |
| `d404cef` | primeiro KNOWLEDGE.md |
| `f189747` | etapa 1 inteira |

O histórico foi reescrito uma vez, antes da primeira publicação, para tirar `tools/sh.rnnn` de todos os commits. Os hashes antigos `b2ef206` e `9d8320f` não existem mais. Depois de publicado, o histórico nunca foi reescrito; não reescreva.

## 3. Ambiente e instalação

- Máquina alvo: Mac Intel (`x86_64`, i9-9980HK, 16 núcleos lógicos, 64 GB), sem GPU dedicada.
- Dependência de runtime: só `pydantic`. Dependências de desenvolvimento: `pytest` e `mypy` (com o plugin `pydantic.mypy`).
- Já aprovado pelo dono em 2026-10-29, ainda não instalado: `opencv-python`, para seguir o rosto na etapa 4.
- Qualquer outra dependência nova precisa da aprovação do dono antes.

### Binários em `tools/` (fora do git)

O `.gitignore` deixa de fora `tools/ffmpeg`, `tools/ffprobe` e `tools/sh.rnnn`. O passo a passo para baixar está no `README.md`, seção 1.3. Os hashes conferidos em 2026-10-29, num clone novo:

| Arquivo | Origem | sha256 |
|---|---|---|
| `tools/ffmpeg` 9.0.2-tessus x86_64 | https://evermeet.cx/ffmpeg/ffmpeg-9.0.2.zip | `a45b462cf91ed89148ae218c4577e30896485d7a6792c3673bcf5f823fa01b63` |
| `tools/ffprobe` | https://evermeet.cx/ffmpeg/ffprobe-9.0.2.zip | `a29f8c2e03553223a8b480b1a1f04c42f680c138fa952c20086718a075db38cb` |
| `tools/sh.rnnn` (voz, "somnolent-hogwash") | GregorR/rnnoise-models | `70bb6685eb0c2a1d18e2918dca3fbfbd39317010b1802eb1b6ea73a92f3fdec0` |

- **Por que um ffmpeg próprio:** o do brew (`/usr/local/bin/ffmpeg` 9.0.1) não tem os filtros `ass`, `subtitles` e `drawtext`. A legenda animada (etapa 4) precisa do libass.
- O link genérico `https://evermeet.cx/ffmpeg/getrelease/zip` foi desligado (HTTP 410). Use o link com a versão.
- **`sh.rnnn` fora do git:** a origem não declara licença (a API do GitHub responde `license: None`). Baixar pode; redistribuir não está claro.

### Instalação do comando

- `uv sync` cria o `.venv`. Para usar `talkedit` em qualquer pasta: `uv tool install --editable .` e depois `uv tool update-shell`.
- Tem que ser `--editable`: `ToolPaths.bundled()` acha `tools/` subindo a partir do caminho do código (`Path(__file__).parents[2] / "tools"`). Uma instalação que copia o código perde o `tools/`.
- Testado em 2026-10-29 num clone novo do GitHub: os 3 downloads bateram com os sha256 acima, `talkedit verificar` deu "Tudo certo." e o comando global funcionou de `/tmp`. O instalador do `uv` e o `uv tool update-shell` não foram testados (o `uv` já existia).

### Chave e arquivos do usuário

- Chave do OpenRouter: variável `OPENROUTER_API_KEY` ou o arquivo `~/.talkedit/chave_openrouter.txt` (`ApiKeyReader`). Nunca imprima o valor.
- Config: `~/.talkedit/config.toml`, criada por `talkedit config` a partir de `src/talkedit/config_modelo.toml`.
- Estilos do usuário: `~/.talkedit/estilos/<nome>.toml`. Os estilos prontos estão em `src/talkedit/estilos/`.
- Vídeos baixados do Drive: `~/Movies/talkedit/<id do arquivo>/` (`UserHome.videos`).
- `talkedit verificar` confere ffmpeg, filtros (`arnndn`, `loudnorm`, `ass`, `silencedetect`), modelo RNNoise, chave e se cada modelo existe no OpenRouter.

## 4. Como usar

O guia para o dono está no `README.md`. Resumo dos comandos:

```
talkedit verificar
talkedit editar video.mp4 [--teste] [--set ritmo.ritmo=acelerado]
talkedit editar "https://drive.google.com/file/d/<ID>/view?usp=sharing" [--pasta ~/Desktop]
talkedit previa    <pasta ou vídeo>
talkedit aprovar   <pasta ou vídeo>
talkedit continuar <pasta ou vídeo>
talkedit refazer   <pasta> <audio|transcricao|proxy|plano|revisao> [--set ...]
talkedit config
talkedit --detalhes <comando> ...      (o --detalhes vem antes do comando)
```

Sem a instalação global, use `uv run talkedit ...` dentro da pasta do repositório.

- O projeto de cada vídeo fica em `<pasta do vídeo>/<nome>_talkedit/`. O vídeo original só é lido.
- `editar` roda até a revisora e para. `aprovar` faz o render final.
- `--set` fica salvo em `estado.json` (`overrides`), para `continuar` e `refazer` usarem o mesmo valor. `refazer --set` soma ao que já existia.
- `editar` num vídeo que já tem projeto é recusado e manda usar `continuar`.

### Pasta do projeto

```
<nome>_talkedit/
  estado.json            etapas feitas, modo (real/teste), overrides, aprovado
  trabalho/
    audio_limpo.wav      48 kHz mono, já no volume final (-14 LUFS)
    transcricao.json     palavras com início e fim (Transcript)
    proxy.mp4            360p, 1 quadro por segundo, sem som (vai para a IA editora)
    plano.json           cortes de conteúdo, ênfases, pausas protegidas, observações (EditPlan)
    custos.json          US$ por função, como o OpenRouter informou
    pedacos_audio/       mp3 de ~2 min enviados para a transcrição
    segmentos/           um mp4 por trecho mantido (final_* e previa_*), reaproveitados
    logs/                saída de cada comando externo
    previa.mp4
  entrega/
    youtube.mp4
    relatorio.md
```

## 5. Arquitetura

Fluxo (`src/talkedit/pipeline.py`; a ordem está em `workspace.STAGE_ORDER`):

```
[link do Drive -> download] -> audio -> transcricao -> proxy -> plano (IA editora)
    -> revisao (IA revisora) -> [aprovação do dono] -> render
```

Cada etapa grava o resultado e marca `estado.json`. Se algo falha ou o terminal fecha, `continuar` retoma da etapa pendente. `refazer X` apaga a marca de X e de todas as etapas seguintes, e também tira a aprovação.

| Módulo | Papel |
|---|---|
| `cli.py` | comandos em português; o ponto de entrada é `CommandLine.entry`; `CommandRegistry` monta os comandos |
| `app.py` | raiz de composição: `ProjectAssembler` monta tudo; `RunMode.TEST` troca as IAs por fakes; `UserHome` |
| `drive.py` | `VideoSource` (caminho local ou link), `DriveLinkParser`, `DriveDownloader`, `UrllibFetcher`, `DownloadFormReader` |
| `pipeline.py` | etapas (`*Step.produce`) e `Pipeline.run_until` |
| `rendering.py` | `RenderStep`, `EditRenderer` (plano -> linha do tempo -> render), `ProjectReport` |
| `settings.py`, `settings_loader.py` | config em pydantic com chaves em português; camadas, da mais fraca para a mais forte: estilo, config do usuário, `--set` |
| `workspace.py` | caminhos da pasta do projeto, `ProjectState`, `Stage`, `RunMode` |
| `media.py` | `CommandRunner` (os.system + log), `MediaProbe` (ffprobe), `ToolPaths` |
| `audio.py` | cadeias de limpeza por intensidade e loudnorm em 2 passadas |
| `transcription.py` | detecção de silêncio, pedaços de ~2 min, Scribe pelo OpenRouter, `FakeTranscriber` |
| `openrouter.py` | cliente HTTP (urllib, 3 tentativas), chat com JSON estrito, `CostLedger` |
| `editor.py` | prompt, esquema e leitura da resposta da IA editora; `FakeEditor` |
| `reviewer.py` | texto editado com marcadores `[corte cN]`, IA revisora; `FakeReviewer` |
| `resolver.py` | `LaughterGuard` (corte com risada volta) e `PlanResolver` (pausas sobre as palavras que ficam) |
| `pacing.py` | `PauseCutter` e os perfis natural, dinâmico e acelerado |
| `timeline.py` | trechos mantidos em quadros inteiros (`FrameGrid`, `TimelineBuilder`) |
| `render.py` | segmentos em paralelo, emenda do áudio em Python, concat do ffmpeg |
| `errors.py` | `TalkeditError(message, hint)` e subclasses; `DriveNotPublicError.saying(...)` já traz a instrução de compartilhar |
| `proxy.py`, `phrases.py`, `plan.py`, `transcript.py`, `report.py`, `stores.py`, `schema.py`, `progress.py`, `doctor.py` | peças de apoio |

### Decisões que não são óbvias

- **Pausas não ficam salvas no plano.** `PlanResolver.all_cuts` recalcula as pausas sobre as palavras que sobraram depois dos cortes de conteúdo. Assim um take removido não deixa duas pausas curtas coladas numa longa, e devolver ou tirar um corte (etapa 2) muda as pausas sozinho.
- **A IA aponta índice de palavra, não tempo.** O tempo vem da transcrição. O corte visual vem em segundos e cresce até a borda das palavras que toca. Se o índice for inválido, o trecho fica no vídeo e entra uma observação.
- **Risada nunca sai.** `LaughterGuard` roda depois da editora e da revisora; qualquer corte que encoste num evento de risada volta com status `devolvido`.
- **Sugestão da revisora não é aplicada.** Ela pode devolver cortes (vale na hora), mas o que ela sugere cortar a mais fica como `sugerido`.
- **Sincronia por quadros.** Cada trecho mantido é arredondado para quadros inteiros (`FrameGrid`), e o áudio é fatiado na amostra que corresponde àquele quadro. Trecho com menos de 3 quadros é descartado.
- **Emendas de áudio:** fade de saída e de entrada de 6 ms em cada emenda (`render.FADE_SECONDS`), sem sobreposição, para não mudar a duração.
- **Render por segmentos:** um mp4 por trecho (libx264, 2 threads cada, `cpu_count // 2` em paralelo), com o nome feito do quadro inicial, da quantidade e do perfil. Um render novo reaproveita os trechos que não mudaram. Tudo junta com o concat do ffmpeg (`-c:v copy`), e o áudio é codificado uma vez só (AAC), o que evita o problema do priming do AAC por segmento.
- **Proxy da IA:** `-skip_frame nokey` (decodifica só keyframes) + `fps=1` + 360p + crf 34, sem som.
- **Transcrição em pedaços** de cerca de 120 s, com o corte movido para o meio do silêncio mais próximo (até 20 s de distância), até 4 em paralelo. Motivo: a doc do OpenRouter diz que o provedor desiste depois de 60 s por pedido.
- **Ordem no `editar`:** primeiro abre o vídeo (ffprobe), só depois grava `estado.json`. Se o arquivo não for vídeo, não sobra projeto quebrado.
- **Download do Drive:** pede `https://drive.usercontent.google.com/download?id=<ID>&export=download&confirm=t`. Se vier a página "Virus scan warning", lê o formulário `download-form` e segue o botão. Faz streaming de 1 MB por vez para `download.parcial`, que só ganha o nome do `Content-Disposition` no fim. Recusa apaga o `.parcial`. O mesmo link de novo reaproveita o arquivo. Só stdlib (`urllib`, `html.parser`, `email.message`), sem `gdown`.

### Modelos padrão (escolhidos em 2026-10-29 pela lista `/api/v1/models`)

| Função | Modelo | Preço na lista |
|---|---|---|
| transcrição | `elevenlabs/scribe-v2` | 0.0000611 por segundo de áudio (conferido: 33.8 s custaram US$ 0.00198) |
| editora | `google/gemini-4-argon` (vídeo + JSON estrito) | US$ 2 / 10 por milhão de tokens (entrada / saída) |
| revisora | `google/gemini-3.5-flash-lite` (só texto) | US$ 0.30 / 2.50 por milhão de tokens |

Formatos usados, tirados da doc atual do OpenRouter (não inventados):
- **Transcrição:** `POST /api/v1/audio/transcriptions` com `input_audio {data, format}`, `language`, `response_format: verbose_json`, `timestamp_granularities: ["word"]` e `keyterms` (palavras difíceis). As palavras voltam com `type: word | audio_event`.
- **Chat:** `POST /api/v1/chat/completions` com `video_url` em data URL base64 e `response_format` `json_schema` `strict: true`. O custo vem em `usage.cost`.
- **Lista de modelos de transcrição:** `/api/v1/models?output_modalities=all`. Sem esse parâmetro, o Scribe não aparece.

## 6. Descobertas (com prova)

1. **O ffmpeg 9.0.2 trava com `arnndn` seguido de `speechnorm`**: a CPU fica em 100 % parada no fim do arquivo, e o processo não morre com SIGTERM. Prova (2026-10-29, vídeo de 33 s, `timeout -s KILL 8`):
   ```
   rc=0 1s :: arnndn=m=M,afftdn=nr=8:nf=-50
   rc=137 8s :: arnndn=m=M,speechnorm=e=4:r=0.0001:l=1
   ```
   Pôr `asetnsamples` entre os dois não resolveu. Trocamos por `dynaudnorm`, que roda em 1 s. Não volte para `speechnorm` depois de `arnndn`.
2. **Todo comando externo roda com `< /dev/null`** (`CommandRunner`), para o ffmpeg nunca esperar teclado.
3. **A IA real acertou o vídeo sintético** (`say -v Luciana` com um take abandonado e "corta isso"): 3 cortes, os 3 certos. Custo total de US$ 0.0121 (transcrição 0.0020, editora 0.0098, revisora 0.0003).
4. **Nenhuma palavra cortada nesse teste:** transcrevi o `youtube.mp4` final de novo e ele saiu completo, "Hoje eu vou falar sobre como economizar dinheiro. ... Era isso, valeu".
5. **Sincronia:** vídeo com 14.247567 s e áudio com 14.247542 s. Volume final de -13.6 LUFS (meta -14).
6. **Tempo num vídeo sintético de 15 min em 1080p** (modo de teste, sem IA, 2026-10-29):
   - limpeza de áudio: 46 s em cada uma das 2 passadas (19.6x tempo real), 92 s no total
   - proxy: 3 s
   - plano completo sem IA: 96 s
   - render final (11:10 de saída, crf 18, preset medium, 235 trechos): 1413 s (23.5 min). Meta: 30 min.
   - Atenção: `testsrc2` é difícil de codificar e tem keyframes regulares. Com vídeo de câmera real pode ser mais rápido ou mais lento; não foi medido.
7. **Download real do Drive** (2026-10-29), com um arquivo público grande: 498 MB, id `1l_5RK28JRL19wpT22B-DY9We3TVXnnQQ`, um `.npz` de exemplo do gdown, não é vídeo.
   - Com `confirm=t`, o Drive entregou o arquivo direto (`206 application/octet-stream`, `content-disposition: attachment; filename="fcn8s_from_caffe.npz"`). Sem `confirm=t`, veio a página `Google Drive - Virus scan warning`.
   - Chegaram 498881336 bytes, igual ao total do `content-range: bytes 0-2047/498881336`. O comando inteiro levou 68 s (cerca de 4.5 MB/s nesta rede).
   - Link inexistente: o Drive responde `404 text/html`, e o programa mostra "respondeu erro 404" com a instrução de compartilhar.
   - Foram achados e corrigidos 2 bugs, cada um com teste: um `editar` que falhava ao abrir o vídeo deixava `estado.json` para trás e travava a nova tentativa; e a busca de "já baixado" podia pegar a pasta `<nome>_talkedit/` no lugar do vídeo.
   - Ainda não foi testado com um vídeo real no Drive nem com um arquivo privado. O esperado no privado é a página de login cair na mensagem "não está público".
8. **Os exemplos do README foram rodados de verdade** num clone novo (2026-10-29): `talkedit config`, `editar --teste` e `refazer <pasta> plano --set estilo=natural`. No vídeo de teste, o estilo natural ficou com 00:22 e o dinâmico com 00:20.

## 7. Regras de código que os hooks cobram

Estas regras valem para todo `.py`, inclusive os testes. O hook `~/.claude/hooks/immutable-rules-check.py` bloqueia na hora; outro hook revisa no fim da sessão.

- Toda função fica dentro de uma classe. `__init__` só atribui (nada de chamar função, nem `super().__init__`; use `@classmethod` de fábrica).
- No máximo 3 parâmetros (use um dataclass frozen). Métodos com até 20 linhas, classes com até 200. No máximo 2 níveis de aninhamento. Sem `elif` (use um dicionário ou polimorfismo).
- Sem número solto além de 0 e 1. Sem nome vago (`result`, `run`, `data`, `s`, `w`). Sem `print` (use logger). Sem `subprocess` (use `os.system` com `shlex`).
- Sem estado global mutável. Um mapa fixo fica como `MappingProxyType` em atributo de classe.
- **Regra vinda da revisão de fim de sessão (2026-10-29):** constante nova vai para a classe dona, como `ClassVar`, e não solta no módulo. Status HTTP usam `http.HTTPStatus`; mensagem fixa de erro fica na subclasse do erro; conversão de unidade vira um objeto de valor (ex.: `ByteCount`). Hoje só `drive.py` segue isso. Os outros 20 módulos ainda têm constantes no módulo; elas passam porque o hook só olha o que é novo em relação ao HEAD. Ao mexer num desses módulos, mova as constantes que você tocar.
- Arquivo de código se escreve com Write ou Edit, nunca com redirecionamento do shell (outro hook bloqueia). O `black` roda depois de cada edição e pode reformatar o arquivo; releia antes de editar de novo.

## 8. O que foi feito

### Etapa 1 (commit `f189747`)

- [x] 5.1 Limpeza de áudio grátis com 4 intensidades (`desligado`, `leve`, `normal`, `forte`) e loudnorm em 2 passadas
- [x] 5.2 Transcrição com tempo por palavra, eventos de som e palavras difíceis (`keyterms`)
- [x] 5.3 Ritmo natural, dinâmico ou acelerado, sem cortar palavra, com pausa protegida pela editora
- [x] 5.4 IA editora com vídeo leve, motivo em português, regras do usuário e postura por estilo
- [x] 5.5 IA revisora só de texto: devolve cortes, sugere mais e deixa observações
- [x] 5.14 (parte) CLI em português, retomar, refazer uma parte, `verificar`, erros com "O que fazer"
- [x] 5.15 (parte) config comentada em português, `--set`, estilos `dinamico` e `natural`, modelo por função
- [x] 5.16 Modo de teste com fakes
- [x] 5.17 (parte) custo real por função e relatório em markdown
- [x] Render do YouTube na resolução original, com emendas suaves, e prévia em 360p

### Depois da etapa 1

- [x] Repositório público no GitHub, sem binários de terceiros
- [x] Entrada por link público do Google Drive (`editar <link>`, `--pasta`), pedida pelo dono
- [x] `README.md` reescrito como guia para quem não programa. Isto cobre boa parte da etapa 7.

## 9. O que falta

### Próxima ação

- [ ] **Rodar com um vídeo real do dono** (de 2 a 5 min, de preferência pelo Drive) e medir custo, tempo, se os cortes estão certos e se as emendas soam bem de ouvido. Nada da etapa 2 deveria começar antes disso.

### Decisões pendentes do dono

- [ ] Licença do repositório (hoje nenhuma, então ninguém pode usar o código).
- [ ] Criar um `main` e deixar como branch padrão (hoje o padrão é `etapa-1-video-longo`).

### Pendências da etapa 1

- [ ] Estimativa de custo antes de começar (5.17), usando a duração do vídeo e os preços de `/api/v1/models`.
- [ ] Tempo restante do fluxo inteiro (5.14). Hoje só existe dentro do render.
- [ ] Opção paga Auphonic (5.1).
- [ ] `continuar` num projeto já aprovado e renderizado não mostra nada; deveria dizer onde está a entrega.
- [ ] Download do Drive interrompido recomeça do zero (não usa `Range`). Só importa com vídeo de vários GB.
- [ ] Testar o Drive com um vídeo real e com um link privado.

### Próximas etapas (ordem de `SPEC.md`, seção 7)

2. **Página de revisão, aba Edição** (5.6): servidor local feito só com Python (`http.server`) + HTML/JS puro, offline, estado em disco. Use `PlanResolver` e `EditRenderer.render(..., RenderProfile.preview())` para a prévia. Os cortes já têm `status` (`aplicado`, `devolvido`, `sugerido`) e `source` (`voce` para corte manual). "Refazer o plano com pedido em texto" precisa de um campo novo no prompt da editora.
3. **Estilo dinâmico** (5.7): disfarce de jump cut (alternar o enquadramento por segmento) e zoom de ênfase (`EditPlan.emphasis` já vem da editora, mas ainda não é usado). O render por segmento facilita, porque o `crop`/`scale` entra no `-vf` de cada trecho. Também a legenda `.srt` do YouTube, que precisa de uma função que leve o tempo do original para o tempo editado (`Timeline`).
4. **Cortes verticais** (5.8, 5.9, 5.10): instalar `opencv-python` (já aprovado), detector de rosto YuNet em resolução baixa, legenda ASS karaokê queimada com o filtro `ass` do `tools/ffmpeg`, área segura comum de Shorts, Reels e TikTok, aba Cortes, modelo de cortes barato com vídeo.
5. **Textos e thumbnail** (5.11, 5.12) e aba Textos.
6. **Página de publicação** (5.13).
7. **Guia de uso:** o `README.md` já cobre a instalação e o uso. Falta atualizar ele a cada etapa e explicar a página de revisão quando ela existir.

## 10. O que vigiar

| Risco | Por quê | Como checar |
|---|---|---|
| Custo da editora em vídeo longo | O Gemini cobra cada quadro do vídeo, e 15 min ainda não foram medidos com IA real. A meta é menos de US$ 1 por vídeo de 15 min no total. | `trabalho/custos.json` depois de um vídeo real de 15 min. Se só a editora passar de ~US$ 0.60, troque o vídeo por folhas de quadros (imagens) ou baixe a taxa de quadros. |
| Tamanho do proxy no pedido | O vídeo vai em base64 dentro do JSON, e o limite do provedor não foi testado. O proxy sintético de 15 min tinha 704 KB. | Tamanho de `trabalho/proxy.mp4` num vídeo real. Se a editora der erro de tamanho, divida em partes. |
| Keyframes raros em vídeo de celular | `-skip_frame nokey` usa só keyframes; com GOP longo, a IA vê menos de 1 quadro por segundo. | `ffprobe -skip_frame nokey -select_streams v -show_entries frame=pts_time` no vídeo real. |
| Fim de palavra comido | A folga em volta das palavras é fixa (`PaceProfiles`) e depende do tempo que o Scribe dá. | Ouça as emendas e transcreva o `youtube.mp4` de novo. Se acontecer, mova o corte para o ponto mais silencioso da pausa (marcado com `ponytail:` em `pacing.py`). |
| Risada não reconhecida | `Word.is_laughter` procura "laugh", "ris" ou "gargalh" no texto do evento. O formato que o Scribe usa para risada em português ainda não foi visto. | Procure `audio_event` no `transcricao.json` de um vídeo com risada. |
| Modelos que mudam de nome | Modelos entram e saem do OpenRouter. | `talkedit verificar` antes de cada uso longo. |
| Travamento do ffmpeg | Ver a descoberta 1. Se uma etapa de áudio passar de alguns minutos num vídeo curto, é isso. | `ps aux \| grep tools/ffmpeg` e o tempo no log em `trabalho/logs/`. |
| Mudança no download do Drive | O fluxo depende de `confirm=t` e do formulário `download-form`, que o Google pode mudar sem aviso. Também há um limite diário de downloads por arquivo. | Se `editar <link>` disser "mostrou uma pagina em vez do video" para um arquivo público, salve a página e confira o HTML. |
| Tempo de render | 23.5 min para 15 min sintéticos em 1080p, perto da meta de 30. Vídeo 4K vai demorar mais. | Meça com vídeo real. `render.velocidade_x264 = "fast"` é a válvula. |
| README desatualizado | O README é o único guia do dono e mostra saídas reais. | A cada etapa, rode os exemplos do README num clone novo antes de publicar. |

## 11. Testes

- `uv run pytest` roda os 50 testes em cerca de 6 s.
- `tests/test_end_to_end.py` gera um vídeo de 12 s (tom de 220 Hz com silêncio), roda `editar --teste` e `aprovar`, e confere a sincronia, o encurtamento e o relatório. Ele também pega a volta do travamento do ffmpeg, porque usa a limpeza `normal`, e confere que um arquivo que não é vídeo não deixa projeto quebrado.
- Testes de unidade: pausas, linha do tempo, emenda de áudio, resposta da editora e da revisora, trava de risada, config, estado, pedaços da transcrição, cliente OpenRouter (transporte falso), progresso (relógio falso) e download do Drive (`tests/test_drive.py`, com `FakeFetcher` no lugar da internet).
- Os testes usam classes com constantes nomeadas por causa da regra de número solto. Os construtores de teste ficam em `tests/builders.py`.
- Os vídeos de teste da sessão de 2026-10-29 ficaram no scratchpad temporário do Claude e já podem ter sumido. Para recriar o vídeo falado de teste:
  ```
  say -v Luciana -o fala.aiff "oi gente, deixa eu ver se ta gravando. [[slnc 2000]] Hoje eu vou falar ..."
  tools/ffmpeg -f lavfi -i "testsrc2=size=1280x720:rate=30000/1001" -i fala.aiff \
    -f lavfi -i "anoisesrc=color=brown:amplitude=0.03:sample_rate=48000" \
    -filter_complex "[1:a]aresample=48000[v];[v][2:a]amix=inputs=2:duration=first:normalize=0[a]" \
    -map 0:v -map "[a]" -shortest -c:v libx264 -c:a aac bruto.mp4
  ```

## 12. Regras de trabalho deste projeto

- Fale com o dono em português simples. Código, comentários, commits e identificadores em inglês. Textos que o usuário vê (CLI, config, relatório, README) em português.
- Não instale dependência nova sem perguntar.
- **Push só quando o dono pedir, a cada vez.** O repositório é público; confira se há segredo antes de qualquer push. Nunca reescreva histórico já publicado.
- Nada de binário de terceiros sem licença clara no git.
- A v1 não publica vídeo em nenhuma plataforma.
- Ao fim de cada etapa: testes, ruff e mypy passando, um commit no branch, este arquivo e o README atualizados, e diga ao dono o que ele pode testar e como.
