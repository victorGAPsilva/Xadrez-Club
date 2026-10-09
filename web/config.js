// Configuração do backend.
//
// NO GITHUB PAGES: coloque a URL pública do seu servidor (FastAPI/Render), ex.:
//   window.CHESS_API_BASE = "https://xadrez-clube.onrender.com";
//
// O multiplayer usa WebSocket derivado desta URL (http->ws / https->wss).
// Se o frontend for servido pelo próprio servidor (uvicorn ou stdlib), deixe vazio:
window.CHESS_API_BASE = "";
