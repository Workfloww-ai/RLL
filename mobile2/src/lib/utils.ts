import { Metrics, Period } from '../types';

export function formatNumber(val: number): string {
  if (val === undefined || val === null) return '0';
  
  // Custom simple Indian numbering format formatting or basic local format
  // since Intl.NumberFormat might behave slightly differently across Hermes/React Native environments
  try {
    return new Intl.NumberFormat('en-IN', {
      maximumFractionDigits: 1,
      minimumFractionDigits: val % 1 !== 0 ? 1 : 0,
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
    cases: Math.round(metrics.cases * scaleFactor),
    bottles: Math.round(metrics.bottles * scaleFactor),
    bl: Number((metrics.bl * scaleFactor).toFixed(1)),
  };
}
