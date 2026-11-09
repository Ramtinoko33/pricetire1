import React from 'react';
import { Badge } from './ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip';
import { cn } from '@/lib/utils';
import { formatAge, formatDateTime, SEASON_LABELS } from '@/lib/format';

const TONES = {
  green: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30',
  red: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30',
  amber: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30',
  blue: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30',
  sky: 'bg-sky-100 text-sky-800 border-sky-300 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-500/30',
  purple: 'bg-purple-100 text-purple-800 border-purple-300 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30',
  slate: 'bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-500/30',
  orange: 'bg-orange-100 text-orange-800 border-orange-300 dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-500/30',
};

export function ToneBadge({ tone = 'slate', className, children, ...props }) {
  return (
    <Badge variant="outline" className={cn('whitespace-nowrap font-medium', TONES[tone] || TONES.slate, className)} {...props}>
      {children}
    </Badge>
  );
}

// Tooltip simples; em ecrãs táteis o conteúdo também aparece via title.
export function WithTooltip({ content, children }) {
  if (!content) return children;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent className="max-w-xs whitespace-pre-line">{content}</TooltipContent>
    </Tooltip>
  );
}

export const MATCH_META = {
  MATCH_EXACTO: { label: 'Exacto', tone: 'green' },
  ALTERNATIVA_COMPATIVEL: { label: 'Alternativa', tone: 'blue' },
  INCOMPATIVEL: { label: 'Incompatível', tone: 'red' },
  INFORMACAO_INSUFICIENTE: { label: 'Info insuficiente', tone: 'amber' },
};

export function matchLabel(matchClass) {
  return MATCH_META[matchClass]?.label || 'Sem classificação';
}

export function MatchBadge({ matchClass, details, reasons }) {
  const meta = MATCH_META[matchClass] || { label: 'Sem classificação', tone: 'slate' };
  const lines = (details && details.length ? details : reasons) || [];
  const badge = (
    <ToneBadge tone={meta.tone} data-testid="match-badge" title={lines.join('\n') || undefined}>
      {meta.label}
    </ToneBadge>
  );
  return lines.length ? <WithTooltip content={lines.join('\n')}>{badge}</WithTooltip> : badge;
}

export function StockBadge({ status, qty, location }) {
  const upTo = typeof location === 'string' ? location.match(/^até \d+/) : null;
  const extra = qty !== null && qty !== undefined ? ` (${qty})` : (upTo ? ` (${upTo[0]})` : '');
  const title = location || undefined;
  if (status === 'available') return <ToneBadge tone="green" title={title}>Disponível{extra}</ToneBadge>;
  if (status === 'unavailable') return <ToneBadge tone="red" title={title}>Indisponível{extra}</ToneBadge>;
  return <ToneBadge tone="slate" title={title}>Desconhecido{extra}</ToneBadge>;
}

export function StaleBadge() {
  return <ToneBadge tone="orange" data-testid="stale-badge">Desactualizado</ToneBadge>;
}

export function FreshnessCell({ at, ageHours, fresh }) {
  return (
    <div className="flex flex-col gap-0.5 text-xs">
      <span className="font-mono whitespace-nowrap">{formatDateTime(at)}</span>
      <span className="text-muted-foreground whitespace-nowrap">
        {ageHours !== undefined && ageHours !== null ? formatAge(ageHours) : formatAge(at)}
      </span>
      {fresh === false && <StaleBadge />}
    </div>
  );
}

// Badges técnicos de uma oferta (C, XL, RunFlat, homologação, estação, DEMO).
export function OfferFlags({ offer }) {
  if (!offer) return null;
  const items = [];
  if (offer.commercial === true || /C$/.test(offer.size_key || '')) {
    items.push(<ToneBadge key="c" tone="amber" title="Pneu comercial (C)">C</ToneBadge>);
  }
  if (offer.xl === true) items.push(<ToneBadge key="xl" tone="purple">XL</ToneBadge>);
  if (offer.runflat === true) {
    items.push(<ToneBadge key="rf" tone="sky">RunFlat{offer.runflat_tech ? ` ${offer.runflat_tech}` : ''}</ToneBadge>);
  }
  if (offer.homologation) {
    String(offer.homologation).split(',').map((h) => h.trim()).filter(Boolean).forEach((h) => {
      items.push(<ToneBadge key={`h-${h}`} tone="slate" title="Homologação">{h}</ToneBadge>);
    });
  }
  if (offer.season && SEASON_LABELS[offer.season]) {
    items.push(<ToneBadge key="season" tone={offer.season === 'winter' ? 'blue' : offer.season === 'summer' ? 'amber' : 'green'}>{SEASON_LABELS[offer.season]}</ToneBadge>);
  }
  if (offer.condition && offer.condition !== 'new') {
    items.push(<ToneBadge key="cond" tone="red">{offer.condition === 'demo' ? 'DEMO' : offer.condition === 'used' ? 'Usado' : offer.condition === 'retread' ? 'Recauchutado' : offer.condition}</ToneBadge>);
  }
  if (!items.length) return null;
  return <div className="flex flex-wrap gap-1">{items}</div>;
}

