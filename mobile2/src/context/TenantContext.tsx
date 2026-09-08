import React, { createContext, useContext, useState, useEffect } from 'react';
import { fetchTenantConfig } from '../lib/api';

export interface TenantConfig {
  tenantSlug: string;
  appName: string;
  logoUrl: string;
  faviconUrl: string;
  splashScreenUrl: string;
  pinnedCompanyName: string;
  excludedCompanies: string[];
}

const defaultTenantConfig: TenantConfig = {
  tenantSlug: 'rll',
  appName: 'LucidX360',
  logoUrl: '',
  faviconUrl: '',
  splashScreenUrl: '',
  pinnedCompanyName: 'Rajasthan Liquor Limited',
  excludedCompanies: ['Others'],
};

interface TenantContextType {
  config: TenantConfig;
  loading: boolean;
  refreshConfig: () => Promise<void>;
}

const TenantContext = createContext<TenantContextType>({
  config: defaultTenantConfig,
  loading: false,
  refreshConfig: async () => {},
});

export const TenantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<TenantConfig>(defaultTenantConfig);
  const [loading, setLoading] = useState<boolean>(true);

  const loadConfig = async () => {
    try {
      const data = await fetchTenantConfig();
      if (data && data.status === 'success') {
        setConfig({
          tenantSlug: data.tenant_slug || 'rll',
          appName: data.app_name || 'LucidX360',
          logoUrl: data.logo_url || '',
          faviconUrl: data.favicon_url || '',
          splashScreenUrl: data.splash_screen_url || '',
          pinnedCompanyName: data.pinned_company_name || '',
          excludedCompanies: data.excluded_companies || ['Others'],
        });
      }
    } catch (e) {
      console.warn('TenantProvider: Could not load tenant config, using defaults:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  return (
    <TenantContext.Provider value={{ config, loading, refreshConfig: loadConfig }}>
      {children}
    </TenantContext.Provider>
  );
};

export const useTenant = () => useContext(TenantContext);
