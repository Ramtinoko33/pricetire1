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
        ? errorMessage(err, 'Email ou password incorrectos')
        : errorMessage(err, 'Não foi possível iniciar sessão'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 dark:bg-zinc-950 px-4" data-testid="login-page">
      <div className="w-full max-w-sm rounded-lg bg-card text-card-foreground shadow-xl p-6 sm:p-8">
        <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>Pneu Price Scout</h1>
        <p className="text-sm text-muted-foreground mt-1 mb-6">Inicie sessão para continuar</p>
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="space-y-1">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              data-testid="login-email"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              data-testid="login-password"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600 dark:text-red-400" role="alert" data-testid="login-error">{error}</p>
          )}
          <Button type="submit" className="w-full" disabled={loading || !email || !password} data-testid="login-submit">
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <LogIn className="mr-2 h-4 w-4" />}
            Entrar
          </Button>
        </form>
      </div>
    </div>
  );
};

export default Login;
