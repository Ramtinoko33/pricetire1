import { describe, expect, it } from 'vitest';
import { formatAge, formatLoadSpeed, parseSize, parseSizeList } from '@/lib/format';

describe('parseSize', () => {
  it.each([
    ['205/55R16', '205/55R16', '2055516'],
    ['205 55 16', '205/55R16', '2055516'],
    ['2055516', '205/55R16', '2055516'],
    ['205/55 r16', '205/55R16', '2055516'],
    ['225/45ZR17', '225/45ZR17', '2254517'],
    ['215/65R16C', '215/65R16C', '2156516C'],
    ['205-55-16', '205/55R16', '2055516'],
  ])('%s → %s', (input, display, key) => {
    const s = parseSize(input);
    expect(s).not.toBeNull();
    expect(s.display).toBe(display);
    expect(s.key).toBe(key);
  });

  it.each(['', 'abc', '205/55', '99/55R16', '2055', '205/55R40'])('rejeita "%s"', (input) => {
    expect(parseSize(input)).toBeNull();
  });

  it('lista de medidas remove duplicados e separa inválidas', () => {
    const { sizes, invalid } = parseSizeList('205/55R16, 2055516; xpto\n195 65 15');
    expect(sizes.map((s) => s.key)).toEqual(['2055516', '1956515']);
    expect(invalid).toEqual(['xpto']);
  });
});

describe('formatAge', () => {
  const now = new Date('2026-11-04T12:00:00Z');
  it('formata horas numéricas (age_hours)', () => {
    expect(formatAge(0)).toBe('agora mesmo');
    expect(formatAge(0.5)).toBe('há 30 min');
    expect(formatAge(3.2)).toBe('há 3 h');
    expect(formatAge(26)).toBe('há 1 dia');
    expect(formatAge(24 * 5)).toBe('há 5 dias');
  });
  it('formata datas', () => {
    expect(formatAge('2026-11-04T09:00:00Z', now)).toBe('há 3 h');
    expect(formatAge('2026-11-04T11:58:00Z', now)).toBe('há 2 min');
  });
  it('valores inválidos', () => {
    expect(formatAge(null)).toBe('—');
    expect(formatAge('não é data')).toBe('—');
  });
});

describe('formatLoadSpeed', () => {
  it('índice simples e duplo', () => {
    expect(formatLoadSpeed({ load_index_1: 91, speed_index: 'V' })).toBe('91V');
    expect(formatLoadSpeed({ load_index_1: 109, load_index_2: 107, speed_index: 'T' })).toBe('109/107T');
    expect(formatLoadSpeed({})).toBe('—');
  });
});

describe('parseSize camião', () => {
  it('aceita compacto de 8 dígitos com jante .5', () => {
    expect(parseSize('31570225')).toMatchObject({ width: 315, aspect: 70, rim: 22.5, display: '315/70R22.5', key: '3157022.5' });
    expect(parseSize('21575175')?.display).toBe('215/75R17.5');
  });
  it('aceita larguras de camião e medidas sem perfil', () => {
    expect(parseSize('445/45R19.5')?.display).toBe('445/45R19.5');
    expect(parseSize('12R22.5')).toMatchObject({ display: '12R22.5', key: '12-22.5', aspect: null });
  });
  it('mantém ligeiros', () => {
    expect(parseSize('2055516')?.display).toBe('205/55R16');
  });
});
