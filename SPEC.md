# Editor de vídeo com IA para talking head (especificação de produto)

Especificação escrita pelo dono do produto em 2026-10-29. Este arquivo é a fonte de verdade
do que o produto faz. As decisões técnicas estão em `README.md` e no código.

---

## 1. Visão

Sou criador de conteúdo. Gravo vídeos brutos falando para a câmera, sozinho, em português,
e perco horas editando. Quero uma ferramenta que eu rodo pela linha de comando no meu Mac:
eu entrego o vídeo bruto, ela edita como um editor humano faria, me mostra o plano numa página
no navegador para eu aprovar, e me entrega tudo pronto para eu publicar no YouTube, YouTube
Shorts, Instagram Reels e TikTok.

Nesta primeira versão a ferramenta **não publica**. Ela entrega os arquivos e os textos
organizados, e eu subo à mão.

## 2. Ambiente

- **Mac com processador Intel**, sem placa de vídeo dedicada. Tudo precisa rodar bem nessa
  máquina. Confirme que cada biblioteca escolhida funciona em Mac Intel antes de usar.
- Partes pesadas (análise de imagem, prévias) devem trabalhar em resolução reduzida para não
  demorar. Meta: um vídeo bruto de 15 minutos fica pronto para revisão em até 15 minutos,
  e o render final em até 30 minutos.
- Uso só pela linha de comando, mais a página de revisão local no navegador.
- Todos os modelos de IA passam pelo **OpenRouter**.
- Consulte a documentação atual do OpenRouter e a lista atual de modelos antes de implementar.

## 3. Princípios

1. **Eu aprovo sempre.** A ferramenta para depois de planejar, me mostra o plano e só renderiza
   a versão final depois que eu aprovar.
2. **A IA decide, não desenha.** A IA escolhe o que cortar, quais trechos usar e escreve os
   textos. A imagem nunca é gerada nem alterada por IA. O resultado é sempre o meu vídeo.
3. **Tudo é explicável.** Cada corte vem com o motivo, em português simples.
4. **Nada se perde.** O original nunca é alterado. Posso desfazer qualquer decisão e renderizar de novo.
5. **Qualidade de editor profissional.** Se alguém perceber que foi editado por máquina
   (estalo de áudio, legenda fora de sincronia, rosto cortado, salto feio na emenda), falhou.
6. **Equilíbrio entre qualidade e custo.** Modelo de IA forte só onde faz diferença (a edição),
   modelos mais baratos no resto. Limpeza de áudio gratuita por padrão.
7. **Custo visível.** Sempre sei quanto cada vídeo custou.

## 4. O que eu recebo no final

| Entrega | Descrição |
|---|---|
| Vídeo do YouTube | 16:9, editado em estilo dinâmico, áudio limpo, resolução original |
| Legenda do YouTube | Arquivo de legenda sincronizado com o vídeo editado |
| Cortes verticais | 3 vídeos 9:16 com legenda animada, que servem para Shorts, Reels e TikTok |
| Thumbnail | Imagem 1280x720 com o melhor frame |
| Textos por plataforma | YouTube, Shorts, Reels e TikTok, cada um no formato daquela plataforma |
| Página de publicação | Página local com cada arquivo e cada texto pronto para copiar, por plataforma |
| Relatório | O que foi cortado e por quê, duração antes e depois, custo |

## 5. Features

### 5.1 Limpeza de áudio
Remove ruído de fundo, reduz eco de sala, equilibra o volume da voz e deixa o volume final no
padrão das plataformas. A voz soa próxima e clara. O áudio limpo é usado em tudo. Intensidade:
leve, normal (padrão), forte ou desligado. Gratuito por padrão; opção de serviço pago (Auphonic).

### 5.2 Transcrição
Transcreve tudo com o momento exato de cada palavra. Precisão alta em português. Marca eventos
que não são fala, principalmente risadas. Lista de palavras difíceis que vale para todos os
vídeos. Modelo: o melhor do OpenRouter com tempo por palavra (hoje: ElevenLabs Scribe v2).

### 5.3 Ritmo e silêncios (estilo dinâmico)
Remove praticamente todas as pausas entre frases, deixando só um respiro curto e natural.
Nunca corta no meio de uma palavra. Pausas dramáticas intencionais são protegidas pela IA
editora. Ritmo: natural, dinâmico (padrão) ou acelerado.

### 5.4 Remoção de takes ruins (IA editora)
Lê a transcrição, assiste uma versão leve do vídeo e marca o que deve sair.
Remove: takes repetidos (mantém a melhor, normalmente a última), frases abandonadas, comandos
para a edição ("corta isso", "de novo", "vou repetir"), conversa antes de começar e depois de
terminar, momentos visuais ruins (olhei para o lado, tossi, saí do quadro, mexi no celular).
Nunca remove: piadas e momentos com risada, pausas dramáticas. Na dúvida, mantém.
Cada trecho removido vem com tempo, texto e motivo. Exemplo: "02:14 a 02:31, 'então o primeiro
ponto é...', take repetido, mantive a versão de 02:32, mais fluida."
Regras próprias em português normal, que valem para todos os vídeos.
Modelo: o mais capaz disponível com entrada de vídeo.

