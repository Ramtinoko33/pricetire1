import { describe, expect, it } from 'vitest';
import { filterOptions } from '@/components/MultiBrandSelect';

describe('filterOptions', () => {
  const opts = ['MICHELIN', 'MINERVA', 'BFGOODRICH', 'GOODYEAR', 'PIRELLI'].map((value) => ({ value }));
  it('sem texto mostra todas', () => {
    expect(filterOptions(opts, '')).toHaveLength(5);
  });
  it('primeiro as que começam pelo texto, depois as que o contêm', () => {
    expect(filterOptions(opts, 'good').map((o) => o.value)).toEqual(['GOODYEAR', 'BFGOODRICH']);
    expect(filterOptions(opts, 'mi').map((o) => o.value)).toEqual(['MICHELIN', 'MINERVA']);
  });
});
