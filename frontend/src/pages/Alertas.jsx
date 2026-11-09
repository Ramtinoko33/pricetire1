import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Mail, Pencil, Play, Plus, Power, Save, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { alertsAPI, catalogAPI } from '@/lib/api';
import { errorMessage, formatDateTime, formatPct, formatPrice } from '@/lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ConfirmDialog, EmptyState, ErrorState, Field, NativeSelect, PageHeader, TableSkeleton } from '@/components/common';
import { ToneBadge, WithTooltip } from '@/components/badges';

const SCOPES = {
  all: 'Todas as referências',
  item: 'Referência',
  brand: 'Marca',
  category: 'Categoria',
};

const EMPTY_RULE = {
  name: '', scope: 'all', catalog_item_id: '', brand: '', category: '',
  min_saving_pct: '', min_saving_eur: '', email_to: '', active: true,
};

const toNum = (v) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(',', '.')));

function rulePayload(form) {
  return {
    name: form.name.trim(),
    scope: form.scope,
    catalog_item_id: form.scope === 'item' ? (form.catalog_item_id || null) : null,
    brand: form.scope === 'brand' ? (form.brand.trim().toUpperCase() || null) : null,
    category: form.scope === 'category' ? (form.category.trim() || null) : null,
    min_saving_pct: toNum(form.min_saving_pct),
    min_saving_eur: toNum(form.min_saving_eur),
    email_to: form.email_to.trim() || null,
    active: Boolean(form.active),
  };
}

function ruleToForm(r) {
  if (!r) return { ...EMPTY_RULE };
  return {
    name: r.name || '',
    scope: r.scope || 'all',
    catalog_item_id: r.catalog_item_id ?? '',
    brand: r.brand || '',
    category: r.category || '',
    min_saving_pct: r.min_saving_pct ?? '',
    min_saving_eur: r.min_saving_eur ?? '',
    email_to: r.email_to || '',
    active: r.active !== false,
  };
}

