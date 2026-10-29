# KNOWLEDGE: talkedit

Estado vivo do projeto, para qualquer agente ou pessoa que continue o trabalho.
Última atualização: 2026-10-29. Leia este arquivo inteiro antes de mexer no código.

| Arquivo | Para quem | Conteúdo |
|---|---|---|
| `README.md` | o dono (não programa) | instalação, uso pela página e pelo Terminal, comandos, config, custo, erros comuns |
| `SPEC.md` | todos | o que o produto deve fazer (resumo fiel do documento do dono) |
| `KNOWLEDGE.md` | agentes e devs | este arquivo: implementação, decisões, descobertas, pendências, riscos |

Desenho das telas (Claude Design, privado do dono): https://claude.ai/artifact/Sh11CoPz6XyUVXSQMSzKtu

---

## 1. Resumo

1. `talkedit` edita o vídeo bruto de uma pessoa falando para a câmera, em português, num Mac Intel. Todos os modelos de IA passam pelo OpenRouter.
2. **Etapa 1 de 7 entregue:** limpeza de áudio, transcrição, IA editora, IA revisora, corte de pausas, prévia e vídeo do YouTube.
3. **Etapa 2 de 7 entregue:** `talkedit abrir` sobe uma página local com 4 telas: Novo vídeo (arrastar e soltar ou link do Drive), Em andamento, Revisão dos cortes, Padrões.
4. Extra pedido pelo dono, fora da spec: o vídeo pode vir de um **link público do Google Drive** (página e Terminal).
5. Modo de teste (`--teste` ou a caixa na página) roda tudo sem IA e sem custo.
6. **Ninguém rodou ainda com um vídeo real do dono.** Só com vídeos sintéticos. Esta é a próxima ação.

## 2. Estado do repositório

| Item | Valor |
|---|---|
| Pasta local | `/Users/iklo/editor` |
| Remoto | `origin` = https://github.com/iklobato/talkedit, público, conta pessoal `iklobato` (`git@github.com:`) |
| Branch de trabalho | `etapa-2-frontend`; antes deste arquivo, em `3a7b337`, igual no local e no GitHub |
| Outro branch | `etapa-1-video-longo`, em `32952e8`. É o **branch padrão** no GitHub. `etapa-2-frontend` saiu dele e tem tudo dele. |
| `main` | não existe. Decisão pendente do dono. |
| Licença | nenhuma (GitHub responde `license=null`). Decisão pendente do dono. |
| Testes | 79 passando (`uv run pytest`, ~14 s), ruff e mypy limpos |
| Python | 3.11 (`.venv` criado por `uv`) |

Histórico, do mais novo para o mais antigo:

| Commit | Branch | O que fez |
|---|---|---|
| `3a7b337` | etapa-2 | KNOWLEDGE marca o branch da etapa 2 como publicado |
| `3bcbb57` | etapa-2 | status das etapas com guard clauses (pedido da revisão de regras) |
| `d1beef3` | etapa-2 | página local inteira (etapa 2) |
| `32952e8` | etapa-1 | KNOWLEDGE depois do Drive, da publicação e do README |
| `2c98c90` | etapa-1 | README virou guia passo a passo para o dono |
| `3716df9` | etapa-1 | constantes do download do Drive nas classes donas |
| `c668b9b` | etapa-1 | entrada por link público do Google Drive |
| `1c5f821` | etapa-1 | KNOWLEDGE aponta para o commit publicado |
| `bc6895a` | etapa-1 | modelo RNNoise fora do git (origem sem licença) |
| `d404cef` | etapa-1 | primeiro KNOWLEDGE.md |
| `f189747` | etapa-1 | etapa 1 inteira |

O histórico foi reescrito uma vez, antes da primeira publicação, para tirar `tools/sh.rnnn` de todos os commits (os hashes antigos `b2ef206` e `9d8320f` não existem mais). Depois de publicado, nunca reescreva.

## 3. Ambiente e instalação

- Máquina alvo: Mac Intel (`x86_64`, i9-9980HK, 16 núcleos lógicos, 64 GB), sem GPU dedicada.
- Dependência de runtime: só `pydantic`. Dependências de desenvolvimento: `pytest` e `mypy` (com o plugin `pydantic.mypy`). A página não usa nenhuma biblioteca: `http.server` da stdlib e JS puro.
- Já aprovado pelo dono em 2026-10-29, ainda não instalado: `opencv-python`, para seguir o rosto na etapa 4.
- Qualquer outra dependência nova precisa da aprovação do dono antes.

### Binários em `tools/` (fora do git)

O `.gitignore` deixa de fora `tools/ffmpeg`, `tools/ffprobe` e `tools/sh.rnnn`. O passo a passo para baixar está no `README.md`, seção 1.3. Hashes conferidos em 2026-10-29 num clone novo:

