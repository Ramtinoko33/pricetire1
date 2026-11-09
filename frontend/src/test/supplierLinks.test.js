import { describe, expect, it } from 'vitest';
import { compactSize, opensResults, slashedSize, supplierSearchUrl } from '@/lib/supplierLinks';

describe('supplierLinks', () => {
  it('MP24 abre os resultados da medida (ligeiro, camião, jipe)', () => {
    expect(supplierSearchUrl('MP24', '2056515')).toBe('https://pt.mp24.online/pt_PT/tyres2v0/car/result?matchcode=2056515');
    expect(supplierSearchUrl('MP24', '3157022.5')).toBe('https://pt.mp24.online/pt_PT/tyres2v0/truck/result?matchcode=31570225');
    expect(supplierSearchUrl('MP24', '31X10.50R15')).toBe('https://pt.mp24.online/pt_PT/tyres2v0/car/result?matchcode=31105015');
  });
  it('TugaPneus pesquisa pela medida; os outros abrem o portal', () => {
    expect(supplierSearchUrl('TugaPneus', '2055516')).toBe('https://www.tugapneus.pt/produtos?search=205%2F55R16');
    expect(supplierSearchUrl('Aguesport', '2055516')).toBe('https://encomendas.aguesport.com/');
    expect(opensResults('MP24') && opensResults('TugaPneus') && !opensResults('Aguesport')).toBe(true);
  });
  it('formatos da medida para colar', () => {
    expect(compactSize('2156516C')).toBe('2156516C');
    expect(slashedSize('3157022.5')).toBe('315/70R22.5');
    expect(slashedSize('37X12.50R17')).toBe('37x12.50R17');
  });
});
