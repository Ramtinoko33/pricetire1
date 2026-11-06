import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { authAPI } from './api';
import { clearSession, getStoredUser, getToken, onSessionChange, setSession, updateStoredUser } from './session';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => getToken());
  const [user, setUser] = useState(() => (getToken() ? getStoredUser() : null));
  const [checking, setChecking] = useState(() => Boolean(getToken()));

  useEffect(() => onSessionChange(({ token: t, user: u }) => {
    setToken(t);
    setUser(u);
  }), []);

  // Validar o token guardado ao arrancar (o interceptor limpa a sessão em 401).
  useEffect(() => {
    if (!getToken()) {
      setChecking(false);
      return;
    }
    let cancelled = false;
    authAPI.me()
      .then(({ data }) => { if (!cancelled && data) updateStoredUser(data); })
      .catch(() => { /* 401 tratado pelo interceptor; outros erros mantêm a sessão local */ })
      .finally(() => { if (!cancelled) setChecking(false); });
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async (email, password) => {
    const { data } = await authAPI.login(email, password);
    setSession(data.token, data.user);
    return data.user;
  }, []);

  const logout = useCallback(() => clearSession(), []);

  const value = useMemo(() => ({
    token,
    user,
    checking,
    isAuthenticated: Boolean(token),
    isAdmin: user?.role === 'admin',
    login,
    logout,
  }), [token, user, checking, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth tem de ser usado dentro de <AuthProvider>');
  return ctx;
}

export function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return children;
}

export function RequireAdmin({ children }) {
  const { isAdmin, user } = useAuth();
  if (!user) return null;
  if (!isAdmin) {
    return (
      <div className="py-16 text-center" data-testid="forbidden">
        <p className="text-lg font-semibold">Acesso reservado a administradores</p>
        <p className="text-sm text-muted-foreground mt-1">A sua conta não tem permissões para esta área.</p>
      </div>
    );
  }
  return children;
}
