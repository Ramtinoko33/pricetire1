import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ComparisonStatusBadge, HealthBadge, JobStatusBadge, MatchBadge, StockBadge, healthKey } from '@/components/badges';
import { exactSaving, summarizeResults } from '@/components/ComparisonResultsTable';

const wrap = (ui) => render(<TooltipProvider>{ui}</TooltipProvider>);

describe('MatchBadge', () => {
  it.each([
    ['MATCH_EXACTO', 'Exacto'],
    ['ALTERNATIVA_COMPATIVEL', 'Alternativa'],
    ['INCOMPATIVEL', 'Incompatível'],
    ['INFORMACAO_INSUFICIENTE', 'Info insuficiente'],
    [null, 'Sem classificação'],
  ])('%s → %s', (cls, label) => {
    wrap(<MatchBadge matchClass={cls} />);
    expect(screen.getByTestId('match-badge')).toHaveTextContent(label);
  });

  it('expõe os detalhes como title', () => {
    wrap(<MatchBadge matchClass="ALTERNATIVA_COMPATIVEL" details={['XL diferente']} />);
    expect(screen.getByTestId('match-badge')).toHaveAttribute('title', 'XL diferente');
  });
});

describe('outros badges', () => {
  it('stock com quantidade', () => {
    wrap(<StockBadge status="available" qty={4} />);
    expect(screen.getByText('Disponível (4)')).toBeInTheDocument();
  });
  it('stock desconhecido', () => {
    wrap(<StockBadge status={null} />);
    expect(screen.getByText('Desconhecido')).toBeInTheDocument();
  });
  it('saúde do fornecedor', () => {
    expect(healthKey(null)).toBe('never');
    expect(healthKey({ status: 'degraded' })).toBe('degraded');
    wrap(<HealthBadge health={{ status: 'failing' }} />);
    expect(screen.getByTestId('health-badge')).toHaveTextContent('Falha');
  });
  it('job parcial', () => {
    wrap(<JobStatusBadge status="partial" />);
    expect(screen.getByText('Parcial')).toBeInTheDocument();
  });
  it('estado da comparação do catálogo', () => {
    wrap(<ComparisonStatusBadge status="no_exact_match" />);
    expect(screen.getByText('Sem correspondência exacta')).toBeInTheDocument();
  });
});

describe('poupança só para MATCH_EXACTO', () => {
  const rows = [
    { match_class: 'MATCH_EXACTO', economia_euro: 4, economia_percent: 7 },
    { match_class: 'ALTERNATIVA_COMPATIVEL', economia_euro: 10, economia_percent: 15 },
    { match_class: null, economia_euro: null },
  ];
  it('exactSaving ignora alternativas', () => {
    expect(exactSaving(rows[0])).toEqual({ eur: 4, pct: 7 });
    expect(exactSaving(rows[1])).toBeNull();
  });
  it('summarizeResults soma só exactos', () => {
    expect(summarizeResults(rows)).toEqual({ total: 3, exact: 1, found: 1, savings: 4 });
  });
});
