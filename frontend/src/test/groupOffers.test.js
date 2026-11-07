import { describe, expect, it } from 'vitest';
import { groupOffers } from '@/lib/groupOffers';

const o = (id, supplier, model, li, si, price, extra = {}) => ({
  id, supplier_id: supplier, supplier_name: supplier, brand: 'MICHELIN', model, model_key: model.replace(/\s/g, ''),
  load_index_1: li, speed_index: si, price, size_key: '2056515', ...extra,
});

describe('groupOffers', () => {
  const offers = [
    o(1, 'S José', 'PRIMACY 4', 94, 'H', 102.43),
    o(2, 'MP24', 'PRIMACY 4', 94, 'H', 101.6),
    o(3, 'ABTyres', 'PRIMACY4', 94, 'H', 103.95),
    o(4, 'ABTyres', 'PRIMACY4', 94, 'V', 103.95),
    o(5, 'Soledad', 'PRIMACY 4', 94, 'V', 105.73),
    o(6, 'MP24', 'PRIMACY 4', 94, 'H', 99.0, { condition: 'demo' }),
    o(7, 'Prismanil', 'AGILIS', 102, 'T', 90.0, { commercial: true, size_key: '2056515C' }),
  ];

  it('agrupa o mesmo pneu e mostra o mais barato', () => {
    const g = groupOffers(offers);
    const h = g.find((x) => x.best.speed_index === 'H' && !x.best.condition);
    expect(h.best.supplier_name).toBe('MP24');
    expect(h.others.map((x) => x.price)).toEqual([102.43, 103.95]);
    expect(h.suppliers).toBe(3);
  });

  it('separa índices, DEMO e pneus C', () => {
    const g = groupOffers(offers);
    expect(g).toHaveLength(4);
    expect(g.map((x) => x.best.id)).toEqual([7, 6, 2, 4]);
  });

  it('ordena os grupos por preço descendente', () => {
    expect(groupOffers(offers, 'desc').map((x) => x.best.id)).toEqual([4, 2, 6, 7]);
  });
});
