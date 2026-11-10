import React from 'react';
import { Badge } from './ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip';
import { cn } from '@/lib/utils';
import { formatAge, formatDateTime, SEASON_LABELS } from '@/lib/format';

// Cores semânticas da identidade C: verde = disponível/poupança exacta, âmbar = atenção,
// vermelho = falha, azul = informação/alternativa, laranja = desactualizado, petróleo = atributo.
const TONES = {
  green: 'bg-success-subtle text-success border-success/25',
  red: 'bg-danger-subtle text-danger border-danger/25',
  amber: 'bg-warning-subtle text-warning border-warning/25',
  blue: 'bg-info-subtle text-info border-info/25',
  sky: 'bg-info-subtle text-info border-info/25',
  purple: 'bg-accent text-accent-foreground border-primary/20',
  slate: 'bg-muted text-muted-foreground border-border',
  orange: 'bg-orange-50 text-orange-700 border-orange-700/25 dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-400/30',
};

// Estado de stock: sinal + texto (sem caixa), como na maqueta; o texto é sempre explícito.
const STOCK_TONES = {
  green: 'text-success',
  red: 'text-danger',
  amber: 'text-warning',
  slate: 'text-muted-foreground',
};

function StockText({ tone, title, children }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold', STOCK_TONES[tone])} title={title} data-testid="stock-badge">
      <span aria-hidden="true" className={cn('h-1.5 w-1.5 flex-shrink-0 rounded-full bg-current', tone === 'slate' && 'bg-transparent ring-1 ring-current')} />
      {children}
    </span>
  );
}

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
  if (status === 'available') return <StockText tone="green" title={title}>{`Disponível${extra}`}</StockText>;
  if (status === 'unavailable') return <StockText tone="red" title={title}>{`Indisponível${extra}`}</StockText>;
  if (location === 'Sob consulta') return <StockText tone="amber" title="O fornecedor não divulga a quantidade no portal">Sob consulta</StockText>;
  return <StockText tone="slate" title={title}>{`Desconhecido${extra}`}</StockText>;
}

export function StaleBadge() {
  return <ToneBadge tone="orange" data-testid="stale-badge">Desactualizado</ToneBadge>;
}

export function FreshnessCell({ at, ageHours, fresh }) {
  return (
    <div className="flex flex-col items-start gap-0.5 text-xs">
      <span className="whitespace-nowrap font-medium text-foreground tabular-nums">{formatDateTime(at)}</span>
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
      <div>Último sucesso: <span className="tabular-nums">{formatDateTime(health.last_success_at)}</span>{health.last_success_at && <span className="text-muted-foreground"> ({formatAge(health.last_success_at)})</span>}</div>
      {health.last_failure_at && (
        <div className="text-red-700 dark:text-red-400">
          Última falha: <span className="tabular-nums">{formatDateTime(health.last_failure_at)}</span>
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
