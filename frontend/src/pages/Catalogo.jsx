import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, FileUp, Loader2, Pencil, Plus, Power, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { catalogAPI, downloadBlob, suppliersAPI } from '@/lib/api';
import {
  errorMessage, formatDate, formatDateTime, formatLoadSpeed, formatPct, formatPrice, parseSize,
} from '@/lib/format';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ConfirmDialog, EmptyState, ErrorState, Field, NativeSelect, PageHeader, TableSkeleton } from '@/components/common';
import { ComparisonStatusBadge, OfferFlags, StaleBadge, ToneBadge, WithTooltip } from '@/components/badges';

const EMPTY_ITEM = {
  reference: '', description: '', size: '', brand: '', model: '', load_index_1: '', load_index_2: '',
  speed_index: '', xl: '', runflat: '', homologation: '', season: '', ean: '', manufacturer_ref: '',
  last_purchase_price: '', last_purchase_date: '', usual_supplier_id: '', category: '', active: true, notes: '',
};

const boolToTri = (v) => (v === true ? 'true' : v === false ? 'false' : '');
const triToBool = (v) => (v === 'true' ? true : v === 'false' ? false : null);
const toNum = (v) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(',', '.')));
const toInt = (v) => (v === '' || v === null || v === undefined ? null : parseInt(v, 10));
const nullIfEmpty = (v) => (v === '' || v === undefined ? null : v);

function itemToForm(item) {
  if (!item) return { ...EMPTY_ITEM };
  return {
    reference: item.reference || '',
    description: item.description || '',
    size: item.size_display || item.size_key || '',
    brand: item.brand || '',
    model: item.model || '',
    load_index_1: item.load_index_1 ?? '',
    load_index_2: item.load_index_2 ?? '',
    speed_index: item.speed_index || '',
    xl: boolToTri(item.xl),
    runflat: boolToTri(item.runflat),
    homologation: item.homologation || '',
    season: item.season || '',
    ean: item.ean || '',
    manufacturer_ref: item.manufacturer_ref || '',
    last_purchase_price: item.last_purchase_price ?? '',
    last_purchase_date: item.last_purchase_date ? String(item.last_purchase_date).slice(0, 10) : '',
    usual_supplier_id: item.usual_supplier_id ?? '',
    category: item.category || '',
    active: item.active !== false,
    notes: item.notes || '',
  };
}

export function formToPayload(form) {
  const size = parseSize(form.size);
  return {
    reference: form.reference.trim(),
    description: nullIfEmpty(form.description.trim()),
    size_display: size ? size.display : nullIfEmpty(form.size.trim()),
    size_key: size ? size.key : null,
    brand: nullIfEmpty(form.brand.trim().toUpperCase()),
    model: nullIfEmpty(form.model.trim()),
    load_index_1: toInt(form.load_index_1),
    load_index_2: toInt(form.load_index_2),
    speed_index: nullIfEmpty(form.speed_index.trim().toUpperCase()),
    xl: triToBool(form.xl),
    runflat: triToBool(form.runflat),
    homologation: nullIfEmpty(form.homologation.trim()),
    season: nullIfEmpty(form.season),
    ean: nullIfEmpty(form.ean.trim()),
    manufacturer_ref: nullIfEmpty(form.manufacturer_ref.trim()),
    last_purchase_price: toNum(form.last_purchase_price),
    last_purchase_date: nullIfEmpty(form.last_purchase_date),
    usual_supplier_id: nullIfEmpty(form.usual_supplier_id),
    category: nullIfEmpty(form.category.trim()),
    active: Boolean(form.active),
    notes: nullIfEmpty(form.notes.trim()),
  };
}

function TriSelect({ id, value, onChange }) {
  return (
    <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Desconhecido</option>
      <option value="true">Sim</option>
      <option value="false">Não</option>
    </NativeSelect>
  );
}

