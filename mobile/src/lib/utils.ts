import { Metrics, Period, Company } from '../types';

export function formatNumber(val: number): string {
  if (val === undefined || val === null) return '0';
  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: 1,
    minimumFractionDigits: val % 1 !== 0 ? 1 : 0,
  }).format(val);
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
    cases: Math.round(metrics.cases * scaleFactor),
    bottles: Math.round(metrics.bottles * scaleFactor),
    bl: Number((metrics.bl * scaleFactor).toFixed(1)),
  };
}

export function exportCompanyDataToCSV(companies: Company[], period: Period, dateFrom: string, dateTo: string) {
  let csvContent = `data:text/csv;charset=utf-8,`;
  csvContent += `RAJASTHAN LIQUORS LIMITED - SALES DASHBOARD REPORT\n`;
  csvContent += `Period: ${period} | Date Range: ${dateFrom} to ${dateTo}\n`;
  csvContent += `Generated At: ${new Date().toLocaleString()}\n\n`;
  csvContent += `Company Name,Category,Pinned,Total Cases,Total Bottles,Volume (BL),Active Brands Count\n`;

  companies.forEach((comp) => {
    const data = comp.data[period];
    const cleanName = `"${comp.name.replace(/"/g, '""')}"`;
    const cleanCategory = `"${(comp.category || '').replace(/"/g, '""')}"`;
    csvContent += `${cleanName},${cleanCategory},${comp.isPinned ? 'Yes' : 'No'},${data.cases},${data.bottles},${data.bl},${comp.brands.length}\n`;

    // Add brands sub-section
    comp.brands.forEach((b) => {
      const bData = b.data[period];
      const cleanBName = `  ↳ "${b.name.replace(/"/g, '""')}"`;
      const cleanBCat = `"${(b.category || '').replace(/"/g, '""')}"`;
      csvContent += `${cleanBName},${cleanBCat},-,${bData.cases},${bData.bottles},${bData.bl},1\n`;
    });
  });

  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `RLL_Sales_Dashboard_${period}_${dateFrom}_to_${dateTo}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
