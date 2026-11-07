import { describe, expect, it } from 'vitest';
import { brandSuggestions } from '@/components/BrandInput';

describe('brandSuggestions', () => {
  const brands = ['MICHELIN', 'MINERVA', 'BFGOODRICH', 'GOODYEAR', 'KUMHO'];
  it('só sugere depois da primeira letra', () => {
    expect(brandSuggestions(brands, '')).toEqual([]);
  });
  it('primeiro as que começam pelo texto, depois as que o contêm', () => {
    expect(brandSuggestions(brands, 'go')).toEqual(['GOODYEAR', 'BFGOODRICH']);
    expect(brandSuggestions(brands, 'mi')).toEqual(['MICHELIN', 'MINERVA']);
  });
  it('não repete a marca já escrita', () => {
    expect(brandSuggestions(brands, 'kumho')).toEqual([]);
  });
});
