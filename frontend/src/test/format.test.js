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
    expect(parseSize('12R22.5')).toMatchObject({ display: '12R22.5', key: '12R22.5', aspect: null });
  });
  it('mantém ligeiros', () => {
    expect(parseSize('2055516')?.display).toBe('205/55R16');
  });
});

describe('parseSize polegadas', () => {
  it.each(['37125017', '371217', '3712517', '37x12.5R17', '37X12.50 R17', '37x12.5-17', 'LT37X12.50R17'])('%s', (v) => {
    expect(parseSize(v)).toMatchObject({ display: '37x12.50R17', key: '37X12.50R17' });
  });
  it('não troca medidas métricas nem de camião', () => {
    expect(parseSize('2055516')?.display).toBe('205/55R16');
    expect(parseSize('31570225')?.display).toBe('315/70R22.5');
  });
});

describe('parseSize agrícola, empilhador e OTR', () => {
  it.each([
    ['11.2R24', '11.2R24'], ['7.50-20', '7.5R20'], ['12.00R20', '12R20'], ['16.9-28', '16.9R28'],
    ['17.5R25', '17.5R25'], ['10-16.5', '10R16.5'], ['18x7-8', '18X7-8'], ['28x9-15', '28X9-15'],
    ['250-15', '250-15'], ['10.5/80-18', '10.5/80R18'], ['16/70-20', '16/70R20'],
    ['600/65R34', '6006534'], ['440/80R28', '4408028'], ['185R14C', '185-14C'],
  ])('%s → %s', (input, key) => {
    expect(parseSize(input)?.key).toBe(key);
  });
  it('mantém jipe e ligeiros', () => {
    expect(parseSize('37x12.5-17')?.key).toBe('37X12.50R17');
    expect(parseSize('205/55-16')?.display).toBe('205/55R16');
    expect(parseSize('400/70-20')?.display).toBe('400/70-20');
  });
});
