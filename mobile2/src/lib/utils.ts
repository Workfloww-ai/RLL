import { Metrics, Period } from '../types';

export function formatNumber(val: number): string {
  if (val === undefined || val === null) return '0';
  
  // Custom simple Indian numbering format formatting or basic local format
  // since Intl.NumberFormat might behave slightly differently across Hermes/React Native environments
  try {
    return new Intl.NumberFormat('en-IN', {
      maximumFractionDigits: 2,
      minimumFractionDigits: val % 1 !== 0 ? 2 : 0,
    }).format(val);
  } catch (e) {
    return val.toLocaleString();
  }
}

export function formatBL(val: number): string {
  if (val === undefined || val === null) return '0.0 BL';
  return `${formatNumber(val)} BL`;
}

export function calculateDateFactor(fromStr: string, toStr: string, period: Period): number {
  if (!fromStr || !toStr) return 1.0;
  
  const from = new Date(fromStr);
  const to = new Date(toStr);
  
  if (isNaN(from.getTime()) || isNaN(to.getTime()) || to < from) {
    return 1.0;
  }
  
  const diffTime = Math.abs(to.getTime() - from.getTime());
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1; // inclusive
  
  // Baseline days per period
  const periodBaselineDays = {
    Daily: 1,
    MTD: 24, // avg active working days in MTD
    YTD: 275  // avg active working days in YTD
  };
  
  const base = periodBaselineDays[period] || 1;
  const factor = diffDays / base;
  
  // Keep factor reasonable so values don't explode or collapse completely
  return Math.max(0.1, Math.min(factor, 3.5));
}

export function getScaledMetrics(metrics: Metrics, scaleFactor: number): Metrics {
  return {
    cases: Number((metrics.cases * scaleFactor).toFixed(2)),
    bottles: Math.round(metrics.bottles * scaleFactor),
    bl: Number((metrics.bl * scaleFactor).toFixed(1)),
  };
}

export function normalizeCompanyName(name: string): string {
  if (!name) return '';
  const lowered = name.trim().toLowerCase();
  if (
    lowered === 'diageo' ||
    lowered === 'inbrew' ||
    lowered === 'in brew' ||
    lowered === 'diageo/inbrew' ||
    lowered === 'diageo/in brew' ||
    lowered === 'diageo / inbrew' ||
    lowered === 'diageo / in brew' ||
    lowered === 'diageo inbrew' ||
    lowered === 'diageo in brew'
  ) {
    return 'Diageo/In brew';
  }
  if (
    lowered === 'rll' ||
    lowered === 'r.l.l.' ||
    lowered === 'rajasthan liquor limited' ||
    lowered === 'rajasthan liquors limited' ||
    lowered === 'rajasthan liquor' || 
    lowered === 'Rajasthan Liquors'
  ) {
    return 'Rajasthan Liquor Limited';
  }
  return name.trim();
}

export function normalizeCompanyList(rawCompanies: any[], pinnedCompanyName?: string, userCompanyName?: string): any[] {
  if (!Array.isArray(rawCompanies) || rawCompanies.length === 0) return rawCompanies;

  let source = rawCompanies;
  if (userCompanyName && userCompanyName.trim().toLowerCase() !== 'all') {
    const targetComp = userCompanyName.trim().toLowerCase();
    const matched = rawCompanies.filter(c => {
      const cName = (c?.name || c?.company_name || '').trim().toLowerCase();
      return cName === targetComp || cName.includes(targetComp) || targetComp.includes(cName);
    });
    if (matched.length > 0) {
      source = matched;
    }
  }

  const targetPinned = (pinnedCompanyName || userCompanyName || 'Rajasthan Liquor Limited').toLowerCase().trim();
  const map = new Map<string, any>();
  for (const c of source) {
    if (!c || !c.name) continue;
    const normName = normalizeCompanyName(c.name || '');
    const normId = normName.toLowerCase().replace(/\s+/g, '-').replace(/\//g, '-');

    const isMatchPinned = normName.toLowerCase().trim() === targetPinned || (targetPinned === 'rajasthan liquor limited' && normName === 'Diageo/In brew');

    if (!map.has(normId)) {
      map.set(normId, {
        ...c,
        id: normId,
        name: normName,
        isPinned: Boolean(c.isPinned || isMatchPinned),
        brands: [...(c.brands || [])],
        data: {
          Daily: { ...(c.data?.Daily || { cases: 0, bottles: 0, bl: 0 }) },
          MTD: { ...(c.data?.MTD || { cases: 0, bottles: 0, bl: 0 }) },
          YTD: { ...(c.data?.YTD || { cases: 0, bottles: 0, bl: 0 }) },
        }
      });
    } else {
      const existing = map.get(normId)!;
      // Merge brands without duplication
      const existingBrandIds = new Set(existing.brands.map((b: any) => b.id || b.brand_id || b.name || b.brand_name));
      for (const b of (c.brands || [])) {
        const bid = b.id || b.brand_id || b.name || b.brand_name;
        if (!existingBrandIds.has(bid)) {
          existing.brands.push(b);
          existingBrandIds.add(bid);
        }
      }
      // Merge metrics
      for (const p of ['Daily', 'MTD', 'YTD'] as Period[]) {
        const dSrc = c.data?.[p] || { cases: 0, bottles: 0, bl: 0 };
        const dDst = existing.data[p] || { cases: 0, bottles: 0, bl: 0 };
        dDst.cases = Number(((dDst.cases || 0) + (dSrc.cases || 0)).toFixed(2));
        dDst.bottles = Math.round((dDst.bottles || 0) + (dSrc.bottles || 0));
        dDst.bl = Number(((dDst.bl || 0) + (dSrc.bl || 0)).toFixed(1));
      }
    }
  }
  return Array.from(map.values());
}
