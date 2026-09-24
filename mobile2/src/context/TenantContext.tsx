import React, { createContext, useContext, useState, useEffect } from 'react';
import { fetchTenantConfig, setTenantId } from '../lib/api';
import { FastStorage } from '../lib/storage';

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
  appName: 'Rajasthan Liquor Limited',
  logoUrl: '',
  faviconUrl: '',
  splashScreenUrl: '',
  pinnedCompanyName: 'Rajasthan Liquor Limited',
  excludedCompanies: [],
};

function getInitialTenantConfig(): TenantConfig {
  try {
    const cached = FastStorage.getObject<TenantConfig>('rll_tenant_config');
    if (cached && cached.tenantId) {
      if (cached.tenantId) setTenantId(cached.tenantId);
      return {
        ...cached,
        appName: (cached.appName && cached.appName !== 'LucidX360') ? cached.appName : 'Rajasthan Liquor Limited',
        pinnedCompanyName: cached.pinnedCompanyName || 'Rajasthan Liquor Limited',
      };
    }
    const cachedUser = FastStorage.getObject<any>('rll_user_session');
    if (cachedUser && (cachedUser.company_name || cachedUser.tenant_id)) {
      if (cachedUser.tenant_id) setTenantId(cachedUser.tenant_id);
      return {
        ...defaultTenantConfig,
        tenantId: cachedUser.tenant_id || defaultTenantConfig.tenantId,
        appName: cachedUser.company_name || 'Rajasthan Liquor Limited',
        pinnedCompanyName: cachedUser.company_name || 'Rajasthan Liquor Limited',
      };
    }
  } catch (e) {
    // Fallback to default config
  }
  return defaultTenantConfig;
}

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
  const [config, setConfig] = useState<TenantConfig>(getInitialTenantConfig);
  const [loading, setLoading] = useState<boolean>(false);

  const updateWithUser = (user: any) => {
    if (!user) return;
    if (user.tenant_id) {
      setTenantId(user.tenant_id);
    }
    setConfig((prev) => {
      const nextConfig = {
        ...prev,
        tenantId: user.tenant_id || prev.tenantId,
        appName: user.company_name || prev.appName || 'Rajasthan Liquor Limited',
        logoUrl: user.company_logo_url || prev.logoUrl,
        pinnedCompanyName: user.company_name || prev.pinnedCompanyName || 'Rajasthan Liquor Limited',
      };
      FastStorage.setObject('rll_tenant_config', nextConfig);
      return nextConfig;
    });
  };

  const updateBranding = (branding: Partial<TenantConfig>) => {
    if (!branding) return;
    setConfig((prev) => {
      const nextConfig = { ...prev, ...branding };
      FastStorage.setObject('rll_tenant_config', nextConfig);
      return nextConfig;
    });
  };

  const loadConfig = async () => {
    try {
      const data = await fetchTenantConfig();
      if (data && data.status === 'success') {
        const resolvedTenantId = data.tenant_id || 'a0000000-0000-0000-0000-000000000001';
        setTenantId(resolvedTenantId);
        setConfig((prev) => {
          const rawAppName = data.app_name;
          const resolvedAppName = (rawAppName && rawAppName !== 'LucidX360')
            ? rawAppName
            : (prev.appName && prev.appName !== 'LucidX360' ? prev.appName : 'Rajasthan Liquor Limited');

          const nextConfig = {
            ...prev,
            tenantId: resolvedTenantId,
            tenantSlug: data.tenant_slug || prev.tenantSlug,
            appName: resolvedAppName,
            logoUrl: prev.logoUrl || data.logo_url || '',
            faviconUrl: data.favicon_url || '',
            splashScreenUrl: data.splash_screen_url || '',
            pinnedCompanyName: data.pinned_company_name || (prev.pinnedCompanyName !== defaultTenantConfig.pinnedCompanyName ? prev.pinnedCompanyName : 'Rajasthan Liquor Limited'),
            excludedCompanies: Array.isArray(data.excluded_companies) ? data.excluded_companies : [],
          };
          FastStorage.setObject('rll_tenant_config', nextConfig);
          return nextConfig;
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
    <TenantContext.Provider value={{ config, loading, refreshConfig: loadConfig, updateWithUser, updateBranding }}>
      {children}
    </TenantContext.Provider>
  );
};

export const useTenant = () => useContext(TenantContext);