| Arquivo | Origem | sha256 |
|---|---|---|
| `tools/ffmpeg` 9.0.2-tessus x86_64 | https://evermeet.cx/ffmpeg/ffmpeg-9.0.2.zip | `a45b462cf91ed89148ae218c4577e30896485d7a6792c3673bcf5f823fa01b63` |
| `tools/ffprobe` | https://evermeet.cx/ffmpeg/ffprobe-9.0.2.zip | `a29f8c2e03553223a8b480b1a1f04c42f680c138fa952c20086718a075db38cb` |
| `tools/sh.rnnn` (voz, "somnolent-hogwash") | GregorR/rnnoise-models | `70bb6685eb0c2a1d18e2918dca3fbfbd39317010b1802eb1b6ea73a92f3fdec0` |

- **Por que um ffmpeg próprio:** o do brew (`/usr/local/bin/ffmpeg` 9.0.1) não tem `ass`, `subtitles` nem `drawtext`. A legenda animada (etapa 4) precisa do libass.
- O link genérico `https://evermeet.cx/ffmpeg/getrelease/zip` responde HTTP 410. Use o link com a versão.
- **`sh.rnnn` fora do git:** a origem não declara licença (`license: None` na API do GitHub). Baixar pode; redistribuir não está claro.

### Instalação do comando

- `uv sync` cria o `.venv`. Para usar `talkedit` em qualquer pasta: `uv tool install --editable .` e `uv tool update-shell`.
- Tem que ser `--editable`: `ToolPaths.bundled()` acha `tools/` subindo a partir do código (`Path(__file__).parents[2] / "tools"`), e a página serve `src/talkedit/web/static/` do mesmo jeito.
- Testado em 2026-10-29 num clone novo: os 3 downloads bateram com os hashes, `talkedit verificar` deu "Tudo certo." e o comando global funcionou de `/tmp`. O instalador do `uv` e o `uv tool update-shell` não foram testados (o `uv` já existia).

### Arquivos do usuário (fora do repositório)

| Caminho | O que é | Quem grava |
|---|---|---|
| `OPENROUTER_API_KEY` ou `~/.talkedit/chave_openrouter.txt` | chave do OpenRouter (`ApiKeyReader`). Nunca imprima. | o dono |
| `~/.talkedit/config.toml` | padrões, com comentário em português por opção | `talkedit config` e a tela Padrões (`SettingsStore`) |
| `~/.talkedit/estilos/<nome>.toml` | estilos do usuário (os prontos ficam em `src/talkedit/estilos/`) | o dono |
| `~/.talkedit/projetos.json` | pastas de projeto, mais nova primeiro, até 50 (`ProjectRegistry`) | Terminal e página, a cada projeto aberto |
| `~/Movies/talkedit/` | vídeos arrastados na página e baixados do Drive (`<id do Drive>/<nome>`) | página e `editar <link>` |

## 4. Como usar

O guia para o dono está no `README.md`. Resumo:

```
talkedit abrir [--porta N] [--sem-navegador]       página local; fecha com Ctrl+C
talkedit verificar
talkedit editar video.mp4 [--teste] [--set ritmo.ritmo=acelerado]
talkedit editar "https://drive.google.com/file/d/<ID>/view?usp=sharing" [--pasta ~/Desktop]
talkedit previa    <pasta ou vídeo>
talkedit aprovar   <pasta ou vídeo>
talkedit continuar <pasta ou vídeo>
talkedit refazer   <pasta> <audio|transcricao|proxy|player|plano|revisao> [--set ...]
talkedit config
talkedit --detalhes <comando> ...                  o --detalhes vem antes do comando
```

Sem a instalação global, use `uv run talkedit ...` dentro do repositório.

- O projeto de cada vídeo fica em `<pasta do vídeo>/<nome>_talkedit/`. O vídeo original só é lido.
- `editar` roda até a revisora e para. `aprovar` faz o render final.
- `--set` fica salvo em `estado.json` (`overrides`), para `continuar` e `refazer` usarem o mesmo valor. `refazer --set` soma ao que já existia.
- `editar` pelo Terminal num vídeo que já tem projeto é recusado e manda usar `continuar`. Pela página, o mesmo vídeo retoma o projeto existente.
- Terminal e página mexem nos mesmos projetos. Rodar os dois ao mesmo tempo no mesmo projeto não é protegido (só a página sabe do seu próprio trabalho em andamento).

### Pasta do projeto

