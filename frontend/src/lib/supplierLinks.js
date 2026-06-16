// Constrói o URL de pesquisa do fornecedor para uma dada medida.
// Só o TugaPneus aceita medida no URL; os restantes abrem o portal/pesquisa (login necessário).
export function supplierSearchUrl(supplierName, medida) {
    const name = (supplierName || '').toLowerCase();
    const digits = (medida || '').replace(/[^0-9]/g, '');
    let slashed = (medida || '').trim();
    if (/^\d{7}$/.test(digits)) {
      slashed = `${digits.slice(0, 3)}/${digits.slice(3, 5)}R${digits.slice(5, 7)}`;
    }
    if (name.includes('tuga'))      return `https://www.tugapneus.pt/produtos?search=${encodeURIComponent(slashed)}`;
    if (name.includes('mp24'))      return 'https://pt.mp24.online/pt_PT/tyres/';
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