/// <reference types="vite/client" />

export const getApiBaseUrl = (): string => {
  const envUrl = (import.meta as any).env?.VITE_API_URL;
  if (envUrl && typeof envUrl === 'string' && envUrl.trim() !== '') {
    let url = envUrl.trim().replace(/\/+$/, '');
    if (!url.endsWith('/api/v1')) {
      url = `${url}/api/v1`;
    }
    return url;
  }
  const port = (import.meta as any).env?.VITE_API_PORT || '8000';
  return `http://localhost:${port}/api/v1`;
};

export const API_BASE_URL = getApiBaseUrl();