function RuleDialog({ open, initial, items, onClose, onSaved }) {
  const isEdit = Boolean(initial?.id);
  const [form, setForm] = useState(EMPTY_RULE);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { if (open) { setForm(ruleToForm(initial)); setError(''); } }, [open, initial]);

  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.name.trim()) { setError('Indique um nome.'); return; }
    if (form.scope === 'item' && !form.catalog_item_id) { setError('Escolha a referência do catálogo.'); return; }
    if (form.scope === 'brand' && !form.brand.trim()) { setError('Indique a marca.'); return; }
    if (form.scope === 'category' && !form.category.trim()) { setError('Indique a categoria.'); return; }
    if (form.min_saving_pct === '' && form.min_saving_eur === '') { setError('Defina pelo menos um limiar (% ou €).'); return; }
    setSaving(true);
    try {
      const payload = rulePayload(form);
      if (isEdit) await alertsAPI.updateRule(initial.id, payload);
      else await alertsAPI.createRule(payload);
      toast.success('Regra guardada');
      onSaved();
      onClose();
    } catch (err) {
      setError(errorMessage(err, 'Erro ao guardar regra'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-[560px] max-h-[90vh] overflow-y-auto">
        <DialogHeader><DialogTitle>{isEdit ? 'Editar regra' : 'Nova regra de alerta'}</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Nome" htmlFor="r-name"><Input id="r-name" value={form.name} onChange={set('name')} required /></Field>
          <Field label="Âmbito" htmlFor="r-scope">
            <NativeSelect id="r-scope" value={form.scope} onChange={set('scope')}>
              {Object.entries(SCOPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect>
          </Field>
          {form.scope === 'item' && (
            <Field label="Referência do catálogo" htmlFor="r-item">
              <NativeSelect id="r-item" value={form.catalog_item_id} onChange={set('catalog_item_id')}>
                <option value="">— escolher —</option>
                {items.map((it) => (
                  <option key={it.id} value={it.id}>{it.reference} · {[it.brand, it.model, it.size_display].filter(Boolean).join(' ')}</option>
                ))}
              </NativeSelect>
            </Field>
          )}
          {form.scope === 'brand' && <Field label="Marca" htmlFor="r-brand"><Input id="r-brand" value={form.brand} onChange={set('brand')} /></Field>}
          {form.scope === 'category' && <Field label="Categoria" htmlFor="r-cat"><Input id="r-cat" value={form.category} onChange={set('category')} /></Field>}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Poupança mínima (%)" htmlFor="r-pct"><Input id="r-pct" inputMode="decimal" value={form.min_saving_pct} onChange={set('min_saving_pct')} /></Field>
            <Field label="Poupança mínima (€)" htmlFor="r-eur"><Input id="r-eur" inputMode="decimal" value={form.min_saving_eur} onChange={set('min_saving_eur')} /></Field>
          </div>
          <Field label="Email de destino" htmlFor="r-email" hint="Vazio = endereço por defeito da oficina (se configurado no servidor).">
            <Input id="r-email" type="email" value={form.email_to} onChange={set('email_to')} />
          </Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.active} onChange={set('active')} /> Regra activa</label>
          <p className="text-xs text-muted-foreground">Os alertas só são gerados para ofertas com correspondência exacta face à referência do catálogo.</p>
          {error && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>Cancelar</Button>
            <Button type="submit" disabled={saving}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Guardar</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RulesTab() {
  const [rules, setRules] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState({ open: false, initial: null });
  const [toDelete, setToDelete] = useState(null);
  const [testEmail, setTestEmail] = useState('');
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await alertsAPI.getRules();
      setRules(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar regras'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    catalogAPI.getAll({ active: true }).then(({ data }) => setItems(Array.isArray(data) ? data : [])).catch(() => {});
  }, [load]);

  const toggle = async (r) => {
    try {
      await alertsAPI.updateRule(r.id, { ...rulePayload(ruleToForm(r)), active: !r.active });
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao actualizar regra'));
    }
  };

  const remove = async () => {
    const r = toDelete;
    setToDelete(null);
    try {
      await alertsAPI.deleteRule(r.id);
      toast.success('Regra eliminada');
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao eliminar regra'));
    }
  };

  const sendTest = async (e) => {
    e.preventDefault();
    if (!testEmail.trim()) return;
    setSending(true);
    try {
      await alertsAPI.testEmail(testEmail.trim());
      toast.success(`E-mail de teste enviado para ${testEmail.trim()}`);
    } catch (err) {
      toast.error(errorMessage(err, 'Falha no envio do e-mail de teste'));
    } finally {
      setSending(false);
    }
  };

  const scopeText = (r) => {
    if (r.scope === 'item') {
      const it = items.find((i) => String(i.id) === String(r.catalog_item_id));
      return `Referência ${it?.reference || r.catalog_item_id || ''}`;
    }
    if (r.scope === 'brand') return `Marca ${r.brand || ''}`;
    if (r.scope === 'category') return `Categoria ${r.category || ''}`;
    return SCOPES.all;
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row gap-3 md:items-end md:justify-between">
        <form onSubmit={sendTest} className="flex flex-col sm:flex-row gap-2 sm:items-end">
          <Field label="Testar envio" htmlFor="test-email">
            <Input id="test-email" type="email" placeholder="email@exemplo.pt" value={testEmail} onChange={(e) => setTestEmail(e.target.value)} className="sm:w-64" />
          </Field>
          <Button type="submit" variant="outline" disabled={sending || !testEmail.trim()}>
            {sending ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Mail size={16} className="mr-2" />}
            Enviar e-mail de teste
          </Button>
        </form>
        <Button onClick={() => setDialog({ open: true, initial: null })}><Plus size={16} className="mr-2" /> Nova regra</Button>
      </div>
      {error && <ErrorState message={error} onRetry={load} />}
      <Card>
        <CardContent className="p-0">
          {loading ? <TableSkeleton rows={3} cols={5} /> : rules.length === 0 ? (
            <EmptyState title="Sem regras de alerta" description="Crie uma regra para ser avisado por e-mail quando surgir um preço exacto abaixo do seu preço de referência." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Âmbito</TableHead>
                  <TableHead className="text-right">Limiar %</TableHead>
                  <TableHead className="text-right">Limiar €</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acções</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rules.map((r) => (
                  <TableRow key={r.id} className={r.active === false ? 'opacity-60' : undefined}>
                    <TableCell className="font-medium">{r.name}</TableCell>
                    <TableCell className="text-sm">{scopeText(r)}</TableCell>
                    <TableCell className="text-right">{r.min_saving_pct != null ? formatPct(r.min_saving_pct) : '—'}</TableCell>
                    <TableCell className="text-right">{r.min_saving_eur != null ? formatPrice(r.min_saving_eur) : '—'}</TableCell>
                    <TableCell className="text-sm">{r.email_to || '—'}</TableCell>
                    <TableCell>{r.active === false ? <ToneBadge>Inactiva</ToneBadge> : <ToneBadge tone="green">Activa</ToneBadge>}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button variant="outline" size="sm" onClick={() => setDialog({ open: true, initial: r })} aria-label="Editar"><Pencil size={14} /></Button>
                        <Button variant="outline" size="sm" onClick={() => toggle(r)} aria-label={r.active ? 'Desactivar' : 'Activar'}><Power size={14} className={r.active ? 'text-green-500' : 'text-muted-foreground'} /></Button>
                        <Button variant="outline" size="sm" onClick={() => setToDelete(r)} aria-label="Eliminar"><Trash2 size={14} className="text-red-600" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <RuleDialog open={dialog.open} initial={dialog.initial} items={items} onClose={() => setDialog({ open: false, initial: null })} onSaved={load} />
      <ConfirmDialog
        open={Boolean(toDelete)}
        onOpenChange={(v) => !v && setToDelete(null)}
        title="Eliminar regra?"
        description={`A regra "${toDelete?.name || ''}" deixa de gerar alertas.`}
        confirmLabel="Eliminar"
        destructive
        onConfirm={remove}
      />
    </div>
  );
}

function EventsTab() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [evaluating, setEvaluating] = useState(false);

  const evaluate = async () => {
    setEvaluating(true);
    try {
      const { data } = await alertsAPI.evaluate();
      const n = data?.created ?? data?.events ?? data?.new_events;
      toast.success(typeof n === 'number' ? `Avaliação concluída: ${n} novo(s) alerta(s)` : 'Avaliação concluída');
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao avaliar regras'));
    } finally {
      setEvaluating(false);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await alertsAPI.events(200);
      setEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar eventos'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="outline" onClick={evaluate} disabled={evaluating} data-testid="evaluate-alerts">
          {evaluating ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Play size={16} className="mr-2" />}
          Avaliar agora
        </Button>
      </div>
      {error && <ErrorState message={error} onRetry={load} />}
      <Card>
        <CardContent className="p-0">
          {loading ? <TableSkeleton rows={5} cols={7} /> : events.length === 0 ? (
            <EmptyState title="Sem alertas registados" description="Os eventos aparecem aqui quando uma recolha encontra um preço exacto que cumpre uma regra activa." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Produto</TableHead>
                  <TableHead>Regra</TableHead>
                  <TableHead>Fornecedor</TableHead>
                  <TableHead className="text-right">Preço anterior</TableHead>
                  <TableHead className="text-right">Preço encontrado</TableHead>
                  <TableHead className="text-right">Poupança</TableHead>
                  <TableHead>Recolha</TableHead>
                  <TableHead>Notificação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((ev) => (
                  <TableRow key={ev.id}>
                    <TableCell className="min-w-[180px]">
                      <div className="font-mono text-xs">{ev.item?.reference}</div>
                      <div className="text-sm">{[ev.item?.brand, ev.item?.model].filter(Boolean).join(' ')} <span className="font-mono text-xs">{ev.item?.size_key}</span></div>
                    </TableCell>
                    <TableCell className="text-sm">{ev.rule_name || '—'}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap">{ev.supplier_name || '—'}</TableCell>
                    <TableCell className="text-right font-mono">{formatPrice(ev.reference_price)}</TableCell>
                    <TableCell className="text-right font-mono">{formatPrice(ev.offer_price)}</TableCell>
                    <TableCell className="text-right whitespace-nowrap text-emerald-700 dark:text-emerald-400 font-semibold">
                      {formatPrice(ev.saving_eur)} <span className="text-xs">({formatPct(ev.saving_pct)})</span>
                    </TableCell>
                    <TableCell className="text-xs whitespace-nowrap">{formatDateTime(ev.observed_at)}</TableCell>
                    <TableCell>
                      {ev.notify_error ? (
                        <WithTooltip content={ev.notify_error}><span><ToneBadge tone="red" title={ev.notify_error}>Falhou</ToneBadge></span></WithTooltip>
                      ) : ev.notified_at ? (
                        <ToneBadge tone="green" title={formatDateTime(ev.notified_at)}>Enviado</ToneBadge>
                      ) : (
                        <ToneBadge>Pendente</ToneBadge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const Alertas = () => (
  <div className="space-y-6" data-testid="alertas-page">
    <PageHeader title="Alertas" description="Aviso por e-mail quando um fornecedor tem uma referência do catálogo abaixo do seu preço de referência." />
    <Tabs defaultValue="events">
      <TabsList className="flex-wrap h-auto">
        <TabsTrigger value="events">Eventos</TabsTrigger>
        <TabsTrigger value="rules">Regras</TabsTrigger>
      </TabsList>
      <TabsContent value="events" className="mt-4"><EventsTab /></TabsContent>
      <TabsContent value="rules" className="mt-4"><RulesTab /></TabsContent>
    </Tabs>
  </div>
);

export default Alertas;
