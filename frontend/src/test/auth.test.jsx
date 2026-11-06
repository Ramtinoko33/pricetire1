import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider, RequireAdmin, RequireAuth } from '@/lib/auth';
import { clearSession, getToken, setSession } from '@/lib/session';

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>ecrã de login</div>} />
          <Route path="/" element={<RequireAuth><div>área privada</div></RequireAuth>} />
          <Route path="/admin" element={<RequireAuth><RequireAdmin><div>área admin</div></RequireAdmin></RequireAuth>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('guarda de rotas', () => {
  it('sem sessão redirecciona para /login', () => {
    clearSession();
    renderAt('/');
    expect(screen.getByText('ecrã de login')).toBeInTheDocument();
  });

  it('com sessão mostra a área privada', () => {
    setSession('tok', { id: 1, email: 'a@b.test', role: 'user' });
    renderAt('/');
    expect(screen.getByText('área privada')).toBeInTheDocument();
  });

  it('utilizador sem role admin não vê a área admin', () => {
    setSession('tok', { id: 1, email: 'a@b.test', role: 'user' });
    renderAt('/admin');
    expect(screen.queryByText('área admin')).not.toBeInTheDocument();
    expect(screen.getByTestId('forbidden')).toBeInTheDocument();
  });

  it('admin vê a área admin', () => {
    setSession('tok', { id: 1, email: 'a@b.test', role: 'admin' });
    renderAt('/admin');
    expect(screen.getByText('área admin')).toBeInTheDocument();
  });

  it('clearSession remove o token', () => {
    setSession('tok', { id: 1 });
    clearSession();
    expect(getToken()).toBeNull();
  });
});
