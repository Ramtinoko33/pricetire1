# Pneu Price Scout — frontend

React 19 + Vite 5 + Tailwind 3 + shadcn/ui. Contrato da API: `docs/ARQUITECTURA_RECUPERACAO.md` (secção "API HTTP").

```bash
npm install
VITE_BACKEND_URL=http://localhost:8000 npm start   # dev contra o backend
VITE_USE_MOCK=1 npm start                          # dev com API simulada (dados fictícios)
npm run build                                      # build de produção (sem mock)
npm test                                           # Vitest
```

O mock (`src/lib/mock.js`) só entra no bundle quando `VITE_USE_MOCK=1` está definido no momento do build. No mock qualquer email/password inicia sessão como admin (password `errada` simula 401).