```
<nome>_talkedit/
  estado.json            etapas feitas, modo (real/teste), overrides, aprovado, editor_request
  trabalho/
    audio_limpo.wav      48 kHz mono, já no volume final (-14 LUFS)
    transcricao.json     palavras com início e fim (Transcript)
    proxy.mp4            360p, 1 quadro por segundo, sem som (vai para a IA editora)
    player.mp4           540p H.264 com o áudio limpo (player da página de revisão)
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
[link do Drive -> download] -> audio -> transcricao -> proxy -> player -> plano (IA editora)
    -> revisao (IA revisora) -> [aprovação do dono] -> render
```

Cada etapa grava o resultado e marca `estado.json`. Se algo falha, `continuar` retoma da etapa pendente. `refazer X` apaga a marca de X e das seguintes, e tira a aprovação.

### Módulos do núcleo (`src/talkedit/`)

| Módulo | Papel |
|---|---|
| `cli.py` | comandos em português; ponto de entrada `CommandLine.entry`; `CommandRegistry` monta os comandos; `OpenCommand` é o `abrir` |
| `app.py` | raiz de composição: `ProjectAssembler` (recebe o `ProgressSink`); `RunMode.TEST` troca as IAs por fakes; `UserHome` (caminhos e `settings_store()`) |
| `projects.py` | `ProjectOpener` (usado pelo Terminal e pela página), `ProjectRegistry`, `ProjectKey` (sha256 da pasta, 12 caracteres) |
| `pipeline.py` | etapas (`*Step.produce`, com `label`) e `Pipeline.run_until` |
| `rendering.py` | `RenderStep`, `EditRenderer` (plano -> linha do tempo -> render), `ProjectReport` |
| `settings.py`, `settings_loader.py` | config em pydantic com chaves em português; camadas: estilo < config do usuário < `--set`; `Settings.with_editor_request` |
| `settings_writer.py` | `ConfigWriter` e `SettingsStore`: validam e gravam o `config.toml` |
| `workspace.py` | caminhos da pasta do projeto, `ProjectState`, `Stage`, `RunMode` |
| `plan_changes.py` | `PlanChanges`: devolver, tirar e marcar um trecho novo (`u1`, `u2`...) |
| `drive.py` | `VideoSource` (caminho local ou link), `DriveLinkParser`, `DriveDownloader`, `UrllibFetcher`, `DownloadFormReader` |
| `media.py` | `CommandRunner` (os.system + log, `< /dev/null`), `MediaProbe` (ffprobe), `ToolPaths` |
| `audio.py` | cadeias de limpeza por intensidade e loudnorm em 2 passadas |
| `transcription.py` | silêncios, pedaços de ~2 min, Scribe pelo OpenRouter, `FakeTranscriber` |
| `openrouter.py` | cliente HTTP (urllib, 3 tentativas), chat com JSON estrito, `CostLedger` |
| `editor.py` | prompt (com o pedido do criador), esquema e leitura da resposta da IA editora; `FakeEditor` |
| `reviewer.py` | texto editado com marcadores `[corte cN]`, IA revisora; `FakeReviewer` |
| `resolver.py` | `LaughterGuard` e `PlanResolver` (pausas sobre as palavras que ficam) |
| `pacing.py`, `timeline.py`, `render.py` | pausas, trechos em quadros inteiros, segmentos em paralelo e emenda do áudio |
| `proxy.py` | `ProxyMaker` (cópia para a IA) e `PlayerMaker` (cópia para o player) |
| `progress.py` | `ProgressSink` (protocolo), `ProgressReporter` (Terminal) |
| `errors.py` | `TalkeditError(message, hint)` e subclasses; `DriveNotPublicError.saying(...)`; `NotFoundError`, `BusyError`, `AccessError` |
| `phrases.py`, `plan.py`, `transcript.py`, `report.py`, `stores.py`, `schema.py`, `doctor.py` | peças de apoio |

### Módulos da página (`src/talkedit/web/`)

| Módulo | Papel |
|---|---|
| `server.py` | `WebServerBuilder` (raiz de composição da página), `ProjectRoutes`, handler do `http.server` |
| `api.py` | `Router`, `WebApplication` (erro vira JSON `{error, hint}`), um endpoint por ação |
| `http.py` | `WebRequest`, `JsonResponse`, `StaticResponse` (CSP), `FileResponse` (Range), `StaticFiles`, `AccessGuard` |
| `actions.py` | `EditJobs` (trabalhos longos), `PlanEditing` (mudanças na hora), `VideoUploads`, `FinderOpener` |
| `jobs.py` | `JobTracker` (um trabalho por vez numa thread), `JobProgress`, `JobLogHandler` |
| `views.py` | JSON da lista, do detalhe com as etapas (`StageStatus`) e do plano |
| `static/` | `index.html`, `app.css`, `app.js` (JS puro, sem framework, funciona sem internet), `icon.svg` |

### API da página

Toda rota `/api/` exige o código secreto: header `X-Talkedit-Token`, ou `?t=` (usado pelo `<video>`). Erros voltam como `{"error", "hint"}` com 400, 403 (`AccessError`), 404 (`NotFoundError`) ou 409 (`BusyError`).