### 5.5 Revisão da edição (IA revisora)
Segunda IA confere o trabalho da editora antes de eu ver. Lê como o vídeo ficaria depois dos
cortes e procura frase sem sentido, raciocínio quebrado, corte arriscado. Pode devolver trechos
removidos ou sugerir remover mais. As observações aparecem na página de revisão. Modelo
intermediário (só texto).

### 5.6 Página de revisão no navegador
Depois de planejar, a ferramenta para e abre uma página local.
- Aba "Edição": resumo ("18:40 vai ficar com 12:05, 23 trechos removidos"), player do original
  com linha do tempo colorida, lista dos trechos removidos com tempo, texto, motivo e botão para
  ouvir, botão para devolver ou remover, marcar trecho novo na linha do tempo, caixa de texto
  para pedir à IA refazer o plano, botão "Gerar prévia", botão "Aprovar edição".
- Aba "Cortes": os 3 cortes com prévia, título, gancho e motivo; ajustar início e fim, trocar
  um corte pedindo em texto, pedir mais opções; botão "Aprovar cortes".
- Aba "Textos e thumbnail": títulos, descrição, capítulos, tags e textos editáveis; thumbnail
  com outras 5 opções; botão "Aprovar e renderizar final".
- Funciona offline. Posso fechar e reabrir e continuar. Depois do render final vira a página
  de publicação.

### 5.7 Vídeo final para YouTube
Disfarce de jump cut (alterna enquadramento normal e levemente mais fechado nas emendas). Zoom
de ênfase suave em frases importantes marcadas pela IA. Emendas de áudio suaves. Qualidade de
imagem igual à do original. Volume no padrão do YouTube. Intensidade dos zooms: sutil, normal
(padrão), forte ou desligado. Legenda do YouTube sincronizada.

### 5.8 Cortes verticais (IA de cortes)
Trechos que fazem sentido sozinhos, gancho forte nos 3 primeiros segundos, começa e termina em
frase completa, considera a imagem. Cada corte com título, gancho e motivo. Quantidade (padrão
3), duração mínima e máxima (padrão 20 a 60 s), regras próprias. Mesmo arquivo para Shorts,
Reels e TikTok, legenda e rosto na área segura comum. Modelo rápido e barato com vídeo.

### 5.9 Enquadramento vertical que segue o rosto
Câmera acompanha o rosto suavemente, sem tremer. Rosto nunca sai do quadro nem fica cortado.
Se eu sair do quadro, fica parado no último enquadramento bom. Alternativa: centro fixo.
Mesmos zooms e disfarce de jump cut do YouTube.

### 5.10 Legenda animada nos cortes
3 palavras por vez, palavra falada destacada em outra cor, sincronia perfeita, área segura.
Personalizável: fonte, tamanho, cores, contorno, maiúsculas, palavras por vez, altura. Estilo
salvo para todos os vídeos.

### 5.11 Textos por plataforma (IA redatora)
YouTube: 3 títulos (até 70 caracteres), descrição de 2 a 4 parágrafos, capítulos pelas regras
do YouTube (primeiro em 0:00, mínimo 3, cada um com pelo menos 10 s, ou nenhum), até 15 tags.
Por corte: Shorts (título e descrição curtos), Reels (gancho na primeira linha e hashtags),
TikTok (curta, direta, hashtags). Tom de voz configurável. Tudo editável. Modelo bom em
português, custo moderado.

### 5.12 Thumbnail
IA olha vários frames e escolhe o de melhor expressão. Sugere texto de até 4 palavras. Mostra
outras 5 opções.

### 5.13 Página de publicação
Uma seção por plataforma com o arquivo e cada texto com botão de copiar. Checklist do que já
foi publicado. Botão para abrir a pasta no Finder.

### 5.14 Linha de comando
Um comando com o caminho do vídeo. Progresso claro em português com tempo restante. Refazer só
uma parte. Retomar depois. Erros em português claro com o que fazer. Comando para verificar a
instalação.

### 5.15 Configurações
Arquivo legível com explicação em português. Modelo de IA por função. Trocar qualquer opção numa
execução só. Dois estilos prontos: dinâmico (padrão) e natural.

### 5.16 Modo de teste
Fluxo inteiro sem gastar com IA, com respostas simuladas.

### 5.17 Custo e relatório
Estimativa antes de começar. Custo real por função. Relatório final. Meta: menos de US$ 1 por
vídeo de 15 minutos.

## 6. Fora do escopo desta versão
Publicação automática, várias pessoas, tutorial de tela, chat com IA, B-roll ou imagem gerada
por IA, música, correção de cor, vários vídeos ao mesmo tempo.

## 7. Ordem de entrega
1. Edição do vídeo longo (modo de teste, depois IA real).
2. Página de revisão, aba Edição.
3. Estilo dinâmico.
4. Cortes verticais, enquadramento, legenda, aba Cortes.
5. Textos e thumbnail, aba Textos.
6. Página de publicação.
7. Guia de uso em português.

## 8. Como vou avaliar
Não percebo os cortes. Ritmo de canal profissional. Nenhuma piada removida sem pedir. Rosto
nunca sai do quadro nos verticais e legenda em sincronia. Textos soam como eu. Aprovo tudo pela
página. Roda no Mac Intel no tempo prometido. Menos de US$ 1 por vídeo de 15 minutos.
