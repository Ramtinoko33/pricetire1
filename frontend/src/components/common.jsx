import React from 'react';
import { AlertCircle, Inbox, Loader2, RefreshCw } from 'lucide-react';
import { Button } from './ui/button';
import { Skeleton } from './ui/skeleton';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from './ui/alert-dialog';
import { cn } from '@/lib/utils';

export function PageHeader({ title, description, actions }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h2 className="text-xl sm:text-2xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>{title}</h2>
        {description && <p className="text-sm text-muted-foreground mt-1">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title = 'Sem dados', description, action, className }) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center py-10 px-4', className)} data-testid="empty-state">
      <Inbox className="text-muted-foreground mb-3" size={36} />
      <p className="font-medium">{title}</p>
      {description && <p className="text-sm text-muted-foreground mt-1 max-w-md">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry, className }) {
  return (
    <div
      className={cn('flex flex-col sm:flex-row sm:items-center gap-3 rounded-md border border-red-300 bg-red-50 dark:bg-red-500/10 dark:border-red-500/30 p-4 text-sm text-red-800 dark:text-red-300', className)}
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
            className={destructive ? 'bg-red-600 hover:bg-red-700 text-white' : undefined}
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
      'flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50',
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
    <div className={cn('space-y-1', className)}>
      {label && <label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">{label}</label>}
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function KpiCard({ title, value, sub, icon: Icon, tone = 'text-foreground', bg = 'bg-muted', loading, testId }) {
  return (
    <div className="rounded-xl border bg-card text-card-foreground shadow p-4 sm:p-5" data-testid={testId}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground mb-1">{title}</p>
          {loading ? (
            <Skeleton className="h-7 w-20" />
          ) : (
            <p className="text-2xl font-bold truncate" style={{ fontFamily: 'JetBrains Mono, monospace' }}>{value}</p>
          )}
          {sub && !loading && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        </div>
        {Icon && (
          <div className={cn('p-3 rounded-sm flex-shrink-0', bg)}>
            <Icon className={tone} size={20} />
          </div>
        )}
      </div>
    </div>
  );
}
