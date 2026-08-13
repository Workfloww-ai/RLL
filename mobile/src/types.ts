export type Period = 'Daily' | 'MTD' | 'YTD';

export interface Metrics {
  cases: number;
  bottles: number;
  bl: number;
}

export interface Brand {
  id: string;
  name: string;
  brand_id?: string;
  brand_name?: string;
  company_id?: string;
  is_active?: boolean;
  created_at?: string;
  category?: string;
  data: Record<Period, Metrics>;
}

export interface Company {
  id: string;
  name: string;
  company_id?: string;
  company_name?: string;
  is_active?: boolean;
  created_at?: string;
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

export interface ASEInfo {
  id: string;
  name: string;
  data: Record<Period, Metrics>;
}

export interface TSM {
  id: string;
  name: string;
  hqLocation?: string;
  ases?: ASEInfo[];
  data: Record<Period, Metrics>;
  brands: TsmBrandSales[];
}

export type ViewMode = 'companies' | 'depots' | 'tsm' | 'groups' | 'profile';

export interface GroupCascading {
  group_id: string;
  group_name: string;
  total_licensees: number;
  linked_depots: string[];
  total_cases: number;
  total_bottles: number;
}

export interface LicenseeCascading {
  licensee_id: string;
  licensee_name: string;
  trade: string;
  licensee_depots: string[];
  total_cases: number;
  total_bottles: number;
}

export interface BrandSaleCascading {
  brand_id: string;
  brand_name: string;
  company_name: string;
  total_cases: number;
  total_bottles: number;
  sales_depots: string[];
}

export interface DateRange {
  from: string;
  to: string;
}