export const HEALTH_META = {
  ok: { label: 'OK', tone: 'green' },
  failing: { label: 'Falha', tone: 'red' },
  failed: { label: 'Falha', tone: 'red' },
  error: { label: 'Falha', tone: 'red' },
  degraded: { label: 'Instável', tone: 'amber' },
  never: { label: 'Nunca testado', tone: 'slate' },
  unknown: { label: 'Nunca testado', tone: 'slate' },
};

export function healthKey(health) {
  if (!health) return 'never';
  const s = String(health.status || '').toLowerCase();
  if (HEALTH_META[s]) return s;
  if (!health.last_success_at && !health.last_failure_at) return 'never';
  return (health.consecutive_failures || 0) > 0 ? 'failing' : 'ok';
}

export function HealthBadge({ health }) {
  const meta = HEALTH_META[healthKey(health)];
  return <ToneBadge tone={meta.tone} data-testid="health-badge">{meta.label}</ToneBadge>;
}

export const COMPARISON_STATUS = {
  saving: { label: 'Poupança', tone: 'green' },
  no_saving: { label: 'Sem poupança', tone: 'slate' },
  no_exact_match: { label: 'Sem correspondência exacta', tone: 'amber' },
  no_data: { label: 'Sem dados', tone: 'slate' },
  no_reference_price: { label: 'Sem preço de referência', tone: 'slate' },
  stale: { label: 'Desactualizado', tone: 'orange' },
};

export function ComparisonStatusBadge({ status }) {
  const meta = COMPARISON_STATUS[status] || { label: status || '—', tone: 'slate' };
  return <ToneBadge tone={meta.tone}>{meta.label}</ToneBadge>;
}

export const JOB_STATUS = {
  queued: { label: 'Em espera', tone: 'slate' },
  pending: { label: 'Em espera', tone: 'slate' },
  running: { label: 'A correr', tone: 'blue' },
  done: { label: 'Concluído', tone: 'green' },
  completed: { label: 'Concluído', tone: 'green' },
  partial: { label: 'Parcial', tone: 'amber' },
  failed: { label: 'Falhou', tone: 'red' },
  error: { label: 'Falhou', tone: 'red' },
  cancelled: { label: 'Cancelado', tone: 'amber' },
  canceled: { label: 'Cancelado', tone: 'amber' },
  timeout: { label: 'Timeout', tone: 'orange' },
};

// Estados terminais de um job (partial = sucesso parcial: algumas medidas falharam).
export const JOB_FINISHED = new Set(['done', 'completed', 'partial', 'failed', 'error', 'cancelled', 'canceled', 'timeout']);
export const JOB_SUCCESS = new Set(['done', 'completed', 'partial']);

export function JobStatusBadge({ status }) {
  const meta = JOB_STATUS[status] || { label: status || '—', tone: 'slate' };
  return <ToneBadge tone={meta.tone}>{meta.label}</ToneBadge>;
}

export const ERROR_KIND_LABELS = {
  login_failed: 'Login falhou',
  blocked: 'Bloqueado/captcha',
  timeout: 'Timeout',
  parse_error: 'Erro de leitura',
  network: 'Erro de rede',
  not_implemented: 'Não implementado',
  unknown: 'Desconhecido',
};

export function HealthDetails({ health }) {
  if (!health) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <div className="text-xs space-y-0.5 min-w-[180px]">
      <div>Último sucesso: <span className="font-mono">{formatDateTime(health.last_success_at)}</span>{health.last_success_at && <span className="text-muted-foreground"> ({formatAge(health.last_success_at)})</span>}</div>
      {health.last_failure_at && (
        <div className="text-red-700 dark:text-red-400">
          Última falha: <span className="font-mono">{formatDateTime(health.last_failure_at)}</span>
          {health.last_error_kind && <> · {ERROR_KIND_LABELS[health.last_error_kind] || health.last_error_kind}</>}
          {health.last_error && (
            <WithTooltip content={health.last_error}>
              <div className="truncate max-w-[260px] cursor-help" title={health.last_error}>{health.last_error}</div>
            </WithTooltip>
          )}
        </div>
      )}
      {(health.consecutive_failures || 0) > 0 && (
        <div className="text-red-700 dark:text-red-400">Falhas consecutivas: {health.consecutive_failures}</div>
      )}
    </div>
  );
}
