// Ligação ao portal do fornecedor para uma medida (size_key: 2055516, 2156516C, 3157022.5, 31X10.50R15).
// MP24 e TugaPneus abrem directamente os resultados; os restantes abrem a página de pesquisa
// e a medida é copiada para colar (o login no portal é do browser do utilizador).

const isTruck = (k) => /(?:17|19|22|24)\.5$/.test(k || '');

// Medida em números, como a escrevem os portais: 2055516, 31570225, 31105015.
export function compactSize(sizeKey) {
  const k = String(sizeKey || '').toUpperCase();
  const flot = k.match(/^(\d{2})X(\d{1,2})\.(\d{2})R(\d{2})$/);
  if (flot) return `${flot[1]}${flot[2].padStart(2, '0')}${flot[3]}${flot[4]}`;
  return k.replace(/[^0-9C]/g, '');
}

export function slashedSize(sizeKey) {
  const k = String(sizeKey || '').toUpperCase();
  const m = k.match(/^(\d{3})(\d{2})(\d{2}(?:\.5)?)(C?)$/);
  if (m) return `${m[1]}/${m[2]}R${m[3]}${m[4]}`;
  const f = k.match(/^(\d{2})X(\d{1,2}\.\d{2})R(\d{2})$/);
  if (f) return `${f[1]}x${f[2]}R${f[3]}`;
  return k;
}

export function supplierSearchUrl(supplierName, sizeKey) {
  const name = (supplierName || '').toLowerCase();
  const compact = compactSize(sizeKey);
  if (name.includes('tuga')) return `https://www.tugapneus.pt/produtos?search=${encodeURIComponent(slashedSize(sizeKey))}`;
  if (name.includes('mp24')) {
    const section = isTruck(sizeKey) ? 'truck' : 'car';
    return compact
      ? `https://pt.mp24.online/pt_PT/tyres2v0/${section}/result?matchcode=${encodeURIComponent(compact)}`
      : 'https://pt.mp24.online/pt_PT/tyres/';
  }
  if (name.includes('aguesport')) return 'https://encomendas.aguesport.com/';
  if (name.includes('cruzeiro'))  return 'https://www.pneuscruzeiro.pt/pt/privatearea?tab=produtos';
  if (name.includes('josé') || name.includes('jose')) return 'https://b2b.sjosepneus.com/articles/articles.aspx';
  if (name.includes('soledad'))   return 'https://b2b.current.gruposoledad.com/dashboard/main';
  if (name.includes('andres'))    return 'https://online.grupoandres.com/';
  if (name.includes('abtyres') || name.includes('abt')) return 'https://b2b.abtyres.pt/pneus';
  if (name.includes('prismanil')) return 'https://www.prismanil.pt/b2b/pesquisa';
  if (name.includes('inter'))     return 'https://customers.inter-sprint.nl/#ecommerce';
  return null;
}

// true quando o URL já abre os resultados da medida (não é preciso colar).
export function opensResults(supplierName) {
  const name = (supplierName || '').toLowerCase();
  return name.includes('tuga') || name.includes('mp24');
}
