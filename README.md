# Xadrez — Edição de Clube

Xadrez com IA em 3 níveis **e multiplayer online em tempo real**, direção de arte
"livro de escore" (papel, madeira, latão).
Regras básicas: movimentos, captura, promoção a dama, xeque, xeque-mate e afogamento
(**sem roque e sem en passant**).

O projeto tem **três caras** que compartilham o mesmo motor:

| Camada | Arquivo | Descrição |
|---|---|---|
| Motor (regras) | `chess_core.py` | Python puro, sem pygame. Engine + IA + notação. |
| Sessão de partida | `game_session.py` | Estado de uma partida; usado por tudo. |
| Salas de multiplayer | `multiplayer.py` | Salas, fila, chat e revanche — sem framework. |
| Rank mundial | `ranking.py` | Placar ELO em SQLite (biblioteca padrão). |
| App desktop | `chess_ai.py` | Jogo em janela, com pygame e animação de peças. |
| Backend web (deploy) | `server.py` | FastAPI: API JSON + WebSocket `/ws` + frontend. |
| Backend web (local, zero-instalação) | `server_stdlib.py` | Mesma coisa, só com a biblioteca padrão. |
| Frontend web | `web/` | HTML/CSS/JS estático. É o que vai para o GitHub Pages. |

---

## 1. Rodar o jogo desktop

```bash
pip install pygame
python chess_ai.py
```

Controles: clique para mover · `N` novo jogo · `U` desfazer · `1/2/3` nível · `ESC` sair.

## 2. Rodar a versão web localmente

Há **dois jeitos** de subir o servidor. Ambos servem o frontend de `web/` e a
mesma API em `/api/...`, então o navegador funciona igual.

### 2a. Modo rápido — sem instalar nada (recomendado para testar)

```bash
python server_stdlib.py
# abra http://127.0.0.1:8000
```

Também dá para simplesmente dar dois cliques em `start.bat` (Windows) ou rodar
`./start.sh` (Linux/WSL/macOS). Usa só a biblioteca padrão do Python.

### 2b. Modo FastAPI — igual ao que vai para produção

```bash
pip install -r requirements.txt
uvicorn server:app --reload
# abra http://127.0.0.1:8000
```

> **Deu erro no `pip`?** Ver a seção *Solução de problemas* abaixo.
> Se a pasta do projeto está no OneDrive (`Documents`, `Área de Trabalho`), evite
> criar o `.venv` dentro dela — o OneDrive corrompe o `pip`. Crie o ambiente
> virtual em outro lugar (ex.: `C:\venvs\xadrez`) ou use o modo 2a.

### 2c. Jogar online (multiplayer)

O multiplayer funciona nos **dois** servidores (o WebSocket está implementado
tanto no `server_stdlib.py` quanto no FastAPI). Para testar sozinho, abra duas
janelas do navegador:

1. Suba o servidor (2a ou 2b) e abra `http://127.0.0.1:8000`.
2. Mude o **MODO** para **ONLINE** e clique em **CRIAR SALA**. Anote o código
   (ex.: `A7K2`) ou clique em **copiar link**.
3. Na segunda janela, **ONLINE** → digite o código e **ENTRAR** — ou abra
   direto `http://127.0.0.1:8000/?sala=A7K2`.
4. Joguem: quem criou começa de brancas. Use a **CONVERSA** e, no fim, **REVANCHE**
   (troca as cores). Uma terceira janela que entrar na mesma sala vira
   **espectadora**.

> Para jogar com alguém em outra rede, o servidor precisa estar acessível (ex.:
> publicado no Render). Sem isso, o WebSocket só alcança a sua própria máquina.

---

## 3. Publicar

### 3.1 Backend (FastAPI) — no Render
> **GitHub Pages não roda Python.** O backend precisa de um host de servidor.

