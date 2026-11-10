import React, { useMemo, useState } from 'react';
import { Input } from './ui/input';
import { cn } from '@/lib/utils';

const MAX_SUGGESTIONS = 10;

// Sugestões de marca por baixo do campo, só depois da primeira letra.
// Primeiro as marcas que começam pelo texto, depois as que o contêm.
export function brandSuggestions(options, value) {
  const q = String(value || '').trim().toUpperCase();
  if (!q) return [];
  const starts = [];
  const contains = [];
  for (const b of options || []) {
    const u = String(b).toUpperCase();
    if (u === q) continue;
    if (u.startsWith(q)) starts.push(b);
    else if (u.includes(q)) contains.push(b);
  }
  return [...starts, ...contains].slice(0, MAX_SUGGESTIONS);
}

export default function BrandInput({ id, value, onChange, options }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const items = useMemo(() => brandSuggestions(options, value), [options, value]);
  const show = open && items.length > 0;

  const pick = (b) => {
    onChange(b);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e) => {
    if (!show) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => (i + 1) % items.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => (i <= 0 ? items.length - 1 : i - 1));
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault();
      pick(items[active]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <Input
        id={id}
        value={value}
        autoComplete="off"
        role="combobox"
        aria-expanded={show}
        aria-controls={`${id}-list`}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(-1); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
      />
      {show && (
        <ul
          id={`${id}-list`}
          role="listbox"
          data-testid="brand-suggestions"
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-64 overflow-auto rounded-lg border bg-popover text-popover-foreground shadow-overlay"
        >
          {items.map((b, i) => (
            <li
              key={b}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => { e.preventDefault(); pick(b); }}
              onMouseEnter={() => setActive(i)}
              className={cn('cursor-pointer px-3 py-1.5 text-sm', i === active && 'bg-accent text-accent-foreground')}
            >
              {b}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
