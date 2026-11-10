import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Clock, Loader2, Play, Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import { monitorAPI } from '@/lib/api';
import { errorMessage, formatAge, formatDateTime } from '@/lib/format';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ConfirmDialog, EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/common';
import { cn } from '@/lib/utils';

function TimesEditor({ category, onSaved }) {
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);
  const save = async (times) => {
    setSaving(true);
    try {
      await monitorAPI.updateCategory(category.id, { times });
      toast.success(`Horários de ${category.name} actualizados`);
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao gravar os horários'));
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {category.times.map((t) => (
        <span key={t} className="inline-flex items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-xs font-mono">
          <Clock size={11} className="text-muted-foreground" /> {t}
          <button type="button" aria-label={`Retirar ${t}`} disabled={saving} onClick={() => save(category.times.filter((x) => x !== t))} className="text-muted-foreground hover:text-foreground">
            <X size={11} />
          </button>
        </span>
      ))}
      <form
        className="inline-flex items-center gap-1"
        onSubmit={(e) => { e.preventDefault(); if (value) { save([...category.times, value]); setValue(''); } }}
      >
        <input type="time" value={value} onChange={(e) => setValue(e.target.value)} aria-label="Novo horário" className="h-7 rounded-md border bg-background px-1.5 text-xs" />
        <button type="submit" disabled={!value || saving} className="inline-flex items-center gap-0.5 rounded-md border px-1.5 h-7 text-xs hover:bg-muted disabled:opacity-50">
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Horário
        </button>
      </form>
    </div>
  );
}

function SizeChip({ size, onDelete }) {
  return (
    <div
      className={cn('group inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs',
        size.recognized ? 'bg-background' : 'bg-amber-50 border-amber-300 dark:bg-amber-500/10 dark:border-amber-500/40')}
      title={size.recognized
        ? `${size.offers} oferta(s)${size.last_success_at ? ` · última recolha ${formatDateTime(size.last_success_at)}` : ' · ainda sem recolha'}`
        : 'Formato ainda não reconhecido pela aplicação: fica guardada, mas não é recolhida.'}
      data-testid="monitor-size"
    >
      <span className="font-mono font-medium">{size.label}</span>
      {size.recognized
        ? <span className="text-muted-foreground">{size.offers}</span>
        : <span className="text-amber-700 dark:text-amber-300">não reconhecida</span>}
      {!size.dynamic && (
        <button type="button" aria-label={`Retirar ${size.label}`} onClick={() => onDelete(size)} className="text-muted-foreground opacity-50 group-hover:opacity-100 hover:text-red-600">
          <X size={12} />
        </button>
      )}
    </div>
  );
}

