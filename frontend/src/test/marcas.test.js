import { describe, expect, it } from 'vitest';
import { filterBrands } from '@/pages/Marcas';

describe('filterBrands', () => {
  const rows = [{ brand: 'MICHELIN', category: 'premium' }, { brand: 'NEXEN', category: 'quality' }, { brand: 'ZETA', category: null }];
  it('filtra por texto e por tier', () => {
    expect(filterBrands(rows, 'ne', 'all').map((r) => r.brand)).toEqual(['NEXEN']);
    expect(filterBrands(rows, '', 'none').map((r) => r.brand)).toEqual(['ZETA']);
    expect(filterBrands(rows, '', 'premium').map((r) => r.brand)).toEqual(['MICHELIN']);
  });
});
