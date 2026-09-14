import { useState, useEffect } from 'react';
import { setTenantId } from '../lib/apiClient';

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
  logoUrl: '/images/rll logo.svg',
  faviconUrl: '',
  splashScreenUrl: '',
  pinnedCompanyName: 'Rajasthan Liquor Limited',
  excludedCompanies: ['Others'],
};

export function useTenantConfig() {
  const [config, setConfig] = useState<TenantConfig>(defaultTenantConfig);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let isMounted = true;
    async function loadTenantConfig() {
      try {
        const backendUrl = import.meta.env.VITE_API_URL || '';
        const res = await fetch(`${backendUrl}/api/v1/system/tenant/config?tenant_slug=rll`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted && data) {
            const resolvedId = data.tenant_id || 'a0000000-0000-0000-0000-000000000001';
            setTenantId(resolvedId);

            setConfig({
              tenantId: resolvedId,
              tenantSlug: data.tenant_slug || 'rll',
              appName: data.app_name || 'LucidX360',
              logoUrl: data.logo_url || '/images/rll logo.svg',
              faviconUrl: data.favicon_url || '',
              splashScreenUrl: data.splash_screen_url || '',
              pinnedCompanyName: data.pinned_company_name || '',
              excludedCompanies: data.excluded_companies || ['Others'],
            });

            // Dynamically update document title and favicon if provided
            if (data.app_name) {
              document.title = `${data.app_name} Admin Portal`;
            }
            if (data.favicon_url) {
              const link: HTMLLinkElement | null = document.querySelector("link[rel*='icon']");
              if (link) {
                link.href = data.favicon_url;
              }
            }
          }
        }
      } catch (e) {
        console.warn('useTenantConfig error:', e);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadTenantConfig();
    return () => {
      isMounted = false;
    };
  }, []);

  return { config, loading };
}
