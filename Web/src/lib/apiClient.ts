import CryptoJS from 'crypto-js';

const ENVIRONMENT = import.meta.env.VITE_ENVIRONMENT || 'development';
const ENCRYPTION_KEY = import.meta.env.VITE_PAYLOAD_ENCRYPTION_KEY || '';

// Active tenant state
let activeTenantId: string = (() => {
  try {
    return localStorage.getItem('rll_tenant_id') || 'a0000000-0000-0000-0000-000000000001';
  } catch {
    return 'a0000000-0000-0000-0000-000000000001';
  }
})();

export function getTenantId(): string {
  return activeTenantId;
}

export function setTenantId(id: string): void {
  if (id && typeof id === 'string') {
    activeTenantId = id;
    try {
      localStorage.setItem('rll_tenant_id', id);
    } catch {
      // Ignore localStorage write failures in private browsing
    }
  }
}

export function encryptPayload(data: string): string {
    if (!ENCRYPTION_KEY || ENCRYPTION_KEY.length !== 64) {
        console.error("Invalid VITE_PAYLOAD_ENCRYPTION_KEY length. Expected 64 characters.");
        return data;
    }
    try {
        const key = CryptoJS.enc.Hex.parse(ENCRYPTION_KEY);
        const iv = CryptoJS.lib.WordArray.random(16);
        const encrypted = CryptoJS.AES.encrypt(data, key, {
            iv: iv,
            mode: CryptoJS.mode.CBC,
            padding: CryptoJS.pad.Pkcs7
        });
        const ivAndCiphertext = iv.clone().concat(encrypted.ciphertext);
        return CryptoJS.enc.Base64.stringify(ivAndCiphertext);
    } catch (e) {
        console.error("Encryption failed", e);
        return data;
    }
}

export function decryptPayload(encryptedB64: string): string {
    if (!ENCRYPTION_KEY || ENCRYPTION_KEY.length !== 64) {
        console.error("Invalid VITE_PAYLOAD_ENCRYPTION_KEY length. Expected 64 characters.");
        return encryptedB64;
    }
    try {
        const key = CryptoJS.enc.Hex.parse(ENCRYPTION_KEY);
        const encryptedWords = CryptoJS.enc.Base64.parse(encryptedB64);
        
        const iv = CryptoJS.lib.WordArray.create(encryptedWords.words.slice(0, 4), 16);
        const ciphertext = CryptoJS.lib.WordArray.create(encryptedWords.words.slice(4), encryptedWords.sigBytes - 16);
        const cipherParams = CryptoJS.lib.CipherParams.create({ ciphertext: ciphertext });
        
        const decrypted = CryptoJS.AES.decrypt(cipherParams, key, {
            iv: iv,
            mode: CryptoJS.mode.CBC,
            padding: CryptoJS.pad.Pkcs7
        });
        return decrypted.toString(CryptoJS.enc.Utf8);
    } catch (e) {
        console.error("Decryption failed", e);
        return encryptedB64;
    }
}

/**
 * Injects tenant_id into request options:
 * 1. Attaches X-Tenant-ID header
 * 2. Injects tenant_id into JSON request body if present
 * 3. Appends tenant_id as query parameter to the URL
 */
export function injectTenantContext(url: string, options: RequestInit = {}): { url: string; options: RequestInit } {
    const tenantId = getTenantId();
    const reqOptions: RequestInit = { ...options };

    // 1. Headers injection
    const headers: Record<string, string> = {
        ...(options.headers as Record<string, string> || {}),
        'X-Tenant-ID': tenantId,
    };
    reqOptions.headers = headers;

    // 2. Body injection (POST, PUT, PATCH with JSON)
    const method = (reqOptions.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && reqOptions.body) {
        if (typeof reqOptions.body === 'string') {
            try {
                const parsed = JSON.parse(reqOptions.body);
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    if (!parsed.tenant_id && !parsed.tenantId) {
                        parsed.tenant_id = tenantId;
                        reqOptions.body = JSON.stringify(parsed);
                    }
                }
            } catch {
                // Not standard JSON string, leave unchanged
            }
        }
    }

    // 3. Query parameter injection
    let finalUrl = url;
    try {
        const isRelative = !url.startsWith('http://') && !url.startsWith('https://');
        const dummyBase = 'http://localhost';
        const parsedUrl = new URL(url, dummyBase);
        if (!parsedUrl.searchParams.has('tenant_id')) {
            parsedUrl.searchParams.set('tenant_id', tenantId);
            finalUrl = isRelative
                ? `${parsedUrl.pathname}${parsedUrl.search}${parsedUrl.hash}`
                : parsedUrl.toString();
        }
    } catch {
        if (!url.includes('tenant_id=')) {
            const separator = url.includes('?') ? '&' : '?';
            finalUrl = `${url}${separator}tenant_id=${encodeURIComponent(tenantId)}`;
        }
    }

    return { url: finalUrl, options: reqOptions };
}

