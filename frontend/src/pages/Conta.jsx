import React, { useState } from 'react';
import { Loader2, KeyRound } from 'lucide-react';
import { toast } from 'sonner';
import { authAPI } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { errorMessage } from '@/lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PageHeader, Field } from '@/components/common';

const MIN_LEN = 8;

const Conta = () => {
  const { user } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (next.length < MIN_LEN) {
      setError(`A nova password tem de ter pelo menos ${MIN_LEN} caracteres.`);
      return;
    }
    if (next !== confirm) {
      setError('A confirmação não coincide com a nova password.');
      return;
    }
    setSaving(true);
    try {
      await authAPI.changePassword(current, next);
      toast.success('Password alterada');
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (err) {
      const msg = errorMessage(err, 'Não foi possível alterar a password');
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl" data-testid="conta-page">
      <PageHeader title="Conta" description="Dados da sessão e alteração de password" />
      <Card>
        <CardHeader><CardTitle className="text-base">Utilizador</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          <div><span className="text-muted-foreground">Nome: </span>{user?.name || '—'}</div>
          <div><span className="text-muted-foreground">Email: </span>{user?.email || '—'}</div>
          <div><span className="text-muted-foreground">Perfil: </span>{user?.role || '—'}</div>
          <div><span className="text-muted-foreground">Oficina: </span>{user?.workshop_id ?? '—'}</div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Mudar password</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Field label="Password actual" htmlFor="cur">
              <Input id="cur" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
            </Field>
            <Field label="Nova password" htmlFor="new" hint={`Mínimo ${MIN_LEN} caracteres.`}>
              <Input id="new" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required />
            </Field>
            <Field label="Confirmar nova password" htmlFor="conf">
              <Input id="conf" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            </Field>
            {error && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>}
            <Button type="submit" disabled={saving || !current || !next || !confirm}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <KeyRound className="mr-2 h-4 w-4" />}
              Guardar password
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

export default Conta;
