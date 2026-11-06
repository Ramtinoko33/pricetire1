import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Field, NativeSelect } from './common';
import { suppliersAPI } from '@/lib/api';

export const ADAPTER_KEYS = [
  'mp24', 'prismanil', 'dispnal', 'sjose', 'euromais', 'soledad',
  'andres', 'aguesport', 'abtyres', 'tugapneus', 'intersprint', 'cruzeiro',
];

const EMPTY = { name: '', adapter_key: '', url_login: '', url_search: '', username: '', password: '', is_active: true };

// Formulário de fornecedor. A password é só de escrita: nunca é lida do servidor;
// em edição, campo vazio = manter a actual.
const SupplierForm = ({ open, onClose, onSubmit, initialData = null, isLoading = false }) => {
  const isEdit = Boolean(initialData?.id);
  const [formData, setFormData] = useState(EMPTY);
  const [adapters, setAdapters] = useState(() => ADAPTER_KEYS.map((key) => ({ key, name: key })));

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    suppliersAPI.adapters()
      .then(({ data }) => { if (!cancelled && Array.isArray(data) && data.length) setAdapters(data); })
      .catch(() => { /* mantém a lista estática */ });
    return () => { cancelled = true; };
  }, [open]);

  const selectedAdapter = adapters.find((a) => a.key === formData.adapter_key);

  useEffect(() => {
    if (open) {
      setFormData(initialData ? {
        name: initialData.name || '',
        adapter_key: initialData.adapter_key || '',
        url_login: initialData.url_login || '',
        url_search: initialData.url_search || '',
        username: initialData.username || '',
        password: '',
        is_active: initialData.is_active !== false,
      } : EMPTY);
    }
  }, [open, initialData]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData((f) => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const payload = { ...formData, adapter_key: formData.adapter_key || null };
    if (isEdit && !payload.password) delete payload.password;
    onSubmit(payload);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-[520px] max-h-[90vh] overflow-y-auto" data-testid="supplier-form-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Editar ${initialData.name}` : 'Adicionar fornecedor'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Field label="Nome *" htmlFor="name">
            <Input id="name" name="name" value={formData.name} onChange={handleChange} required data-testid="supplier-name-input" />
          </Field>
          <Field
            label="Conector (adapter_key)"
            htmlFor="adapter_key"
            hint={selectedAdapter?.notes
              ? `${selectedAdapter.notes}${selectedAdapter.brand_aware ? ' · pesquisa por marca' : ''}`
              : 'Define que scraper é usado para este fornecedor.'}
          >
            <NativeSelect id="adapter_key" name="adapter_key" value={formData.adapter_key} onChange={handleChange} data-testid="supplier-adapter-select">
              <option value="">— sem conector —</option>
              {adapters.map((a) => <option key={a.key} value={a.key}>{a.name && a.name !== a.key ? `${a.name} (${a.key})` : a.key}</option>)}
              {formData.adapter_key && !adapters.some((a) => a.key === formData.adapter_key) && (
                <option value={formData.adapter_key}>{formData.adapter_key} (desconhecido)</option>
              )}
            </NativeSelect>
          </Field>
          <Field label="URL login" htmlFor="url_login">
            <Input id="url_login" name="url_login" type="url" value={formData.url_login} onChange={handleChange} />
          </Field>
          <Field label="URL pesquisa" htmlFor="url_search">
            <Input id="url_search" name="url_search" type="url" value={formData.url_search} onChange={handleChange} />
          </Field>
          <Field label="Utilizador" htmlFor="username">
            <Input id="username" name="username" autoComplete="off" value={formData.username} onChange={handleChange} data-testid="supplier-username-input" />
          </Field>
          <Field
            label="Password"
            htmlFor="password"
            hint={isEdit
              ? (initialData?.has_password ? 'Há uma password guardada. Deixe vazio para a manter.' : 'Sem password guardada.')
              : 'Guardada encriptada no servidor; nunca é mostrada.'}
          >
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              value={formData.password}
              onChange={handleChange}
              placeholder={isEdit && initialData?.has_password ? '•••••••• (manter)' : ''}
              data-testid="supplier-password-input"
            />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" name="is_active" checked={formData.is_active} onChange={handleChange} /> Activo (incluído nas recolhas)
          </label>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>Cancelar</Button>
            <Button type="submit" disabled={isLoading} data-testid="supplier-submit-btn">
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEdit ? 'Guardar' : 'Adicionar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default SupplierForm;