| Método e caminho | O que faz |
|---|---|
| `GET /` e `GET /static/<arquivo>` | a página (sem código; só arquivos de `web/static/`) |
| `GET /api/state` | trabalho atual (`phase`: `parado`, `rodando`, `pronto`, `erro`), lista de projetos, resumo dos padrões |
| `GET` / `PUT /api/settings` | ler / gravar padrões (chaves do `config.toml`); a resposta traz `settings`, `factory` e `path` |
| `PUT /api/videos?name=<arquivo>` | recebe o vídeo arrastado (corpo cru) e devolve o caminho salvo |
| `POST /api/projects` | `{source, test, style}`: começa um vídeo (caminho local ou link do Drive) |
| `GET /api/projects/<key>` | detalhe: status (`running`, `failed`, `review`, `ready`, `stopped`), etapas, pastas, o que existe |
| `GET /api/projects/<key>/plan` | resumo, cortes (`aplicado`, `devolvido`, `sugerido`), pausas, observações, custo |
| `POST /api/projects/<key>/continue`, `/preview`, `/approve` | começa o trabalho em segundo plano |
| `POST /api/projects/<key>/redo` | `{request}`: refaz plano e revisão com o pedido do criador |
| `POST /api/projects/<key>/cuts` | `{start, end}`: marca um trecho novo (mínimo 0.5 s) |
| `POST /api/projects/<key>/cuts/<id>/give-back` ou `/apply` | devolve ou tira um trecho |
| `POST /api/projects/<key>/finder` | abre a pasta `entrega/` (ou a do projeto) no Finder |
| `GET /api/projects/<key>/media/player`, `/preview`, `/final` | vídeo com suporte a Range |

### Decisões que não são óbvias

**Edição**
- **Pausas não ficam salvas no plano.** `PlanResolver.all_cuts` recalcula sobre as palavras que sobraram. Um take removido não deixa duas pausas coladas, e devolver ou tirar um corte na página muda as pausas sozinho.
- **A IA aponta índice de palavra, não tempo.** Corte visual vem em segundos e cresce até a borda das palavras. Índice inválido: o trecho fica e entra uma observação.
- **Risada nunca sai pela IA.** `LaughterGuard` roda depois da editora e da revisora. Um corte que o próprio dono marca na página não passa pela trava: é escolha dele.
- **Sugestão da revisora não é aplicada**: fica como `sugerido` até o dono tirar.
- **Sincronia por quadros**: trechos em quadros inteiros, áudio fatiado na amostra do quadro, trecho com menos de 3 quadros descartado. Emendas com fade de 6 ms, sem sobreposição.
- **Render por segmentos**: um mp4 por trecho (2 threads cada, `cpu_count // 2` em paralelo), reaproveitado se não mudou; junta com concat (`-c:v copy`) e o áudio é codificado uma vez só.
- **Proxy da IA**: `-skip_frame nokey` + `fps=1` + 360p + crf 34, sem som.
- **Transcrição em pedaços** de ~120 s cortados no meio de um silêncio, até 4 em paralelo (o provedor desiste depois de 60 s por pedido).
- **Ordem no `editar`**: abre o vídeo (ffprobe) antes de gravar `estado.json`, para um arquivo que não é vídeo não deixar projeto quebrado.

**Página**
- **Segurança**: escuta só em `127.0.0.1`, porta livre; código secreto novo a cada `talkedit abrir` (`secrets.token_urlsafe(24)`, comparado com `hmac.compare_digest`); `Host` tem que ser o próprio servidor (contra DNS rebinding). A página tira o código da barra de endereço (`history.replaceState`) e guarda em `sessionStorage`. CSP `default-src 'self'`, com estilos em linha liberados (as barras da linha do tempo usam `style`). Todo texto vindo do servidor entra por `textContent`.
- **Um trabalho por vez** (`JobTracker`), como diz a spec. Segundo pedido: 409. Erro do talkedit vira `erro` com mensagem e dica; erro inesperado também vira `erro` (no `finally`) e o traceback vai para o Terminal.
- **O projeto só aparece para a página depois de existir em disco**: `EditJobs._edit_new` anuncia a chave depois de salvar `estado.json` e registrar em `projetos.json`. Antes disso a página mostra "Preparando o vídeo".
- **Arrastar e soltar copia o vídeo** (`PUT /api/videos`, 1 MB por vez, `.parcial` até o fim). O navegador nunca dá o caminho do arquivo. Nome limpo, só extensões de vídeo, nome repetido ganha `-2`.
- **Player usa `player.mp4`** (etapa `player`), não o original: o navegador pode não tocar HEVC 4K do celular, e o que se ouve já é o áudio limpo.
- **Mudança no plano pela página cancela a aprovação** (`reopen_from(Stage.RENDER)`), porque o vídeo final antigo não bate mais. É recusada (409) se um trabalho roda no mesmo projeto.
- **Refazer com pedido**: o texto vai para `ProjectState.editor_request` e entra no prompt da editora. Refazer apaga as mudanças feitas à mão (a página avisa).
- **Padrões**: `SettingsStore.save` valida com o mesmo loader do Terminal antes de gravar. O ritmo só é gravado se for diferente do ritmo do estilo, para que trocar de estilo depois continue trocando o ritmo. O arquivo é reescrito inteiro (decisão do dono), então comentários feitos à mão se perdem.
- **Mensagens de log viram o "detalhe" do trabalho** (`JobLogHandler` no logger `talkedit`), só enquanto um trabalho roda.

