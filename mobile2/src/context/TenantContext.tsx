import React, { createContext, useContext, useState, useEffect } from 'react';
import { fetchTenantConfig, setTenantId } from '../lib/api';

export interface TenantConfig {
  tenantId: string;
  tenantSlug: string;
  appName: string;
  logoUrl: string;
  faviconUrl: string;
  splashScreenUrl: string;
  pinnedCompanyName: string;
  excludedCompanies: string[];
}

const defaultTenantConfig: TenantConfig = {
  tenantId: 'a0000000-0000-0000-0000-000000000001',
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
  updateWithUser: (user: any) => void;
  updateBranding: (branding: Partial<TenantConfig>) => void;
}

const TenantContext = createContext<TenantContextType>({
  config: defaultTenantConfig,
  loading: false,
  refreshConfig: async () => {},
  updateWithUser: () => {},
  updateBranding: () => {},
});

export const TenantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<TenantConfig>(defaultTenantConfig);
  const [loading, setLoading] = useState<boolean>(true);

  const updateWithUser = (user: any) => {
    if (!user) return;
    if (user.tenant_id) {
      setTenantId(user.tenant_id);
    }
    setConfig((prev) => ({
      ...prev,
      tenantId: user.tenant_id || prev.tenantId,
      appName: user.company_name || prev.appName,
      logoUrl: user.company_logo_url || prev.logoUrl,
      pinnedCompanyName: user.company_name || prev.pinnedCompanyName,
    }));
  };

  const updateBranding = (branding: Partial<TenantConfig>) => {
    if (!branding) return;
    setConfig((prev) => ({ ...prev, ...branding }));
  };

  const loadConfig = async () => {
    try {
      const data = await fetchTenantConfig();
      if (data && data.status === 'success') {
        const resolvedTenantId = data.tenant_id || 'a0000000-0000-0000-0000-000000000001';
        setTenantId(resolvedTenantId);
        setConfig((prev) => ({
          ...prev,
          tenantId: resolvedTenantId,
          tenantSlug: data.tenant_slug || prev.tenantSlug,
          appName: prev.appName !== defaultTenantConfig.appName ? prev.appName : (data.app_name || 'LucidX360'),
          logoUrl: prev.logoUrl || data.logo_url || '',
          faviconUrl: data.favicon_url || '',
          splashScreenUrl: data.splash_screen_url || '',
          pinnedCompanyName: prev.pinnedCompanyName !== defaultTenantConfig.pinnedCompanyName ? prev.pinnedCompanyName : (data.pinned_company_name || ''),
          excludedCompanies: data.excluded_companies || ['Others'],
        }));
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
    <TenantContext.Provider value={{ config, loading, refreshConfig: loadConfig, updateWithUser, updateBranding }}>
      {children}
    </TenantContext.Provider>
  );
};

export const useTenant = () => useContext(TenantContext);