function SupplierToggles({ category, suppliers, onSaved }) {
  const [saving, setSaving] = useState('');
  const excluded = new Set(category.excluded_suppliers || []);
  const toggle = async (name) => {
    const next = excluded.has(name) ? [...excluded].filter((x) => x !== name) : [...excluded, name];
    setSaving(name);
    try {
      await monitorAPI.updateCategory(category.id, { excluded_suppliers: next });
      toast.success(`${category.name}: ${excluded.has(name) ? 'volta a pesquisar' : 'deixa de pesquisar'} em ${name}`);
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao gravar os fornecedores'));
    } finally {
      setSaving('');
    }
  };
  return (
    <div className="space-y-1.5" data-testid="monitor-suppliers">
      <p className="text-xs font-medium">Fornecedores onde esta categoria é pesquisada <span className="font-normal text-muted-foreground">(desligue os que não têm estes pneus, para não fazer pesquisas inúteis)</span></p>
      <div className="flex flex-wrap gap-1.5">
        {suppliers.map((name) => {
          const on = !excluded.has(name);
          return (
            <button
              key={name}
              type="button"
              onClick={() => toggle(name)}
              disabled={Boolean(saving)}
              aria-pressed={on}
              className={cn('inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs transition-colors',
                on ? 'bg-emerald-50 border-emerald-300 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200 dark:border-emerald-500/40'
                  : 'bg-muted text-muted-foreground line-through')}
            >
              {saving === name && <Loader2 size={11} className="animate-spin" />} {name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function CategoryCard({ category, suppliers, onChanged, onDelete }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [adding, setAdding] = useState(false);
  const [running, setRunning] = useState(false);
  const recognized = category.sizes.filter((s) => s.recognized).length;
  const Chevron = open ? ChevronDown : ChevronRight;

  const add = async () => {
    setAdding(true);
    try {
      const { data } = await monitorAPI.addSizes(category.id, text);
      const parts = [];
      if (data.added.length) parts.push(`${data.added.length} adicionada(s)`);
      if (data.existing.length) parts.push(`${data.existing.length} já existia(m): ${data.existing.map((e) => `${e.label} (${e.category})`).join(', ')}`);
      if (data.unrecognized.length) parts.push(`${data.unrecognized.length} não reconhecida(s)`);
      toast.success(parts.join(' · ') || 'Sem alterações');
      setText('');
      onChanged();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao adicionar medidas'));
    } finally {
      setAdding(false);
    }
  };

  const runNow = async () => {
    setRunning(true);
    try {
      const { data } = await monitorAPI.runNow(category.id);
      toast.success(`${category.name}: ${data.searches ?? data.sizes} pesquisas em ${data.new_jobs} lote(s) na fila`);
      onChanged();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao enfileirar a recolha'));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card data-testid={`monitor-cat-${category.id ?? 'none'}`}>
      <CardContent className="p-0">
        <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-4 py-3">
          <button type="button" onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 text-left min-w-0 lg:w-72" aria-expanded={open}>
            <Chevron size={16} className="flex-shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <p className="font-semibold truncate">{category.name}</p>
              <p className="text-xs text-muted-foreground">
                {category.dynamic ? 'automática · ' : ''}{category.sizes.length} medida(s)
                {category.excluded_suppliers?.length > 0 && <span> · {suppliers.length - category.excluded_suppliers.length} de {suppliers.length} fornecedores</span>}
                {recognized < category.sizes.length && <span className="text-amber-700 dark:text-amber-300"> · {category.sizes.length - recognized} não reconhecida(s)</span>}
              </p>
            </div>
          </button>
          <div className="flex-1 min-w-0">
            {category.id ? <TimesEditor category={category} onSaved={onChanged} /> : <span className="text-xs text-muted-foreground">Sem horário: mova estas medidas para uma categoria.</span>}
          </div>
          <div className="text-xs text-muted-foreground lg:w-56 lg:text-right">
            {category.next_run_at && <div>Próxima: <span className="text-foreground">{formatDateTime(category.next_run_at)}</span></div>}
            {category.last_run && <div>Última: {formatDateTime(category.last_run.at)} ({category.last_run.sizes} medidas)</div>}
          </div>
          {category.id && (
            <Button size="sm" variant="outline" onClick={runNow} disabled={running || recognized === 0} title="Enfileira já a recolha desta categoria em todos os fornecedores activos">
              {running ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Play size={14} className="mr-1" />} Recolher agora
            </Button>
          )}
        </div>
        {open && (
          <div className="border-t px-4 py-3 space-y-3 bg-muted/20">
            {category.dynamic && (
              <p className="text-xs text-muted-foreground">
                Calculada automaticamente a cada recolha: as medidas mais pesquisadas na aplicação nos últimos 14 dias (pelo menos 2 pesquisas). Não se editam à mão.
              </p>
            )}
            {category.sizes.length === 0
              ? <p className="text-sm text-muted-foreground">Sem medidas nesta categoria.</p>
              : <div className="flex flex-wrap gap-1.5">{category.sizes.map((s) => <SizeChip key={s.id ?? s.size_key} size={s} onDelete={onDelete} />)}</div>}
            {category.id && suppliers.length > 0 && <SupplierToggles category={category} suppliers={suppliers} onSaved={onChanged} />}
            {category.id && !category.dynamic && (
              <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={2}
                  placeholder="Acrescentar medidas: uma por linha ou separadas por vírgula (ex.: 205/55R16, 31570225)"
                  className="flex-1 rounded-md border bg-background px-2 py-1.5 text-sm font-mono"
                  aria-label={`Acrescentar medidas a ${category.name}`}
                />
                <Button size="sm" onClick={add} disabled={adding || !text.trim()}>
                  {adding ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Plus size={14} className="mr-1" />} Acrescentar
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const Monitorizacao = () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [toDelete, setToDelete] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data: d } = await monitorAPI.categories();
      setData(d);
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar as medidas monitorizadas'));
      setData((d) => d || { categories: [] });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const doDelete = async () => {
    const s = toDelete;
    setToDelete(null);
    try {
      await monitorAPI.deleteSize(s.id);
      toast.success(`${s.label} retirada`);
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao retirar a medida'));
    }
  };

  const cats = data?.categories || [];
  const total = cats.reduce((n, c) => n + c.sizes.length, 0);
  const lastSeen = cats.flatMap((c) => c.sizes).map((s) => s.last_success_at).filter(Boolean).sort().pop();

  return (
    <div className="space-y-4" data-testid="monitorizacao">
      <PageHeader
        eyebrow="Administração"
        title="Medidas monitorizadas"
        description={`Medidas que a aplicação recolhe automaticamente nos fornecedores, por categoria e horário (hora de ${data?.timezone === 'Europe/Lisbon' ? 'Lisboa' : data?.timezone || 'Lisboa'}). As categorias arrancam desfasadas e cada recolha começa com uma variação de até 10 minutos, para não sobrecarregar a aplicação nem os portais.`}
      />
      {error && <ErrorState message={error} onRetry={load} />}
      {data === null ? <Card><CardContent className="p-0"><TableSkeleton rows={6} cols={4} /></CardContent></Card> : cats.length === 0 ? (
        <Card><EmptyState title="Sem categorias" /></Card>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {total} medidas em {cats.length} categorias{lastSeen ? ` · última recolha ${formatAge(lastSeen)}` : ''}. Clique numa categoria para ver e editar as medidas.
            {data?.pause_seconds && ` Em cada fornecedor: pausa de ${data.pause_seconds[0]}–${data.pause_seconds[1]} s entre pesquisas, lotes de ${data.chunk_size} medidas e sem repetir medidas recolhidas há menos de ${data.skip_fresh_hours} h.`}
          </p>
          {cats.map((c) => <CategoryCard key={c.id ?? 'none'} category={c} suppliers={data?.suppliers || []} onChanged={load} onDelete={setToDelete} />)}
        </>
      )}
      <ConfirmDialog
        open={Boolean(toDelete)}
        onOpenChange={(o) => { if (!o) setToDelete(null); }}
        title={`Retirar ${toDelete?.label || ''}?`}
        description="Deixa de ser recolhida automaticamente. As ofertas já guardadas não são apagadas."
        confirmLabel="Retirar"
        onConfirm={doDelete}
      />
    </div>
  );
};

export default Monitorizacao;