**Drive**
- Pede `https://drive.usercontent.google.com/download?id=<ID>&export=download&confirm=t`. Se vier a página "Virus scan warning", lê o formulário `download-form` e segue o botão. Streaming de 1 MB para `download.parcial`, nome final do `Content-Disposition`. Recusa apaga o `.parcial`. O mesmo link de novo reaproveita o arquivo. Só stdlib, sem `gdown`.

## 6. Modelos e formatos do OpenRouter

Modelos padrão, escolhidos em 2026-10-29 pela lista `/api/v1/models`:

| Função | Modelo | Preço na lista |
|---|---|---|
| transcrição | `elevenlabs/scribe-v2` | 0.0000611 por segundo de áudio (conferido: 33.8 s custaram US$ 0.00198) |
| editora | `google/gemini-4-argon` (vídeo + JSON estrito) | US$ 2 / 10 por milhão de tokens (entrada / saída) |
| revisora | `google/gemini-3.5-flash-lite` (só texto) | US$ 0.30 / 2.50 por milhão de tokens |

Formatos usados, tirados da doc atual do OpenRouter (não inventados):
- **Transcrição:** `POST /api/v1/audio/transcriptions` com `input_audio {data, format}`, `language`, `response_format: verbose_json`, `timestamp_granularities: ["word"]` e `keyterms`. As palavras voltam com `type: word | audio_event`.
- **Chat:** `POST /api/v1/chat/completions` com `video_url` em data URL base64 e `response_format` `json_schema` `strict: true`. O custo vem em `usage.cost`.
- **Lista de modelos de transcrição:** `/api/v1/models?output_modalities=all`. Sem esse parâmetro, o Scribe não aparece.

## 7. Descobertas (com prova)

1. **O ffmpeg 9.0.2 trava com `arnndn` seguido de `speechnorm`**: CPU em 100 % parada no fim do arquivo, e o processo não morre com SIGTERM. Prova (2026-10-29, vídeo de 33 s, `timeout -s KILL 8`):
   ```
   rc=0 1s :: arnndn=m=M,afftdn=nr=8:nf=-50
   rc=137 8s :: arnndn=m=M,speechnorm=e=4:r=0.0001:l=1
   ```
   `asetnsamples` entre os dois não resolveu. Usamos `dynaudnorm`, que roda em 1 s. Não volte para `speechnorm` depois de `arnndn`.
2. **IA real acertou o vídeo sintético** (`say -v Luciana`, com take abandonado e "corta isso"): 3 cortes, os 3 certos, US$ 0.0121 (transcrição 0.0020, editora 0.0098, revisora 0.0003).
3. **Nenhuma palavra cortada**: o `youtube.mp4` transcrito de novo saiu completo, "Hoje eu vou falar sobre como economizar dinheiro. ... Era isso, valeu".
4. **Sincronia**: vídeo com 14.247567 s e áudio com 14.247542 s. Volume final -13.6 LUFS (meta -14).
5. **Tempo num vídeo sintético de 15 min em 1080p** (modo de teste, sem IA, antes da etapa `player` existir): limpeza de áudio 46 s em cada uma das 2 passadas (19.6x tempo real); proxy 3 s; plano sem IA 96 s; render final (11:10 de saída, crf 18, preset medium, 235 trechos) 1413 s (23.5 min, meta 30). `testsrc2` é difícil de codificar; com vídeo real não foi medido.
6. **Download real do Drive**, arquivo público de 498 MB (`1l_5RK28JRL19wpT22B-DY9We3TVXnnQQ`, `.npz` do gdown, não é vídeo): com `confirm=t` veio direto (`206 application/octet-stream`, `content-disposition: attachment; filename="fcn8s_from_caffe.npz"`); sem ele, a página `Google Drive - Virus scan warning`. Chegaram 498881336 bytes, igual ao total do `content-range`, em 68 s (~4.5 MB/s). Link inexistente: `404 text/html`.
7. **Exemplos do README rodados num clone novo**: `talkedit config`, `editar --teste` e `refazer <pasta> plano --set estilo=natural` (natural ficou com 00:22, dinâmico com 00:20).
8. **Etapa 2 testada de verdade** (navegador Playwright, `curl` e IA real):
   - Página: arrastar e soltar (eventos `dragover`/`drop` com um `File` de 12 MB criado na página), envio, andamento, revisão, devolver, marcar arrastando, ouvir trecho (parou em 18.05 s para um trecho que termina em ~17.8 s + 0.3 s), prévia, aprovar, vídeo final, Padrões gravando `config.toml`. Em 390 px de largura, sem rolagem para o lado (`scrollWidth` 375).
   - API: sem código, 403; `Host: evil.com`, 403; segundo trabalho, 409; Range devolve `206` com `Content-Range: bytes 0-99/3203547`.
   - IA real pela página (vídeo falado de 33 s): 3 cortes certos; "refazer" com o pedido "corte tambem a frase Parece chato, mas funciona" gerou o corte `c4` com essa frase. Total US$ 0.0231.
