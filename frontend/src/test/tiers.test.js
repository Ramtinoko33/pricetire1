import { describe, expect, it } from 'vitest';
import { buildTierMap, splitByTier, tierFromCategory, tierOf } from '@/lib/tiers';

describe('tiers', () => {
  const map = buildTierMap([
    { brand: 'MICHELIN', category: 'premium' },
    { brand: 'HANKOOK', category: 'quality' },
    { brand: 'LINGLONG', category: 'budget' },
    { brand: 'GT RADIAL', category: 'budget' },
  ]);
  it('lê as categorias', () => {
    expect([tierFromCategory('Premium'), tierFromCategory('tier 2'), tierFromCategory('3'), tierFromCategory('x')]).toEqual([1, 2, 3, 0]);
    expect(tierOf('GTRADIAL', map)).toBe(3);
  });
  it('divide por colunas e só mostra "Sem classificação" quando há ofertas', () => {
    const cols = splitByTier([{ brand: 'MICHELIN' }, { brand: 'LINGLONG' }], map);
    expect(cols.map((c) => [c.key, c.offers.length])).toEqual([[1, 1], [2, 0], [3, 1]]);
    expect(splitByTier([{ brand: 'ZZZ' }], map).map((c) => c.key)).toEqual([1, 2, 3, 0]);
  });
});
