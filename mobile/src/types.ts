export type Period = 'Daily' | 'MTD' | 'YTD';

export interface Metrics {
  cases: number;
  bottles: number;
  bl: number;
}

export interface Brand {
  id: string;
  name: string;
  category?: string;
  data: Record<Period, Metrics>;
}

export interface Company {
  id: string;
  name: string;
  isPinned: boolean;
  category?: string;
  hqLocation?: string;
  data: Record<Period, Metrics>;
  brands: Brand[];
}

export interface DepotBrandSales {
  brandId: string;
  brandName: string;
  data: Record<Period, Metrics>;
}

export interface Depot {
  id: string;
  name: string;
  hqName: string;
  address?: string;
  data: Record<Period, Metrics>;
  brands: DepotBrandSales[];
}

export interface TsmBrandSales {
  brandId: string;
  brandName: string;
  data: Record<Period, Metrics>;
}

export interface TSM {
  id: string;
  name: string;
  hqLocation?: string;
  data: Record<Period, Metrics>;
  brands: TsmBrandSales[];
}

export type ViewMode = 'companies' | 'depots' | 'tsm' | 'profile';

export interface DateRange {
  from: string;
  to: string;
}
