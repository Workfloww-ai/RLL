/// <reference types="vite/client" />

export const getApiBaseUrl = (): string => {
  const envUrl = (import.meta as any).env?.VITE_API_URL;
  let url = '';

  if (envUrl && typeof envUrl === 'string' && envUrl.trim() !== '') {
    url = envUrl.trim().replace(/\/+$/, '');
    if (!url.endsWith('/api/v1')) {
      url = `${url}/api/v1`;
    }
    return url;
  }

  // If running on production/live domain, default directly to Google Cloud Run production backend
  if (typeof window !== 'undefined' && window.location && window.location.hostname) {
    const host = window.location.hostname;
    if (host !== 'localhost' && host !== '127.0.0.1') {
      return 'https://rll-backend-414899512001.asia-south2.run.app/api/v1';
    }
  }

  // Local development fallback
  const port = (import.meta as any).env?.VITE_API_PORT || '8000';
  return `http://localhost:${port}/api/v1`;
};

export const API_BASE_URL = getApiBaseUrl();