9. **Bugs achados nos testes e corrigidos (cada um coberto por teste ou conferido de novo)**:
   - `editar` que falhava ao abrir o vídeo deixava `estado.json` e travava a nova tentativa.
   - A busca de "já baixado" do Drive podia pegar a pasta `<nome>_talkedit/`.
   - A página pedia o projeto antes dele existir ("Nao achei esse projeto").
   - A checagem do link do Drive no JS recusava link válido (exigia `/` duas vezes).
   - O botão "Trocar video" aparecia sem vídeo (o `display` do CSS anulava `hidden`; corrigido com `[hidden] { display: none !important; }`).
   - A linha de progresso mostrava mensagens de fora do trabalho.
   - Marcar um trecho de 1.8 a 2.3 s dava 0.4999 s por ponto flutuante e era recusado; o teste usa 1.8 a 2.35 s. Na página, o mínimo é checado com a mesma conta, então um arraste no limite exato pode ser recusado.

## 8. Regras de código que os hooks cobram

Valem para todo `.py`, inclusive testes. `~/.claude/hooks/immutable-rules-check.py` bloqueia na hora; um agente revisa no fim da sessão (já pediu duas correções: constantes na classe dona e ternário encadeado).

- Toda função dentro de uma classe. `__init__` só atribui (sem chamadas; use `@classmethod` de fábrica). Subclasse de stdlib que precisa de estado (ex.: `HTMLParser`) inicializa em `reset()`.
- No máximo 3 parâmetros (use dataclass frozen). Sem parâmetro booleano. Sem `*args`/`**kwargs` (por isso o handler do `http.server` sobrescreve `log_request`, não `log_message`).
- Métodos com até 20 linhas, classes com até 200, no máximo 2 níveis de aninhamento. Sem `elif` e **sem ternário encadeado** (use guard clauses, Enum ou dicionário).
- Sem número solto além de 0 e 1; sem nome vago (`result`, `run`, `data`, uma letra); sem `print`; sem `subprocess` (use `os.system` com `shlex`); sem `except Exception`.
- Sem estado global mutável. Constante nova vai para a classe dona como `ClassVar`; mapa fixo como `MappingProxyType`; status HTTP com `http.HTTPStatus`; mensagem fixa de erro na subclasse do erro; conversão de unidade num objeto de valor. Os módulos novos seguem isso; 20 módulos antigos ainda têm constantes no módulo (passam porque o hook só olha o que é novo em relação ao HEAD). Ao mexer neles, mova as constantes que tocar.
- Arquivo de código se escreve com Write ou Edit, nunca com redirecionamento do shell. Um formatador roda depois de cada edição (o `app.js` também é reformatado); releia antes de editar de novo.

## 9. O que foi feito

### Etapa 1 (`f189747`)

- [x] 5.1 Limpeza de áudio grátis com 4 intensidades e loudnorm em 2 passadas
- [x] 5.2 Transcrição com tempo por palavra, eventos de som e palavras difíceis
- [x] 5.3 Ritmo natural, dinâmico ou acelerado, sem cortar palavra, pausa protegida pela editora
- [x] 5.4 IA editora com vídeo leve, motivo em português, regras do usuário, postura por estilo
- [x] 5.5 IA revisora só de texto: devolve cortes, sugere mais, deixa observações
- [x] 5.14 (parte) CLI em português, retomar, refazer uma parte, `verificar`, erros com "O que fazer"
- [x] 5.15 (parte) config comentada, `--set`, estilos `dinamico` e `natural`, modelo por função
- [x] 5.16 Modo de teste com fakes
- [x] 5.17 (parte) custo real por função e relatório
- [x] Render do YouTube na resolução original, com emendas suaves, e prévia em 360p