1. Suba o repositório no GitHub.
2. No [Render](https://render.com), crie um **Web Service** a partir do repositório
   (ou use o blueprint `render.yaml`, que já vem pronto).
3. Build: `pip install -r requirements.txt`
   Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. Anote a URL pública, ex.: `https://xadrez-clube.onrender.com`.

O CORS já está liberado (`allow_origins=["*"]`), então o frontend em outro domínio funciona.

### 3.2 Frontend — no GitHub Pages
1. Edite `web/config.js` e aponte para o backend:
   ```js
   window.CHESS_API_BASE = "https://xadrez-clube.onrender.com";
   ```
2. Publique o conteúdo de `web/` no GitHub Pages (Settings → Pages → escolha a
   pasta `web/` ou uma branch `gh-pages`).
3. Acesse a URL do Pages — o tabuleiro abre e conversa com o backend.

> Também funciona tudo no mesmo host: se o frontend for servido pelo próprio
> FastAPI, deixe `CHESS_API_BASE = ""`.

---

## 4. API

| Método | Rota | Corpo | Retorno |
|---|---|---|---|
| GET | `/api/health` | — | `{ok, games, lobby}` |
| GET | `/api/ranking` | `?limit=50` | `{top:[...], total}` — top do rank mundial |
| GET | `/api/player/{id}` | — | perfil de um jogador (rating, V/E/D, posição) |
| POST | `/api/new` | `{level, human_color}` | `{game_id, state}` |
| GET | `/api/state/{game_id}` | — | `{state}` |
| POST | `/api/move` | `{game_id, move:[fr,fc,tr,tc]}` | `{state}` |
| POST | `/api/ai` | `{game_id}` | `{state, ai_move}` |
| POST | `/api/undo` | `{game_id}` | `{state}` |
| POST | `/api/level` | `{game_id, level}` | `{state}` |
| WS | `/ws` | ver abaixo | ver abaixo |

O `state` inclui tabuleiro, turno, lances legais, histórico (SAN), capturadas,
estado de xeque/fim e os dados da animação (`anim`).

### 4.1 Multiplayer (WebSocket `/ws`)

No modo **ONLINE** do frontend, o navegador abre um WebSocket. Mensagens JSON:

**Cliente → servidor**

| Tipo | Campos | Efeito |
|---|---|---|
| `create` | `name?, pid?` | cria uma sala (você fica com as brancas) |
| `join` | `code, name?, pid?` | entra numa sala pelo código (4 letras) |
| `queue` | `name?, pid?` | entra na fila e é pareado com o próximo |
| `move` | `move:[fr,fc,tr,tc]` | faz um lance |
| `chat` | `text` | manda mensagem |
| `rematch` | — | pede revanche (as cores trocam) |
| `leave` | — | sai da sala |
| `ping` | — | keep-alive |

O **`pid`** identifica você no rank: o frontend gera um ID e guarda no
`localStorage` (junto com o apelido). Sempre que você entra no online ele é
enviado, então vitórias/derrotas caem na sua conta mesmo trocando de janela.

**Servidor → cliente**: `created`, `room` (código, sua cor, status, nomes),
`state` (estado autoritativo — igual ao REST, com `human_color` personalizado
para você), `chat`, `sys` (avisos do sistema), `queued`, `error`, `pong`,
`rating` (seu perfil: rating, posição e delta depois de cada partida) e
`ranking_refresh` (aviso de que o placar global mudou).

Recursos: **sala por código**, **link de convite** (`?sala=A7K2`), **fila
aleatória**, **espectadores** (quem entra depois da sala cheia assiste),
**chat**, **revanche** com troca de cores e **rank mundial**. Toda a validação
de lance é feita no servidor — um cliente nunca decide o resultado.

### 4.2 Rank mundial (ELO)

- Rating inicial **1200**; a partida mexe no rating conforme a força do
  adversário (fórmula ELO, `K=32`).
- Só contam partidas **online entre humanos** terminadas por **xeque-mate,
  afogamento, empate** ou **W.O.** (quem abandona uma partida em andamento
  perde).
- O placar fica num **SQLite** persistente (nível do projeto): **`~/.xadrez/
  ranking.db`** — de propósito **fora do OneDrive**, que atrapalha arquivos
  sincronizados. Para apontar outro lugar (ex.: um disco no Render), defina a
  variável **`XADREZ_DB`**:
  ```bash
  XADREZ_DB=/data/ranking.db uvicorn server:app --port $PORT
  ```
- O painel **RANKING MUNDIAL** fica sempre visível na página: top 20, suas
  V/E/D e sua posição. Ele atualiza sozinho quando uma partida termina.

## 5. Níveis da IA
- **Fácil** — profundidade 1, 55% de lance aleatório.
- **Médio** — profundidade 3, quiescence.
- **Difícil** — profundidade 4, quiescence, *iterative deepening* com teto de tempo.

## 6. Testes

Todos os testes usam **só a biblioteca padrão** (os de FastAPI/pygame têm stubs
embutidos) e rodam da raiz do repositório:

```bash
python tests/test_chess.py        # regras do motor
python tests/test_gui.py          # fluxo/desenho do app desktop
python tests/test_server.py       # API (stub de FastAPI)
python tests/test_stdlib.py       # HTTP real do servidor stdlib
python tests/test_multiplayer.py  # lógica de salas
python tests/test_ws.py           # WebSocket fim-a-fim (e2e real)
python tests/test_ranking.py      # ELO, persistência, casos inválidos
python tests/test_ws_rank.py      # e2e: partida pontuada + W.O.
```

No Windows, cada um pode ser rodado com `py tests/test_ws_rank.py` (o `py`
launcher acha o Python certo). Os dois testes e2e sobem o servidor numa porta
livre e encerram sozinhos.

## 7. Limitações conhecidas
- As partidas e as **salas de multiplayer** ficam **em memória** no servidor:
  reiniciar o processo apaga as salas em andamento (ok para demonstração; para
  produção, use Redis/DB e pub/sub entre instâncias). O **rank mundial**, porém,
  **persiste** em `ranking.db` — e no Render ele sobrevive enquanto o disco
  estiver montado na mesma instância.
- Sem roque e sem en passant (decisão do projeto).
- **Não há reconexão**: se você fechar a aba, sai da sala. (Uma partida
  abandonada vira **derrota por W.O.** do lado de quem saiu, e a pontuação é
  aplicada.)
- Um único worker (sem compartilhamento de estado entre instâncias).

## 8. Solução de problemas

**`ModuleNotFoundError: No module named 'pip._internal.cli'`**
O `pip` do seu `.venv` está corrompido — quase sempre porque a pasta do projeto
está no **OneDrive** (`Documents`, `Área de Trabalho`, `Imagens`), que sincroniza
e corrompe os milhares de arquivos de um ambiente virtual. Saídas:

1. **Testar agora:** use `python server_stdlib.py` (não precisa de `pip`). ✅
2. Recrie o ambiente virtual **fora do OneDrive**:
   ```bat
   rmdir /s /q .venv
   python -m venv C:\venvs\xadrez
   C:\venvs\xadrez\Scripts\python.exe -m pip install -r requirements.txt
   C:\venvs\xadrez\Scripts\python.exe -m uvicorn server:app
   ```

**`ModuleNotFoundError: No module named 'pygame'`**
É o app desktop; instale a dependência: `pip install pygame`.

**A porta 8000 já está em uso:** feche o outro servidor ou edite `PORT` em
`server_stdlib.py` (e ajuste `CHESS_API_BASE` em `web/config.js`, se necessário).

**A janela web abriu mas o tabuleiro não aparece:** abra o Console do navegador
(F12). Se houver erro de CORS/rede, confirme que o servidor está rodando e que
`web/config.js` aponta para a URL correta.

