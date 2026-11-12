import { describe, expect, it } from 'vitest';
import { describeFilters } from '@/pages/HistoricoPesquisas';

describe('describeFilters', () => {
  it('descreve os filtros técnicos sem a marca', () => {
    expect(describeFilters({ load_index: '91', xl: true, supplier_ids: ['a', 'b'] }))
      .toBe('Índice: 91 · XL: sim · Fornecedores: a, b');
    expect(describeFilters({})).toBe('');
  });
});