### Entre as etapas

- [x] Repositório público no GitHub, sem binários de terceiros
- [x] Entrada por link público do Google Drive (pedido do dono)
- [x] `README.md` como guia para quem não programa (cobre boa parte da etapa 7)

### Etapa 2 (`d1beef3`, `3bcbb57`)

- [x] 5.6 Página de revisão, aba Edição: resumo, player com linha do tempo colorida, lista com motivo, ouvir, devolver e tirar, marcar trecho novo, pedir para refazer, prévia, aprovar
- [x] Tela Novo vídeo com arrastar e soltar e link do Drive (pedido do dono)
- [x] Tela Em andamento com etapas, tempo e custo, e retomada depois de erro
- [x] Tela Padrões gravando `~/.talkedit/config.toml` (decisão do dono)
- [x] 5.13 (parte) botão Abrir pasta no Finder
- [x] Offline e retomável: fechar a aba não para nada; tudo está em disco

## 10. O que falta

### Próxima ação

- [ ] **Rodar um vídeo real do dono** pela página (`talkedit abrir`), de 2 a 5 min, e medir custo, tempo, acerto dos cortes e as emendas de ouvido. Nada da etapa 3 deveria começar antes disso.

### Decisões pendentes do dono

- [ ] Licença do repositório (hoje nenhuma, então ninguém pode usar o código).
- [ ] Criar `main` com tudo e deixar como padrão (hoje o padrão é `etapa-1-video-longo`, que não tem a página).

### Pendências conhecidas

- [ ] Estimativa de custo antes de começar (5.17), com a duração do vídeo e os preços de `/api/v1/models`.
- [ ] Tempo restante do fluxo inteiro (5.14). Hoje a página mostra o tempo decorrido; o Terminal só estima dentro do render.
- [ ] Opção paga Auphonic (5.1).
- [ ] `continuar` pelo Terminal num projeto já pronto não mostra nada; deveria dizer onde está a entrega.
- [ ] Download do Drive interrompido recomeça do zero (não usa `Range`).
- [ ] Mostrar as pausas encurtadas na linha do tempo da revisão (hoje só o total).
- [ ] Testar: vídeo real no Drive, link privado do Drive, arrastar com o mouse de verdade, Finder de verdade, Safari, vídeo de vários GB pelo envio, etapa `player` num vídeo de 15 min.
- [ ] O desenho no canvas tem o erro antigo da checagem do link do Drive (só no desenho; o código já foi corrigido).

### Próximas etapas (ordem de `SPEC.md`, seção 7)

3. **Estilo dinâmico** (5.7): disfarce de jump cut (alternar o enquadramento por segmento) e zoom de ênfase (`EditPlan.emphasis` já vem da editora, sem uso ainda). O `crop`/`scale` entra no `-vf` de cada trecho em `SegmentEncoder`. Também a legenda `.srt` do YouTube, que precisa levar o tempo do original para o tempo editado (`Timeline`).
4. **Cortes verticais** (5.8 a 5.10): instalar `opencv-python` (já aprovado), YuNet em resolução baixa, legenda ASS karaokê com o filtro `ass` do `tools/ffmpeg`, área segura comum de Shorts, Reels e TikTok, aba Cortes na página.
5. **Textos e thumbnail** (5.11, 5.12) e aba Textos.
6. **Página de publicação** (5.13): checklist por plataforma e botões de copiar. O botão de Finder já existe.
7. **Guia de uso:** o `README.md` já cobre instalação, Terminal e página. Atualizar a cada etapa.

## 11. O que vigiar