export async function secureFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const isProduction = ENVIRONMENT === 'production';
    const { url: enrichedUrl, options: enrichedOptions } = injectTenantContext(url, options);

    // Encrypt request body if applicable
    if (isProduction && enrichedOptions.body && typeof enrichedOptions.body === 'string') {
        const encrypted = encryptPayload(enrichedOptions.body);
        enrichedOptions.body = JSON.stringify({ encrypted_data: encrypted });
        
        if (!enrichedOptions.headers) enrichedOptions.headers = {};
        (enrichedOptions.headers as Record<string, string>)['Content-Type'] = 'application/json';
    }

    const response = await fetch(enrichedUrl, enrichedOptions);

    // If production, decrypt response body if it's encrypted
    if (isProduction && response.ok) {
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            const responseClone = response.clone();
            const text = await responseClone.text();
            
            try {
                const json = JSON.parse(text);
                if (json.encrypted_data) {
                    const decryptedStr = decryptPayload(json.encrypted_data);
                    
                    return new Response(decryptedStr, {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers
                    });
                }
            } catch (e) {
                console.warn("Failed to parse or decrypt response", e);
            }
        }
    }

    return response;
}

// ── Web Refresh Mutex (Single-Flight Lock) ─────────────────────────
let _webRefreshPromise: Promise<string | null> | null = null;

export async function refreshWebToken(): Promise<string | null> {
    if (_webRefreshPromise) {
        return _webRefreshPromise;
    }

    _webRefreshPromise = (async () => {
        try {
            const refreshToken = localStorage.getItem('refresh_token');
            const tenantId = getTenantId();
            
            // Resolve API base URL for refresh
            let refreshUrl = '/api/v1/auth/refresh';
            if (typeof window !== 'undefined' && (window as any).API_BASE_URL) {
                refreshUrl = `${(window as any).API_BASE_URL}/auth/refresh`;
            }

            const originalFetch = (window as any).__originalFetch || window.fetch;
            const res = await originalFetch(`${refreshUrl}?tenant_id=${encodeURIComponent(tenantId)}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Tenant-ID': tenantId,
                },
                credentials: 'include',
                body: JSON.stringify({ refresh_token: refreshToken || undefined }),
            });

            if (!res.ok) {
                return null;
            }

            const data = await res.json();
            if (data?.access_token) {
                localStorage.setItem('token', data.access_token);
                if (data.refresh_token) {
                    localStorage.setItem('refresh_token', data.refresh_token);
                }
                if (data.user) {
                    localStorage.setItem('user', JSON.stringify(data.user));
                }
                return data.access_token;
            }
            return null;
        } catch (e) {
            console.warn('Web token refresh exception:', e);
            return null;
        } finally {
            _webRefreshPromise = null;
        }
    })();

    return _webRefreshPromise;
}

// Global fetch interceptor to guarantee 100% of API calls include tenant_id, auth, and rolling refresh
if (typeof window !== 'undefined' && window.fetch) {
    const originalFetch = window.fetch;
    (window as any).__originalFetch = originalFetch;

    window.fetch = async function(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
        let inputUrl = typeof input === 'string' ? input : (input instanceof Request ? input.url : String(input));

        if (inputUrl.includes('/api/v1') || inputUrl.includes('/api/')) {
            const { url, options } = injectTenantContext(inputUrl, init || {});

            // 1. Auto-attach credentials: 'include' for session cookies
            if (!options.credentials) {
                options.credentials = 'include';
            }

            // 2. Auto-attach Authorization: Bearer <token> if present in localStorage
            const token = localStorage.getItem('token');
            if (token) {
                const hdrs = (options.headers as Record<string, string>) || {};
                if (!hdrs['Authorization'] && !hdrs['authorization']) {
                    hdrs['Authorization'] = `Bearer ${token}`;
                    options.headers = hdrs;
                }
            }

            const response = await originalFetch.call(this, url, options);

            // 3. Handle 401 Unauthorized with automatic sliding refresh
            const isAuthRoute = url.includes('/auth/login') ||
                                url.includes('/auth/refresh') ||
                                url.includes('/auth/forgot-password') ||
                                url.includes('/auth/reset-password');

            if (response.status === 401 && !isAuthRoute) {
                const newAccessToken = await refreshWebToken();
                if (newAccessToken) {
                    // Retry with updated Bearer token
                    const retryOptions = { ...options };
                    const retryHeaders = { ...(retryOptions.headers as Record<string, string> || {}) };
                    retryHeaders['Authorization'] = `Bearer ${newAccessToken}`;
                    retryOptions.headers = retryHeaders;
                    return originalFetch.call(this, url, retryOptions);
                } else {
                    // Refresh token expired after 30 days inactivity or revoked
                    localStorage.removeItem('token');
                    localStorage.removeItem('refresh_token');
                    localStorage.removeItem('user');
                    localStorage.removeItem('user_name');
                    window.dispatchEvent(new Event('rll:session_expired'));
                }
            }

            return response;
        }
        return originalFetch.call(this, input, init);
    };
}
