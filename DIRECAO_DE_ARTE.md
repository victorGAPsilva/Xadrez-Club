# Xadrez — Edição de Clube · Direção de Arte

## 1. Conceito
O xadrez como **objeto de biblioteca e de torneio**, não como aplicativo genérico.
A interface deve lembrar um livro de escore sobre uma mesa de madeira: papel,
tinta, latão e nada mais. A pergunta-guia do projeto:

> "Removendo sombras e efeitos, ainda existe um design forte e reconhecível?"

Resposta: sim — a força está na grelha de 8×8, na moldura de madeira e na
tipografia editorial.

## 2. Referências (características, não cópias)
- Papel de livro envelhecido e réguas finas de impressão editorial.
- Tabuleiro de torneio em madeira (nogueira/faia).
- Plaquetas de latão gravadas (numeração de museu/troféu).
- Fichas de anotação de partidas (notação algébrica em monoespaçada).

## 3. Paleta (com função)
| Token       | Hex       | Função                                   |
|-------------|-----------|------------------------------------------|
| PAPER       | `#EDE6D6` | fundo geral (papel)                      |
| PAPER_DIM   | `#E0D6C2` | superfície de botões inativos            |
| RULE        | `#C6B698` | réguas/separadores finos                 |
| INK         | `#1C1914` | texto principal e peças pretas           |
| INK_SOFT    | `#5C5446` | texto secundário                         |
| FRAME       | `#4A3828` | moldura de madeira do tabuleiro          |
| BOARD_L     | `#E9DEC2` | casa clara                               |
| BOARD_D     | `#7C5E40` | casa escura                              |
| BRASS       | `#B08D57` | destaque, estado ativo, coordenadas      |
| BLOOD       | `#962C26` | xeque / perigo                           |
| GOOD        | `#4A6E56` | jogadas legais                           |

Contraste não depende só de cor: peças usam **contorno de contraste**
(clara com contorno escuro / escura com contorno claro); alvos de jogada usam
**forma** (disco = casa vazia, anel = captura).

## 4. Tipografia
- Títulos: serifada (Georgia / Palatino / Cambria).
- Dados e HUD: sans-serif (Segoe UI / Calibri).
- Notação: monoespaçada (Consolas / DejaVu Sans Mono).
- Peças: glifos Unicode vetoriais (Segoe UI Symbol / DejaVu Sans).
- Rótulos de seção em versalete com espaçamento (aspecto editorial).

## 5. Composição
- Tabuleiro à esquerda sobre moldura de madeira com filete de latão.
- À direita, um **livro de escore**: nível do oponente, cartão de vez,
  notação, capturadas e ações.
- Hierarquia por réguias finas, não por caixas arredondadas.
- Estados: seleção (latão), última jogada (âmbar), xeque (sangue, pulsante),
  jogadas legais (verde), fim de partida (overlay de tinta).

## 6. Movimento (animação)
Princípio: a animação existe para tornar o tabuleiro **físico e legível**, não para
enfeitar. Regras adotadas:
- Deslize curto de **180 ms** com *ease-out* cúbico — não atrasa a partida.
- A peça é **erguida** suavemente no meio do trajeto, com sombra de contato que
  encolhe: reforça a peça como objeto real, sem sombras exageradas.
- Peça capturada **desvanece** no primeiro trecho (a perda é percebida).
- Durante o voo a peça de destino é omitida; a jogada só "conclui" (xeque/IA)
  quando ela **assenta**, preservando a causalidade visual.
- Interação de tabuleiro bloqueada durante o voo (evita estados inconsistentes);
  botões de nível/novo/desfazer seguem ativos.

## 7. Tokens técnicos
Todas as cores, dimensões e fontes estão centralizadas no topo de
`chess_ai.py` (`class C`, constantes de geometria e `make_font`), para manter
a identidade consistente e permitir ajustes em um único lugar.
