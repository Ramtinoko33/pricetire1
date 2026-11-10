import React, { useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, X } from 'lucide-react';
import { cn } from '@/lib/utils';

const norm = (s) => String(s || '').toUpperCase();

// Opções filtradas pelo texto: primeiro as que começam por ele, depois as que o contêm.
export function filterOptions(options, query) {
  const q = norm(query).trim();
  if (!q) return options;
  const starts = [];
  const contains = [];
  options.forEach((o) => {
    const v = norm(o.value);
    if (v.startsWith(q)) starts.push(o);
    else if (v.includes(q)) contains.push(o);
  });
  return [...starts, ...contains];
}

// Selecção de várias marcas: escrever filtra a lista, clicar (ou Enter) marca/desmarca.
// options: [{ value, count? }]. showAllOnFocus=false só abre a lista depois da 1.ª letra.
export default function MultiBrandSelect({
  id, value = [], onChange, options = [], placeholder = 'Todas as marcas', showAllOnFocus = true, compact = false, testId,
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const selected = useMemo(() => new Set(value.map(norm)), [value]);
  const items = useMemo(() => filterOptions(options, query), [options, query]);
  const show = open && (showAllOnFocus || query.trim().length > 0) && items.length > 0;

  const toggle = (v) => {
    const key = norm(v);
    onChange(selected.has(key) ? value.filter((x) => norm(x) !== key) : [...value, v]);
    setQuery('');
    setActive(0);
    inputRef.current?.focus();
  };

  const onKeyDown = (e) => {
    if (e.key === 'Backspace' && !query && value.length) {
      onChange(value.slice(0, -1));
      return;
    }
    if (!show) {
      if (e.key === 'ArrowDown') setOpen(true);
      return;
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % items.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i <= 0 ? items.length - 1 : i - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); if (items[active]) toggle(items[active].value); }
    else if (e.key === 'Escape') setOpen(false);
  };

  return (
    <div className="relative" data-testid={testId}>
      <div
        className={cn(
          'relative flex flex-wrap items-center gap-1 rounded-lg border border-input bg-card pl-2 pr-7 cursor-text hover:border-foreground/50 focus-within:border-primary focus-within:ring-2 focus-within:ring-ring/25',
          compact ? 'min-h-8 py-0.5' : 'min-h-10 py-1',
          value.length > 0 && 'border-primary',
        )}
        onClick={() => { inputRef.current?.focus(); setOpen(true); }}
      >
        {value.map((v) => (
          <span key={v} className="inline-flex items-center gap-0.5 rounded-sm bg-accent text-accent-foreground px-1.5 py-0.5 text-xs font-semibold">
            {v}
            <button type="button" aria-label={`Remover ${v}`} onMouseDown={(e) => { e.preventDefault(); toggle(v); }} className="hover:text-foreground">
              <X size={11} />
            </button>
          </span>
        ))}
        <input
          id={id}
          ref={inputRef}
          value={query}
          autoComplete="off"
          role="combobox"
          aria-expanded={show}
          placeholder={value.length ? '' : placeholder}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
          onFocus={() => { setOpen(true); setFocused(true); }}
          onBlur={() => { setFocused(false); setTimeout(() => setOpen(false), 120); }}
          onKeyDown={onKeyDown}
          // Com marcas escolhidas, o campo só ocupa espaço enquanto se escreve (não empurra nada para baixo).
          className={cn('bg-transparent outline-none', compact ? 'text-xs h-6' : 'text-sm h-7',
            !value.length ? 'flex-1 min-w-[60px]' : (focused || query ? 'flex-1 min-w-[3ch]' : 'w-0 min-w-0 flex-1'))}
        />
        {value.length > 0 ? (
          <button type="button" aria-label="Limpar marcas" onMouseDown={(e) => { e.preventDefault(); onChange([]); }} className={cn('absolute right-1.5 text-muted-foreground hover:text-foreground p-0.5', compact ? 'top-[7px]' : 'top-[9px]')}>
            <X size={14} />
          </button>
        ) : showAllOnFocus && <ChevronDown size={14} className={cn('absolute right-2 text-muted-foreground pointer-events-none', compact ? 'top-[8px]' : 'top-[10px]')} />}
      </div>
      {show && (
        <ul role="listbox" aria-multiselectable="true" className="absolute left-0 right-0 top-full z-50 mt-1 max-h-64 overflow-auto rounded-lg border bg-popover text-popover-foreground shadow-overlay py-1">
          {items.map((o, i) => {
            const on = selected.has(norm(o.value));
            return (
              <li
                key={o.value}
                role="option"
                aria-selected={on}
                onMouseDown={(e) => { e.preventDefault(); toggle(o.value); }}
                onMouseEnter={() => setActive(i)}
                className={cn('flex items-center gap-2 cursor-pointer px-2.5 py-1.5 text-sm', i === active && 'bg-accent text-accent-foreground')}
              >
                <span className={cn('flex h-4 w-4 items-center justify-center rounded border', on ? 'bg-primary border-primary text-primary-foreground' : 'border-input')}>
                  {on && <Check size={12} />}
                </span>
                <span className="flex-1">{o.value}</span>
                {o.count != null && <span className="text-xs text-muted-foreground">{o.count}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
