# talkedit

Editor de video com IA para talking head. O que o produto faz esta em `SPEC.md`.
Estado atual, descobertas, pendencias e riscos: `KNOWLEDGE.md` (leia antes de mexer).
O guia de uso para quem nao programa vem na etapa 7 (`GUIA.md`).

## Decisoes tecnicas

- Python 3.11, uma dependencia (`pydantic`). Testes com `pytest`, tipos com `mypy`.
- ffmpeg estatico 9.0.2 (evermeet.cx, Intel) em `tools/`, com libass para a legenda animada.
  O ffmpeg do brew nao tem libass. `tools/sh.rnnn` e o modelo RNNoise de voz (GregorR/rnnoise-models).
  Nenhum dos tres vai no git; os comandos para baixar estao em `KNOWLEDGE.md`, secao 3.
- Comandos externos rodam com `os.system` e a saida vai para `trabalho/logs/` de cada projeto.
- Limpeza de audio gratuita: `highpass`, `arnndn`, `afftdn`, `dynaudnorm`, `acompressor` e
  `loudnorm` em duas passadas (-14 LUFS). `speechnorm` depois de `arnndn` trava o ffmpeg 9.0.2.
- Transcricao: `elevenlabs/scribe-v2` pelo `/api/v1/audio/transcriptions`, em pedacos de ~2 min
  cortados no meio de um silencio (o provedor desiste depois de 60 s por pedido).
- IA editora: `google/gemini-4-argon` com a transcricao (indice por palavra) e uma copia de
  360p a 1 quadro por segundo, sem som. Resposta em JSON com esquema estrito.
- IA revisora: `google/gemini-3.5-flash-lite`, so texto. Pode devolver cortes; o que ela sugere
  cortar a mais fica como sugestao.
- Corte que encosta em risada volta para o video, sempre (`LaughterGuard`).
- Pausas nao ficam salvas no plano: sao recalculadas sobre as palavras que ficaram.
- Render: cada trecho mantido vira um arquivo (em paralelo, reaproveitado se nao mudou), o audio
  e emendado em Python no grid de quadros com fade de 6 ms, e tudo junta com o concat do ffmpeg.

## Desenvolvimento

```
uv sync
uv run pytest
uv run ruff check src tests
uv run mypy src
uv run talkedit editar video.mp4 --teste
```
