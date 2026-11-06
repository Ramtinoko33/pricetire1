import React, { useCallback, useEffect, useState } from 'react';
import { Copy, KeyRound, Loader2, Pencil, Plus, Trash2, UserPlus } from 'lucide-react';
import { toast } from 'sonner';
import { apiKeysAPI, usersAPI } from '@/lib/api';
import { errorMessage, formatDateTime } from '@/lib/format';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ConfirmDialog, EmptyState, ErrorState, Field, NativeSelect, PageHeader, TableSkeleton } from '@/components/common';
import { ToneBadge } from '@/components/badges';

const ROLES = [
  { value: 'admin', label: 'Administrador' },
  { value: 'user', label: 'Utilizador' },
];

function UserDialog({ open, onClose, initial, onSaved }) {
  const isEdit = Boolean(initial?.id);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({
        email: initial?.email || '',
        name: initial?.name || '',
        role: initial?.role || 'user',
        password: '',
        is_active: initial?.is_active ?? true,
      });
    }
  }, [open, initial]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { name: form.name, role: form.role, is_active: form.is_active };
      if (form.password) payload.password = form.password;
      if (isEdit) {
        await usersAPI.update(initial.id, payload);
        toast.success('Utilizador actualizado');
      } else {
        await usersAPI.create({ ...payload, email: form.email.trim(), password: form.password });
        toast.success('Utilizador criado');
      }
      onSaved();
      onClose();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao guardar utilizador'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar utilizador' : 'Novo utilizador'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Email" htmlFor="u-email">
            <Input id="u-email" type="email" value={form.email || ''} onChange={set('email')} required disabled={isEdit} />
          </Field>
          <Field label="Nome" htmlFor="u-name">
            <Input id="u-name" value={form.name || ''} onChange={set('name')} required />
          </Field>
          <Field label="Perfil" htmlFor="u-role">
            <NativeSelect id="u-role" value={form.role || 'user'} onChange={set('role')}>
              {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </NativeSelect>
          </Field>
          <Field
            label={isEdit ? 'Nova password (opcional)' : 'Password inicial'}
            htmlFor="u-pass"
            hint={isEdit ? 'Deixe vazio para manter a password actual.' : 'Mínimo 8 caracteres.'}
          >
            <Input id="u-pass" type="password" autoComplete="new-password" value={form.password || ''} onChange={set('password')} required={!isEdit} minLength={isEdit ? undefined : 8} />
          </Field>
          {isEdit && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={Boolean(form.is_active)} onChange={set('is_active')} /> Conta activa
            </label>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>Cancelar</Button>
            <Button type="submit" disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Guardar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function UsersTab() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState({ open: false, initial: null });

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await usersAPI.getAll();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar utilizadores'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setDialog({ open: true, initial: null })}>
          <UserPlus size={16} className="mr-2" /> Novo utilizador
        </Button>
      </div>
      {error && <ErrorState message={error} onRetry={load} />}
      <Card>
        <CardContent className="p-0">
          {loading ? <TableSkeleton rows={3} cols={4} /> : users.length === 0 ? (
            <EmptyState title="Sem utilizadores" description="Crie o primeiro utilizador com o botão acima." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Perfil</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acções</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">{u.name || '—'}</TableCell>
                    <TableCell className="text-sm">{u.email}</TableCell>
                    <TableCell>{u.role === 'admin' ? <ToneBadge tone="purple">Administrador</ToneBadge> : <ToneBadge>Utilizador</ToneBadge>}</TableCell>
                    <TableCell>{u.is_active === false ? <ToneBadge tone="red">Inactiva</ToneBadge> : <ToneBadge tone="green">Activa</ToneBadge>}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" onClick={() => setDialog({ open: true, initial: u })} aria-label="Editar">
                        <Pencil size={14} />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <UserDialog open={dialog.open} initial={dialog.initial} onClose={() => setDialog({ open: false, initial: null })} onSaved={load} />
    </div>
  );
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('Copiado para a área de transferência');
  } catch {
    toast.error('Não foi possível copiar. Seleccione e copie manualmente.');
  }
}

function ApiKeysTab() {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(null);
  const [toDelete, setToDelete] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await apiKeysAPI.getAll();
      setKeys(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar API keys'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      const { data } = await apiKeysAPI.create({ name: name.trim() });
      const secret = data?.key ?? data?.api_key ?? data?.token ?? null;
      setCreated({ name: data?.name || name.trim(), key: secret });
      setName('');
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao criar API key'));
    } finally {
      setCreating(false);
    }
  };

  const remove = async () => {
    const k = toDelete;
    setToDelete(null);
    try {
      await apiKeysAPI.delete(k.id);
      toast.success('API key revogada');
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao revogar API key'));
    }
  };

  return (
    <div className="space-y-4">
      <form onSubmit={create} className="flex flex-col sm:flex-row gap-2">
        <Input placeholder="Nome da integração (ex.: ERP oficina)" value={name} onChange={(e) => setName(e.target.value)} className="sm:max-w-sm" />
        <Button type="submit" disabled={creating || !name.trim()}>
          {creating ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Plus size={16} className="mr-2" />}
          Criar API key
        </Button>
      </form>
      {error && <ErrorState message={error} onRetry={load} />}
      <Card>
        <CardContent className="p-0">
          {loading ? <TableSkeleton rows={3} cols={4} /> : keys.length === 0 ? (
            <EmptyState title="Sem API keys" description="As integrações externas autenticam-se com o cabeçalho X-API-Key." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Prefixo</TableHead>
                  <TableHead>Criada</TableHead>
                  <TableHead>Última utilização</TableHead>
                  <TableHead className="text-right">Acções</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.map((k) => (
                  <TableRow key={k.id}>
                    <TableCell className="font-medium">{k.name || '—'}</TableCell>
                    <TableCell className="font-mono text-xs">{k.prefix ? `${k.prefix}…` : '—'}</TableCell>
                    <TableCell className="text-xs">{formatDateTime(k.created_at)}</TableCell>
                    <TableCell className="text-xs">{formatDateTime(k.last_used_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="outline" size="sm" onClick={() => setToDelete(k)} aria-label="Revogar">
                        <Trash2 size={14} className="text-red-600" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={Boolean(created)} onOpenChange={(v) => !v && setCreated(null)}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle><KeyRound className="inline mr-2" size={18} />API key criada: {created?.name}</DialogTitle>
            <DialogDescription>
              Esta chave só é mostrada agora. Copie-a e guarde-a num local seguro; depois de fechar esta janela não será possível vê-la novamente.
            </DialogDescription>
          </DialogHeader>
          {created?.key ? (
            <div className="flex gap-2">
              <Input readOnly value={created.key} className="font-mono text-xs" onFocus={(e) => e.target.select()} data-testid="api-key-value" />
              <Button type="button" variant="outline" onClick={() => copyText(created.key)}>
                <Copy size={14} className="mr-1" /> Copiar
              </Button>
            </div>
          ) : (
            <p className="text-sm text-red-600">O servidor não devolveu a chave na resposta.</p>
          )}
          <DialogFooter>
            <Button onClick={() => setCreated(null)}>Já guardei a chave</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(toDelete)}
        onOpenChange={(v) => !v && setToDelete(null)}
        title="Revogar API key?"
        description={`A integração "${toDelete?.name || ''}" deixa de ter acesso imediatamente.`}
        confirmLabel="Revogar"
        destructive
        onConfirm={remove}
      />
    </div>
  );
}

const Admin = () => (
  <div className="space-y-6" data-testid="admin-page">
    <PageHeader title="Administração" description="Utilizadores e chaves de API" />
    <Tabs defaultValue="users">
      <TabsList>
        <TabsTrigger value="users">Utilizadores</TabsTrigger>
        <TabsTrigger value="keys">API keys</TabsTrigger>
      </TabsList>
      <TabsContent value="users" className="mt-4"><UsersTab /></TabsContent>
      <TabsContent value="keys" className="mt-4"><ApiKeysTab /></TabsContent>
    </Tabs>
  </div>
);

export default Admin;
