/// <reference types="vite/client" />

export const getApiBaseUrl = (): string => {
  const envUrl = (import.meta as any).env?.VITE_API_URL;
  let url = '';
  if (envUrl && typeof envUrl === 'string' && envUrl.trim() !== '') {
    url = envUrl.trim().replace(/\/+$/, '');
    if (!url.endsWith('/api/v1')) {
      url = `${url}/api/v1`;
    }
  } else {
    const port = (import.meta as any).env?.VITE_API_PORT || '8000';
    url = `http://localhost:${port}/api/v1`;
  }

  // If in browser and URL targets localhost/127.0.0.1, dynamically use active window hostname
  if (typeof window !== 'undefined' && window.location && window.location.hostname) {
    const host = window.location.hostname;
    if (host !== 'localhost' && host !== '127.0.0.1') {
      url = url.replace('localhost', host).replace('127.0.0.1', host);
    }
  }

  return url;
};

export const API_BASE_URL = getApiBaseUrl();