function ItemDialog({ open, initial, suppliers, onClose, onSaved }) {
  const isEdit = Boolean(initial?.id);
  const [form, setForm] = useState(EMPTY_ITEM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) { setForm(itemToForm(initial)); setError(''); }
  }, [open, initial]);

  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
  };

  const parsedSize = parseSize(form.size);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (!form.reference.trim()) { setError('A referência é obrigatória.'); return; }
    if (!parsedSize) { setError('Indique uma medida válida (ex.: 205/55R16).'); return; }
    setSaving(true);
    try {
      const payload = formToPayload(form);
      if (isEdit) await catalogAPI.update(initial.id, payload);
      else await catalogAPI.create(payload);
      toast.success(isEdit ? 'Referência actualizada' : 'Referência criada');
      onSaved();
      onClose();
    } catch (err) {
      setError(errorMessage(err, 'Erro ao guardar referência'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-[760px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Editar referência' : 'Nova referência'}</DialogTitle>
          <DialogDescription>Deixe em branco os atributos que não conhece; não são assumidos valores por defeito.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Field label="Referência *" htmlFor="c-ref" className="col-span-2 md:col-span-1"><Input id="c-ref" value={form.reference} onChange={set('reference')} required /></Field>
            <Field label="Medida *" htmlFor="c-size" hint={parsedSize ? parsedSize.display : form.size ? 'Medida não reconhecida' : undefined}>
              <Input id="c-size" value={form.size} onChange={set('size')} placeholder="205/55R16" required />
            </Field>
            <Field label="Marca" htmlFor="c-brand"><Input id="c-brand" value={form.brand} onChange={set('brand')} /></Field>
            <Field label="Modelo" htmlFor="c-model"><Input id="c-model" value={form.model} onChange={set('model')} /></Field>
            <Field label="Descrição" htmlFor="c-desc" className="col-span-2 md:col-span-4"><Input id="c-desc" value={form.description} onChange={set('description')} /></Field>
            <Field label="Carga" htmlFor="c-li1"><Input id="c-li1" inputMode="numeric" value={form.load_index_1} onChange={set('load_index_1')} placeholder="91" /></Field>
            <Field label="Carga 2 (dupla)" htmlFor="c-li2"><Input id="c-li2" inputMode="numeric" value={form.load_index_2} onChange={set('load_index_2')} placeholder="107" /></Field>
            <Field label="Velocidade" htmlFor="c-si"><Input id="c-si" value={form.speed_index} onChange={set('speed_index')} maxLength={2} placeholder="V" /></Field>
            <Field label="Estação" htmlFor="c-season">
              <NativeSelect id="c-season" value={form.season} onChange={set('season')}>
                <option value="">Desconhecida</option>
                <option value="summer">Verão</option>
                <option value="winter">Inverno</option>
                <option value="all_season">Todo o ano</option>
              </NativeSelect>
            </Field>
            <Field label="XL" htmlFor="c-xl"><TriSelect id="c-xl" value={form.xl} onChange={(v) => setForm((f) => ({ ...f, xl: v }))} /></Field>
            <Field label="RunFlat" htmlFor="c-rf"><TriSelect id="c-rf" value={form.runflat} onChange={(v) => setForm((f) => ({ ...f, runflat: v }))} /></Field>
            <Field label="Homologação" htmlFor="c-hom"><Input id="c-hom" value={form.homologation} onChange={set('homologation')} placeholder="MO, *, AO…" /></Field>
            <Field label="Categoria" htmlFor="c-cat"><Input id="c-cat" value={form.category} onChange={set('category')} /></Field>
            <Field label="EAN" htmlFor="c-ean"><Input id="c-ean" value={form.ean} onChange={set('ean')} /></Field>
            <Field label="Ref. fabricante" htmlFor="c-mref"><Input id="c-mref" value={form.manufacturer_ref} onChange={set('manufacturer_ref')} /></Field>
            <Field label="Último preço compra (€)" htmlFor="c-price"><Input id="c-price" inputMode="decimal" value={form.last_purchase_price} onChange={set('last_purchase_price')} /></Field>
            <Field label="Data última compra" htmlFor="c-pdate"><Input id="c-pdate" type="date" value={form.last_purchase_date} onChange={set('last_purchase_date')} /></Field>
            <Field label="Fornecedor habitual" htmlFor="c-sup" className="col-span-2">
              <NativeSelect id="c-sup" value={form.usual_supplier_id} onChange={set('usual_supplier_id')}>
                <option value="">—</option>
                {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Notas" htmlFor="c-notes" className="col-span-2 md:col-span-4"><Textarea id="c-notes" rows={2} value={form.notes} onChange={set('notes')} /></Field>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.active} onChange={set('active')} /> Activo (incluído na recolha e na comparação)</label>
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

function ImportDialog({ open, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState('upsert');
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) { setFile(null); setReport(null); setError(''); setMode('upsert'); }
  }, [open]);

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const { data } = await catalogAPI.import(file, mode);
      setReport(data);
      toast.success(`Importação concluída: ${data.created ?? 0} criadas, ${data.updated ?? 0} actualizadas`);
      onDone();
    } catch (err) {
      setError(errorMessage(err, 'Erro na importação'));
    } finally {
      setBusy(false);
    }
  };

  const template = async () => {
    try {
      const { data } = await catalogAPI.template();
      downloadBlob(data, 'modelo_catalogo.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao descarregar o modelo'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-[620px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Importar catálogo</DialogTitle>
          <DialogDescription>Ficheiro Excel (.xlsx) ou CSV com as colunas do modelo.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Button variant="link" className="px-0" onClick={template}><Download size={14} className="mr-1" /> Descarregar modelo</Button>
          <Input type="file" accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="catalog-file" />
          <Field label="Modo" htmlFor="imp-mode">
            <NativeSelect id="imp-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="upsert">Actualizar existentes e criar novas (pela referência)</option>
              <option value="append">Só acrescentar novas</option>
            </NativeSelect>
          </Field>
          {error && <ErrorState message={error} />}
          {report && (
            <div className="space-y-2" data-testid="import-report">
              <div className="flex flex-wrap gap-2">
                <ToneBadge tone="green">Criadas: {report.created ?? 0}</ToneBadge>
                <ToneBadge tone="blue">Actualizadas: {report.updated ?? 0}</ToneBadge>
                <ToneBadge tone={report.rejected?.length ? 'red' : 'slate'}>Rejeitadas: {report.rejected?.length ?? 0}</ToneBadge>
              </div>
              {report.rejected?.length > 0 && (
                <div className="max-h-60 overflow-auto border rounded-md">
                  <Table>
                    <TableHeader><TableRow><TableHead className="w-20">Linha</TableHead><TableHead>Motivo</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {report.rejected.map((r, i) => (
                        <TableRow key={i}><TableCell className="font-mono">{r.row}</TableCell><TableCell className="text-sm">{r.reason}</TableCell></TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
          <Button onClick={submit} disabled={!file || busy}>
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileUp className="mr-2 h-4 w-4" />}
            Importar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ItemsTab({ suppliers }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [active, setActive] = useState('');
  const [dialog, setDialog] = useState({ open: false, initial: null });
  const [importOpen, setImportOpen] = useState(false);
  const [toDelete, setToDelete] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await catalogAPI.getAll({ q: query, active });
      setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar o catálogo'));
    } finally {
      setLoading(false);
    }
  }, [query, active]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);

  const toggleActive = async (item) => {
    try {
      await catalogAPI.update(item.id, { ...formToPayload(itemToForm(item)), active: !item.active });
      toast.success(item.active ? 'Referência desactivada' : 'Referência activada');
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao actualizar'));
    }
  };

  const remove = async () => {
    const item = toDelete;
    setToDelete(null);
    try {
      await catalogAPI.delete(item.id);
      toast.success('Referência eliminada');
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao eliminar'));
    }
  };

  const supplierName = (id) => suppliers.find((s) => String(s.id) === String(id))?.name;

  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row gap-2 md:items-center md:justify-between">
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-2.5 text-muted-foreground" />
            <Input className="pl-8 sm:w-72" placeholder="Pesquisar referência, marca, medida…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <NativeSelect className="sm:w-40" value={active} onChange={(e) => setActive(e.target.value)} aria-label="Filtro de estado">
            <option value="">Todos</option>
            <option value="true">Activos</option>
            <option value="false">Inactivos</option>
          </NativeSelect>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setImportOpen(true)}><FileUp size={16} className="mr-2" /> Importar</Button>
          <Button onClick={() => setDialog({ open: true, initial: null })}><Plus size={16} className="mr-2" /> Nova referência</Button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={load} />}

      <Card>
        <CardContent className="p-0">
          {loading ? <TableSkeleton rows={6} cols={6} /> : items.length === 0 ? (
            <EmptyState
              title={query || active ? 'Nenhuma referência corresponde aos filtros' : 'Catálogo vazio'}
              description="Adicione referências manualmente ou importe um ficheiro Excel/CSV a partir do modelo."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Referência</TableHead>
                  <TableHead>Medida</TableHead>
                  <TableHead>Marca / modelo</TableHead>
                  <TableHead>Índice</TableHead>
                  <TableHead>Características</TableHead>
                  <TableHead className="text-right">Último preço</TableHead>
                  <TableHead>Fornecedor habitual</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acções</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((it) => (
                  <TableRow key={it.id} className={it.active === false ? 'opacity-60' : undefined}>
                    <TableCell className="font-mono text-xs whitespace-nowrap">{it.reference}</TableCell>
                    <TableCell className="font-mono text-xs whitespace-nowrap">{it.size_display || it.size_key}</TableCell>
                    <TableCell className="min-w-[160px]">
                      <WithTooltip content={it.description}>
                        <span className="cursor-help">{[it.brand, it.model].filter(Boolean).join(' ') || it.description || '—'}</span>
                      </WithTooltip>
                      {it.category && <div className="text-xs text-muted-foreground">{it.category}</div>}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{formatLoadSpeed(it)}</TableCell>
                    <TableCell><OfferFlags offer={it} /></TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      <div className="font-mono">{formatPrice(it.last_purchase_price)}</div>
                      <div className="text-xs text-muted-foreground">{formatDate(it.last_purchase_date)}</div>
                    </TableCell>
                    <TableCell className="text-sm">{supplierName(it.usual_supplier_id) || '—'}</TableCell>
                    <TableCell>{it.active === false ? <ToneBadge>Inactivo</ToneBadge> : <ToneBadge tone="green">Activo</ToneBadge>}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button variant="outline" size="sm" onClick={() => setDialog({ open: true, initial: it })} aria-label="Editar"><Pencil size={14} /></Button>
                        <Button variant="outline" size="sm" onClick={() => toggleActive(it)} aria-label={it.active ? 'Desactivar' : 'Activar'} title={it.active ? 'Desactivar' : 'Activar'}>
                          <Power size={14} className={it.active ? 'text-green-500' : 'text-muted-foreground'} />
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setToDelete(it)} aria-label="Eliminar"><Trash2 size={14} className="text-red-600" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ItemDialog open={dialog.open} initial={dialog.initial} suppliers={suppliers} onClose={() => setDialog({ open: false, initial: null })} onSaved={load} />
      <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} onDone={load} />
      <ConfirmDialog
        open={Boolean(toDelete)}
        onOpenChange={(v) => !v && setToDelete(null)}
        title="Eliminar referência?"
        description={`A referência ${toDelete?.reference || ''} será eliminada do catálogo. Para a manter sem a monitorizar, desactive-a em vez de eliminar.`}
        confirmLabel="Eliminar"
        destructive
        onConfirm={remove}
      />
    </div>
  );
}

function ComparisonTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [onlySavings, setOnlySavings] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await catalogAPI.comparison(onlySavings);
      setRows(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar a comparação'));
    } finally {
      setLoading(false);
    }
  }, [onlySavings]);

  useEffect(() => { load(); }, [load]);

  const counts = useMemo(() => rows.reduce((acc, r) => { acc[r.status] = (acc[r.status] || 0) + 1; return acc; }, {}), [rows]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlySavings} onChange={(e) => setOnlySavings(e.target.checked)} data-testid="only-savings" /> Só oportunidades
        </label>
        <div className="flex flex-wrap gap-1">
          {Object.entries(counts).map(([s, n]) => (
            <span key={s} className="inline-flex items-center gap-1 text-xs"><ComparisonStatusBadge status={s} /> {n}</span>
          ))}
        </div>
      </div>
      {error && <ErrorState message={error} onRetry={load} />}
      <Card>
        <CardContent className="p-0">
          {loading ? <TableSkeleton rows={6} cols={7} /> : rows.length === 0 ? (
            <EmptyState
              title={onlySavings ? 'Sem oportunidades de poupança' : 'Sem dados de comparação'}
              description="A comparação usa o último preço de compra de cada referência activa e os preços exactos recolhidos nos fornecedores."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Referência</TableHead>
                  <TableHead className="text-right">Preço de referência</TableHead>
                  <TableHead className="text-right">Melhor preço exacto</TableHead>
                  <TableHead>Fornecedor</TableHead>
                  <TableHead className="text-right">Diferença</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Alternativas</TableHead>
                  <TableHead className="text-right">Info insuf.</TableHead>
                  <TableHead>Preços de</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => {
                  const it = r.item || {};
                  const isSaving = r.status === 'saving';
                  const showDiff = r.best_exact && r.saving_eur !== null && r.saving_eur !== undefined;
                  return (
                    <TableRow key={it.id ?? it.reference} className={isSaving ? 'bg-emerald-50 dark:bg-emerald-500/10' : undefined}>
                      <TableCell className="min-w-[180px]">
                        <div className="font-mono text-xs">{it.reference}</div>
                        <div className="text-sm">{[it.brand, it.model].filter(Boolean).join(' ')} <span className="font-mono text-xs">{it.size_display || it.size_key} {formatLoadSpeed(it)}</span></div>
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        <div className="font-mono">{formatPrice(r.reference_price)}</div>
                        <div className="text-xs text-muted-foreground">{formatDate(r.reference_date)}</div>
                      </TableCell>
                      <TableCell className="text-right font-mono whitespace-nowrap">
                        {r.best_exact ? formatPrice(r.best_exact.price, r.best_exact.currency) : '—'}
                        {r.best_exact?.fresh === false && <div className="mt-1"><StaleBadge /></div>}
                      </TableCell>
                      <TableCell className="text-sm whitespace-nowrap">{r.best_exact?.supplier_name || '—'}</TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        {showDiff ? (
                          <span className={isSaving ? 'text-emerald-700 dark:text-emerald-400 font-semibold' : 'text-muted-foreground'}>
                            {formatPrice(r.saving_eur)} <span className="text-xs">({formatPct(r.saving_pct)})</span>
                          </span>
                        ) : '—'}
                      </TableCell>
                      <TableCell><ComparisonStatusBadge status={r.status} /></TableCell>
                      <TableCell className="text-right">{r.alternatives_count ?? 0}</TableCell>
                      <TableCell className="text-right">{r.insufficient_count ?? 0}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">{formatDateTime(r.prices_at)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        A diferença é calculada apenas contra ofertas com correspondência exacta (preço de referência − melhor preço exacto). As alternativas são contadas mas não entram no cálculo.
      </p>
    </div>
  );
}

const Catalogo = () => {
  const [suppliers, setSuppliers] = useState([]);

  useEffect(() => {
    suppliersAPI.getAll().then(({ data }) => setSuppliers(Array.isArray(data) ? data : [])).catch(() => {});
  }, []);

  return (
    <div className="space-y-6" data-testid="catalogo-page">
      <PageHeader eyebrow="Referências habituais" title="Catálogo" description="Referências compradas habitualmente, monitorizadas e comparadas com os preços dos fornecedores." />
      <Tabs defaultValue="items">
        <TabsList>
          <TabsTrigger value="items">Referências</TabsTrigger>
          <TabsTrigger value="comparison">Comparação</TabsTrigger>
        </TabsList>
        <TabsContent value="items" className="mt-4"><ItemsTab suppliers={suppliers} /></TabsContent>
        <TabsContent value="comparison" className="mt-4"><ComparisonTab /></TabsContent>
      </Tabs>
    </div>
  );
};

export default Catalogo;