| Risco | Por quê | Como checar |
|---|---|---|
| Custo da editora em vídeo longo | O Gemini cobra cada quadro; 15 min não foram medidos com IA real. Meta: menos de US$ 1 por vídeo de 15 min. | `trabalho/custos.json` de um vídeo real. Se só a editora passar de ~US$ 0.60, troque o vídeo por folhas de quadros ou baixe a taxa de quadros. |
| Tamanho do proxy no pedido | Vai em base64 no JSON; limite do provedor não testado. Proxy sintético de 15 min: 704 KB. | Tamanho de `trabalho/proxy.mp4`. Se a editora der erro de tamanho, divida. |
| Keyframes raros em vídeo de celular | `-skip_frame nokey` usa só keyframes. | `ffprobe -skip_frame nokey -select_streams v -show_entries frame=pts_time` no vídeo real. |
| Fim de palavra comido | Folga fixa (`PaceProfiles`) sobre o tempo do Scribe. | Ouvir as emendas; transcrever o `youtube.mp4` de novo. Melhora marcada com `ponytail:` em `pacing.py`. |
| Risada não reconhecida | `Word.is_laughter` procura "laugh", "ris" ou "gargalh"; o formato do Scribe em português não foi visto. | `audio_event` no `transcricao.json` de um vídeo com risada. |
| Modelos que mudam de nome | Modelos entram e saem do OpenRouter. | `talkedit verificar`. |
| Travamento do ffmpeg | Ver descoberta 1. | `ps aux \| grep tools/ffmpeg` e o tempo nos logs. |
| Mudança no download do Drive | Depende de `confirm=t` e do formulário `download-form`; há limite diário por arquivo. | Se aparecer "mostrou uma pagina em vez do video" num arquivo público, salve a página e confira o HTML. |
| Tempo de render | 23.5 min para 15 min sintéticos em 1080p; 4K vai demorar mais. A etapa `player` soma tempo no plano. | Medir com vídeo real. `render.velocidade_x264 = "fast"` é a válvula. |
| Página parada com o Terminal | A página depende do processo `talkedit abrir`; fechar o Terminal para o trabalho no meio. | Rodar `talkedit abrir` de novo e usar "Continuar de onde parou". |
| Código secreto da página | O endereço com `?t=` aparece no Terminal; quem tiver o código e acesso ao Mac usa a API. Muda a cada `abrir`. | Não colar esse endereço em lugar nenhum. |
| Envio de vídeo grande | Arrastar copia o vídeo inteiro; não testado com vários GB; ocupa espaço 2 vezes. | Tempo do envio e espaço em `~/Movies/talkedit/`. |
| Terminal e página no mesmo projeto | Só a página conhece o próprio trabalho em andamento. | Usar um dos dois por vez em cada projeto. |
| README desatualizado | É o único guia do dono e mostra saídas reais. | A cada etapa, rodar os exemplos do README num clone novo. |

## 12. Testes

- `uv run pytest`: 79 testes em ~14 s.
- `tests/test_end_to_end.py`: vídeo de 12 s (tom de 220 Hz com silêncio), `editar --teste` e `aprovar` pelo Terminal; confere sincronia, encurtamento e relatório; pega a volta do travamento do ffmpeg (usa a limpeza `normal`); arquivo que não é vídeo não deixa projeto.
- `tests/test_web.py`: Range, trava de acesso, envio de vídeo, `JobTracker` (409, erro com dica, crash inesperado) e um ponta a ponta com o servidor HTTP de verdade numa porta livre (enviar, planejar em modo de teste, devolver um corte, aprovar, ler o vídeo final com Range, abrir pasta com `FolderOpener` falso).
- `tests/test_settings_writer_and_changes.py`: gravar e reler padrões, ritmo omitido quando igual ao estilo, valor inválido não grava, `PlanChanges`, `ProjectRegistry`.
- Outros: pausas, linha do tempo, emenda de áudio, resposta da editora e da revisora, trava de risada, config, estado, pedaços da transcrição, cliente OpenRouter (transporte falso), progresso (relógio falso), Drive (`FakeFetcher`).
- Os testes usam classes com constantes nomeadas (regra de número solto). Construtores de teste em `tests/builders.py`.
- O JS (`app.js`) não tem teste automático; foi testado no navegador com Playwright (ver descoberta 8). As capturas ficam em `.playwright-mcp/`, fora do git.
- Para recriar o vídeo falado de teste:
  ```
  say -v Luciana -o fala.aiff "oi gente, deixa eu ver se ta gravando. [[slnc 2000]] Hoje eu vou falar ..."
  tools/ffmpeg -f lavfi -i "testsrc2=size=1280x720:rate=30000/1001" -i fala.aiff \
    -f lavfi -i "anoisesrc=color=brown:amplitude=0.03:sample_rate=48000" \
    -filter_complex "[1:a]aresample=48000[v];[v][2:a]amix=inputs=2:duration=first:normalize=0[a]" \
    -map 0:v -map "[a]" -shortest -c:v libx264 -c:a aac bruto.mp4
  ```
- Para testar a página sem mexer nos arquivos do dono: `HOME=<pasta temporária> OPENROUTER_API_KEY=x uv run talkedit abrir --porta 8799 --sem-navegador` e use o endereço que ele imprime (o modo de teste não usa a chave).

## 13. Regras de trabalho deste projeto

- Fale com o dono em português simples. Código, comentários, commits e identificadores em inglês. Textos que o usuário vê (CLI, página, config, relatório, README) em português.
- Não instale dependência nova sem perguntar.
- **Push só quando o dono pedir, a cada vez.** O repositório é público: confira se há segredo antes de qualquer push. Nunca reescreva histórico publicado.
- Nada de binário de terceiros sem licença clara no git.
- A v1 não publica vídeo em nenhuma plataforma.
- Ao fim de cada etapa: testes, ruff e mypy passando, um branch e commit por etapa, este arquivo e o README atualizados, e diga ao dono o que ele pode testar e como.
