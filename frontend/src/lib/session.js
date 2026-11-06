// Persistência da sessão (token + utilizador). Todos os acessos ao storage
// estão protegidos: em modo privado ou com storage bloqueado a app continua a
// funcionar, apenas sem persistência entre recargas.

const TOKEN_KEY = 'pps_token';
const USER_KEY = 'pps_user';

let memoryToken = null;
let memoryUser = null;
const listeners = new Set();

function safeGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key, value) {
  try {
    if (value === null || value === undefined) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage indisponível */
  }
}

export function getToken() {
  return memoryToken ?? safeGet(TOKEN_KEY);
}

export function getStoredUser() {
  if (memoryUser) return memoryUser;
  const raw = safeGet(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setSession(token, user) {
  memoryToken = token;
  memoryUser = user;
  safeSet(TOKEN_KEY, token);
  safeSet(USER_KEY, user ? JSON.stringify(user) : null);
  listeners.forEach((fn) => fn({ token, user }));
}

export function updateStoredUser(user) {
  memoryUser = user;
  safeSet(USER_KEY, user ? JSON.stringify(user) : null);
  listeners.forEach((fn) => fn({ token: getToken(), user }));
}

export function clearSession() {
  memoryToken = null;
  memoryUser = null;
  safeSet(TOKEN_KEY, null);
  safeSet(USER_KEY, null);
  listeners.forEach((fn) => fn({ token: null, user: null }));
}

export function onSessionChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
