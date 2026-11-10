import React from 'react';
import { AlertCircle, Inbox, Loader2, RefreshCw } from 'lucide-react';
import { Button } from './ui/button';
import { Skeleton } from './ui/skeleton';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from './ui/alert-dialog';
import { cn } from '@/lib/utils';

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between" data-testid="page-header">
      <div className="min-w-0">
        {eyebrow && <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-primary">{eyebrow}</p>}
        <h1 className="text-2xl sm:text-[28px] font-extrabold leading-tight tracking-[-0.02em] text-foreground">{title}</h1>
        {description && <p className="mt-1.5 max-w-3xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title = 'Sem dados', description, action, className, icon: Icon = Inbox }) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center py-10 px-4', className)} data-testid="empty-state">
      {Icon && <Icon className="text-muted-foreground/70 mb-3" size={28} strokeWidth={1.6} aria-hidden="true" />}
      <p className="font-bold text-foreground">{title}</p>
      {description && <p className="text-sm text-muted-foreground mt-1.5 max-w-md">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry, className }) {
  return (
    <div
      className={cn('flex flex-col sm:flex-row sm:items-center gap-3 rounded-lg border border-danger/30 bg-danger-subtle p-4 text-sm text-danger', className)}
      role="alert"
      data-testid="error-state"
    >
      <div className="flex items-start gap-2 flex-1">
        <AlertCircle size={18} className="mt-0.5 flex-shrink-0" />
        <span>{message || 'Ocorreu um erro ao carregar os dados.'}</span>
      </div>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw size={14} className="mr-1" /> Tentar novamente
        </Button>
      )}
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 5 }) {
  return (
    <div className="space-y-2 p-4" data-testid="loading">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton key={c} className="h-6 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Spinner({ label = 'A carregar...', className }) {
  return (
    <div className={cn('flex items-center justify-center gap-2 py-10 text-muted-foreground text-sm', className)} data-testid="loading">
      <Loader2 className="animate-spin" size={18} /> {label}
    </div>
  );
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = 'Confirmar', destructive = false, onConfirm }) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description && <AlertDialogDescription>{description}</AlertDialogDescription>}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            className={destructive ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : undefined}
            onClick={onConfirm}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// Select nativo estilizado como os inputs shadcn (mais robusto em mobile).
export const NativeSelect = React.forwardRef(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      'flex h-10 w-full rounded-lg border border-input bg-card px-3 py-1 text-sm text-foreground hover:border-foreground/50 focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/25 disabled:opacity-55',
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
NativeSelect.displayName = 'NativeSelect';

export function Field({ label, htmlFor, hint, children, className }) {
  return (
    <div className={cn('space-y-1.5', className)}>
      {label && <label htmlFor={htmlFor} className="block text-xs font-semibold text-foreground">{label}</label>}
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

// Indicador compacto: valor em destaque, sem caixas decorativas de ícone (o ícone é opcional e discreto).
export function KpiCard({ title, value, sub, icon: Icon, tone, loading, testId, className }) {
  return (
    <div className={cn('rounded-lg border bg-card text-card-foreground shadow-panel p-4 sm:p-5', className)} data-testid={testId}>
      <KpiBody title={title} value={value} sub={sub} icon={Icon} tone={tone} loading={loading} />
    </div>
  );
}

function KpiBody({ title, value, sub, icon: Icon, tone, loading }) {
  return (
    <div className="min-w-0">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        {Icon && <Icon size={14} className={cn('flex-shrink-0', tone || 'text-muted-foreground')} aria-hidden="true" />}
        {title}
      </p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-20" />
      ) : (
        <p className="mt-1.5 truncate text-[26px] sm:text-[28px] font-extrabold leading-tight tracking-[-0.03em] tabular-nums text-foreground">{value}</p>
      )}
      {sub && !loading && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

// Faixa de indicadores separados por divisórias (Dashboard / Operação).
export function KpiStrip({ items, loading }) {
  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 border-y border-border py-5 gap-y-5" data-testid="kpi-strip">
      {items.map((k, i) => (
        <div
          key={k.testId || k.title}
          data-testid={k.testId}
          className={cn(
            'min-w-0 px-4 sm:px-5 border-border',
            i % 2 === 0 ? 'pl-0 sm:pl-0' : 'border-l',
            i > 0 && 'xl:border-l xl:pl-5',
          )}
        >
          <KpiBody {...k} loading={loading} />
        </div>
      ))}
    </div>
  );
}
