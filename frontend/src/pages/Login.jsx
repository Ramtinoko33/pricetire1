import React, { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Loader2, LogIn } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { errorMessage } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const Login = () => {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const from = location.state?.from && location.state.from !== '/login' ? location.state.from : '/';

  if (isAuthenticated) return <Navigate to={from} replace />;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      const status = err?.response?.status;
      setError(status === 401 || status === 400
        ? errorMessage(err, 'Email ou palavra-passe incorrectos')
        : errorMessage(err, 'Não foi possível iniciar sessão'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[minmax(320px,440px)_1fr]" data-testid="login-page">
      <aside className="bg-sidebar text-sidebar-foreground px-6 py-6 sm:px-10 lg:flex lg:flex-col lg:justify-between lg:py-12">
        <div>
          <p className="text-xl font-extrabold tracking-[-0.03em]">Pneu Price Scout</p>
          <p className="mt-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-sidebar-muted">Comparador B2B</p>
        </div>
        <p className="hidden lg:block max-w-xs text-sm leading-relaxed text-sidebar-muted">
          Preços de compra, stock e datas de recolha dos fornecedores, num só lugar.
        </p>
      </aside>
      <main className="flex items-start justify-center px-4 py-10 sm:py-16 lg:items-center">
        <div className="w-full max-w-[400px] rounded-lg border border-border border-t-[3px] border-t-primary bg-card p-6 text-card-foreground shadow-panel sm:p-8">
          <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Acesso</p>
          <h1 className="text-2xl font-extrabold tracking-[-0.02em]">Iniciar sessão</h1>
          <p className="mt-1.5 mb-6 text-sm text-muted-foreground">Use as credenciais da sua conta.</p>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-xs font-semibold">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                aria-describedby={error ? 'login-error' : undefined}
                data-testid="login-email"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-xs font-semibold">Palavra-passe</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                aria-describedby={error ? 'login-error' : undefined}
                data-testid="login-password"
              />
            </div>
            {error && (
              <p id="login-error" className="rounded-md border border-danger/30 bg-danger-subtle px-3 py-2 text-sm text-danger" role="alert" data-testid="login-error">{error}</p>
            )}
            <Button type="submit" size="lg" className="w-full" disabled={loading || !email || !password} data-testid="login-submit">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
              Entrar
            </Button>
          </form>
        </div>
      </main>
    </div>
  );
};

export default Login;
