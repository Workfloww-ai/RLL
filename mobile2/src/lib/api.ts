import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { logger } from './logger';

function formatBaseUrl(url: string): string {
  let formatted = url.trim();
  if (!formatted.startsWith('http://') && !formatted.startsWith('https://')) {
    formatted = `http://${formatted}`;
  }
  formatted = formatted.replace(/\/+$/, '');
  if (!formatted.endsWith('/api/v1')) {
    formatted = `${formatted}/api/v1`;
  }
  return formatted;
}

export function getApiBaseUrl(): string {
  // 1. Native Expo public environment variable
  const envUrl = process.env.EXPO_PUBLIC_API_URL;
  if (envUrl && envUrl !== 'undefined' && envUrl.trim() !== '') {
    return formatBaseUrl(envUrl);
  }

  // Configurable backend port (defaults to 8000 if not specified)
  const port = process.env.EXPO_PUBLIC_API_PORT || process.env.EXPO_PUBLIC_PORT || '8000';

  // 2. Automatically derive computer's host IP from Metro bundler hostUri (works for physical devices & emulators)
  const hostUri = Constants.expoConfig?.hostUri || Constants.manifest2?.extra?.expoGo?.developer?.tool;
  if (hostUri) {
    const hostIp = hostUri.split(':')[0];
    if (hostIp && hostIp !== 'localhost' && hostIp !== '127.0.0.1') {
      return `http://${hostIp}:${port}/api/v1`;
    }
  }

  // 3. Fallback to localhost (for ADB reverse tcp or iOS Simulator)
  return `http://localhost:${port}/api/v1`;
}

export const BASE_URL = getApiBaseUrl();

export async function apiFetch(endpointPath: string, init?: RequestInit): Promise<Response> {
  const cleanPath = endpointPath.startsWith('/') ? endpointPath : `/${endpointPath}`;
  const url = `${BASE_URL}${cleanPath}`;

  const reqInit: RequestInit = { ...(init || {}) };
  const token = await getAuthToken();
  if (token) {
    const headers = new Headers(reqInit.headers || {});
    if (!headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    reqInit.headers = headers;
  }

  logger.info(`apiFetch: ${reqInit.method || 'GET'} ${url}`);
  try {
    return await fetch(url, reqInit);
  } catch (err: any) {
    const isAbort =
      err?.name === 'AbortError' ||
      (err?.message && (
        err.message.toLowerCase().includes('canceled') ||
        err.message.toLowerCase().includes('cancelled') ||
        err.message.toLowerCase().includes('aborted')
      ));
    if (isAbort) {
      throw err;
    }
    if (err?.message && (err.message.includes('ConnectException') || err.message.includes('Network request failed'))) {
      throw new Error(`Cannot connect to server at ${BASE_URL}. Please ensure the backend server is running.`);
    }
    throw err;
  }
}

// ── Auth Token Cache ────────────────────────────────────────────────────────
// Avoids repeated AsyncStorage disk reads on every API call after first load.
let _cachedToken: string | null = null;

export async function getAuthToken(): Promise<string | null> {
  if (_cachedToken !== null) return _cachedToken;
  _cachedToken = await AsyncStorage.getItem('rll_mobile_token');
  return _cachedToken;
}

export function seedCachedToken(token: string): void {
  _cachedToken = token;
}

export function clearCachedToken(): void {
  _cachedToken = null;
}

// ── API Response Cache (Persistent L1 Memory + AsyncStorage) ──────────────────
const _apiCache = new Map<string, { data: unknown; expiry: number }>();
const DISK_CACHE_PREFIX = 'rll_disk_cache::';

/**
 * Hydrates in-memory cache from persistent AsyncStorage on app startup.
 * Enables 0ms instantaneous mounting even across cold app restarts.
 */
export async function hydratePersistentCache(): Promise<void> {
  try {
    const keys = await AsyncStorage.getAllKeys();
    const cacheKeys = keys.filter(k => k.startsWith(DISK_CACHE_PREFIX));
    if (cacheKeys.length === 0) return;
    const pairs = await AsyncStorage.multiGet(cacheKeys);
    for (const [key, val] of pairs) {
      if (val) {
        try {
          const parsed = JSON.parse(val);
          if (parsed && parsed.expiry > Date.now()) {
            const memoryKey = key.replace(DISK_CACHE_PREFIX, '');
            _apiCache.set(memoryKey, parsed);
          } else {
            AsyncStorage.removeItem(key).catch(() => {});
          }
        } catch (_) {}
      }
    }
    logger.info(`hydratePersistentCache: Hydrated ${_apiCache.size} persistent cache entries from AsyncStorage.`);
  } catch (err) {
    logger.warn('Failed to hydrate persistent cache from AsyncStorage', err);
  }
}

/**
 * Synchronously checks if a cached response payload exists in memory or disk.
 */
export function getCachedSnapshot<T = unknown>(endpointPath: string, authToken?: string): T | null {
  const cacheKey = `${endpointPath}::${authToken ?? ''}`;
  const cached = _apiCache.get(cacheKey);
  if (cached) return cached.data as T;
  return null;
}

/**
 * Caches GET responses in memory and persistent AsyncStorage.
 * Returns cached snapshot in 0ms while supporting background revalidation.
 */
export async function apiFetchCached(
  endpointPath: string,
  ttlMs: number = 60_000,
  authToken?: string
): Promise<unknown> {
  const cacheKey = `${endpointPath}::${authToken ?? ''}`;
  const cached = _apiCache.get(cacheKey);

  // 1. Memory HIT (0ms)
  if (cached && Date.now() < cached.expiry) {
    logger.info(`apiFetchCached: memory HIT — ${endpointPath}`);
    return cached.data;
  }

  // 2. Disk HIT (fallback read if memory empty)
  if (!cached) {
    try {
      const diskVal = await AsyncStorage.getItem(`${DISK_CACHE_PREFIX}${cacheKey}`);
      if (diskVal) {
        const parsed = JSON.parse(diskVal);
        if (parsed && Date.now() < parsed.expiry) {
          _apiCache.set(cacheKey, parsed);
          logger.info(`apiFetchCached: disk HIT — ${endpointPath}`);
          return parsed.data;
        }
      }
    } catch (_) {}
  }

  // 3. Network Fetch
  const headers: Record<string, string> = {};
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  const res = await apiFetch(endpointPath, { headers });
  if (!res.ok) {
    if (res.status === 401) {
      logger.warn(`apiFetchCached: Auth token expired (HTTP 401) on ${endpointPath}. Clearing stale credentials.`);
      AsyncStorage.removeItem('rll_mobile_token').catch(() => {});
      AsyncStorage.removeItem('rll_mobile_user').catch(() => {});
      clearCachedToken();
    }
    throw new Error(`apiFetchCached: ${res.status} for ${endpointPath}`);
  }
  const data = await res.json();
  const cacheEntry = { data, expiry: Date.now() + ttlMs };
  _apiCache.set(cacheKey, cacheEntry);
  AsyncStorage.setItem(`${DISK_CACHE_PREFIX}${cacheKey}`, JSON.stringify(cacheEntry)).catch(() => {});
  return data;
}

export function invalidateApiCache(pathPrefix?: string): void {
  if (!pathPrefix) {
    _apiCache.clear();
    AsyncStorage.getAllKeys().then(keys => {
      const cacheKeys = keys.filter(k => k.startsWith(DISK_CACHE_PREFIX));
      if (cacheKeys.length > 0) AsyncStorage.multiRemove(cacheKeys).catch(() => {});
    }).catch(() => {});
    return;
  }
  for (const key of _apiCache.keys()) {
    if (key.startsWith(pathPrefix)) {
      _apiCache.delete(key);
      AsyncStorage.removeItem(`${DISK_CACHE_PREFIX}${key}`).catch(() => {});
    }
  }
}


export async function sendMobileOTP(phone: string, email: string = '') {
  logger.info(`sendMobileOTP: Requesting OTP for phone: ${phone}, email: ${email}`);
  try {
    const res = await apiFetch('/mobile/send-otp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ phone, email }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      const errMsg = errorData.detail || 'Failed to send OTP verification code.';
      logger.warn(`sendMobileOTP: API returned error status ${res.status}: ${errMsg}`);
      throw new Error(errMsg);
    }

    const data = await res.json();
    logger.info(`sendMobileOTP: Success for phone: ${phone}`);
    return data;
  } catch (error) {
    logger.error(`sendMobileOTP: Exception while requesting OTP for phone: ${phone}`, error);
    throw error;
  }
}

export async function verifyMobileOTP(phone: string, otp: string, email: string = '') {
  logger.info(`verifyMobileOTP: Verifying OTP code for phone: ${phone}`);
  try {
    const res = await apiFetch('/mobile/verify-otp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ phone, otp, email }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      const errMsg = errorData.detail || 'Invalid or expired 6-digit OTP code.';
      logger.warn(`verifyMobileOTP: API returned error status ${res.status}: ${errMsg}`);
      throw new Error(errMsg);
    }

    const data = await res.json();
    if (data.access_token) {
      await AsyncStorage.setItem('rll_mobile_token', data.access_token);
      await AsyncStorage.setItem('rll_mobile_user', JSON.stringify(data.user));
      seedCachedToken(data.access_token);
    }
    logger.info(`verifyMobileOTP: Success. Token acquired for phone: ${phone}`);
    return data;
  } catch (error) {
    logger.error(`verifyMobileOTP: Exception while verifying OTP for phone: ${phone}`, error);
    throw error;
  }
}

export async function loginMobileUser(email: string, password: string) {
  logger.info(`loginMobileUser: Authenticating email: ${email}`);
  try {
    const res = await apiFetch('/mobile/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      const errMsg = errorData.detail || 'Authentication failed. Invalid email or password.';
      logger.warn(`loginMobileUser: API returned error status ${res.status}: ${errMsg}`);
      throw new Error(errMsg);
    }

    const data = await res.json();
    if (data.access_token) {
      await AsyncStorage.setItem('rll_mobile_token', data.access_token);
      await AsyncStorage.setItem('rll_mobile_user', JSON.stringify(data.user));
      seedCachedToken(data.access_token);
    }
    logger.info(`loginMobileUser: Success. Session loaded for email: ${email}`);
    return data;
  } catch (error) {
    logger.error(`loginMobileUser: Exception while authenticating email: ${email}`, error);
    throw error;
  }
}

let activeSalesAbortController: AbortController | null = null;
let activeCompaniesAbortController: AbortController | null = null;

export async function fetchMobileSales(
  dateFrom: string,
  dateTo: string,
  period: string,
  selectedHq: string = 'All Headquarters',
  testLimit?: number
) {
  const token = await getAuthToken();
  if (!token) {
    logger.warn('fetchMobileSales: Missing authentication token.');
    return null;
  }

  // Cancel previous in-flight sales request if filters change rapidly
  if (activeSalesAbortController) {
    activeSalesAbortController.abort();
    logger.info('fetchMobileSales: Aborted previous in-flight sales request due to filter update.');
  }
  activeSalesAbortController = new AbortController();
  const signal = activeSalesAbortController.signal;

  const requestId = `req_${Math.random().toString(36).substring(2, 10)}`;
  const now = () => Date.now();
  const tRequestStart = now();

  try {
    const queryParams: Record<string, string> = {
      date_from: dateFrom,
      date_to: dateTo,
      period,
      selected_hq: selectedHq,
    };
    if (testLimit) {
      queryParams['test_limit'] = String(testLimit);
    }

    const query = new URLSearchParams(queryParams);
    const endpoint = `/mobile/sales?${query.toString()}`;
    const cleanPath = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${BASE_URL}${cleanPath}`;

    logger.info(`🚀 [MOBILE_REQUEST_START] Request ID: ${requestId} → GET ${url}`);

    const headers: Record<string, string> = {
      'Authorization': `Bearer ${token}`,
      'X-Request-ID': requestId,
    };

    const res = await fetch(url, { headers, signal });
    const tResponseReceived = now();
    const networkDurationMs = Math.round(tResponseReceived - tRequestStart);

    if (!res.ok) {
      if (res.status === 401) {
        logger.warn('fetchMobileSales: Authentication token expired or invalid (HTTP 401). Clearing stale credentials.');
        await AsyncStorage.removeItem('rll_mobile_token');
        await AsyncStorage.removeItem('rll_mobile_user');
        clearCachedToken();
      }
      throw new Error(`fetchMobileSales API returned HTTP ${res.status}`);
    }

    const contentLength = res.headers.get('content-length');
    const backendDurationMs = res.headers.get('x-backend-duration-ms');
    const cacheStatus = res.headers.get('x-sales-cache-status') || 'MISS';

    const responseText = await res.text();
    if (!responseText || !responseText.trim()) {
      logger.warn(`fetchMobileSales: Received empty response body (0 bytes) from server.`);
      return null;
    }

    const responseBytes = responseText.length;
    const responseKb = (responseBytes / 1024).toFixed(2);
    const responseMb = (responseBytes / (1024 * 1024)).toFixed(2);

    const tParseStart = now();
    const data = JSON.parse(responseText);
    const tParseEnd = now();
    const jsonParseDurationMs = Math.round(tParseStart > 0 ? tParseEnd - tParseStart : 0);

    if (data) {
      data._requestId = requestId;
      data._tRequestStart = tRequestStart;
      data._tResponseReceived = tResponseReceived;
      data._networkDurationMs = networkDurationMs;
      data._responseBytes = responseBytes;
      data._responseKb = responseKb;
      data._responseMb = responseMb;
      data._jsonParseDurationMs = jsonParseDurationMs;
      data._backendDurationMs = backendDurationMs ? parseFloat(backendDurationMs) : null;
      data._cacheStatus = cacheStatus;
    }

    let totCases = 0;
    let totBtl = 0;
    if (Array.isArray(data?.companies)) {
      data.companies.forEach((c: any) => {
        const pData = c.data?.[period] || c.data?.Daily || { cases: 0, bottles: 0 };
        totCases += pData.cases || 0;
        totBtl += pData.bottles || 0;
      });
    }

    logger.info(
      `📊 [MOBILE_RESPONSE_RECEIVED] Request ID: ${requestId} | ` +
      `Network=${networkDurationMs}ms | Size=${responseKb}KB (${responseMb}MB) | ` +
      `JSON.parse=${jsonParseDurationMs}ms | Cache=${cacheStatus}`
    );

    return data;
  } catch (error: any) {
    const isAbort =
      error?.name === 'AbortError' ||
      (error?.message && (
        error.message.toLowerCase().includes('canceled') ||
        error.message.toLowerCase().includes('cancelled') ||
        error.message.toLowerCase().includes('aborted')
      ));

    if (isAbort) {
      logger.info('fetchMobileSales: In-flight request canceled due to parameter change.');
      return null;
    }
    logger.error('fetchMobileSales: Exception while retrieving sales data', error);
    return null;
  }
}

export async function fetchUserProfile() {
  logger.info('fetchUserProfile: Checking for active mobile session...');
  const token = await getAuthToken();
  if (!token) {
    logger.info('fetchUserProfile: No token found in AsyncStorage.');
    return null;
  }
  try {
    const res = await apiFetch('/mobile/me', {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (res.status === 401) {
      logger.warn('fetchUserProfile: Token has expired or is invalid (401). Clearing session.');
      await AsyncStorage.removeItem('rll_mobile_token');
      await AsyncStorage.removeItem('rll_mobile_user');
      clearCachedToken();
      return null;
    }
    if (!res.ok) {
      logger.warn(`fetchUserProfile: API returned error status ${res.status}`);
      return null;
    }
    const data = await res.json();
    if (data && data.email) {
      await AsyncStorage.setItem('rll_mobile_user', JSON.stringify(data));
    }
    logger.info('fetchUserProfile: Successfully fetched current user profile.');
    return data;
  } catch (error) {
    logger.error('fetchUserProfile: Exception fetching user profile:', error);
    return null;
  }
}

export async function fetchMobileHeadquarters() {
  logger.info('fetchMobileHeadquarters: Fetching registered headquarters...');
  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const data = await apiFetchCached('/mobile/headquarters', 600_000, token || undefined) as any;
    const hqs = data?.headquarters || [];
    logger.info(`fetchMobileHeadquarters: Successfully retrieved ${hqs.length} headquarters.`);
    return hqs;
    logger.info(`fetchMobileHeadquarters: Successfully retrieved ${hqs.length} headquarters.`);
    return hqs;
  } catch (error) {
    logger.error('fetchMobileHeadquarters: Exception fetching headquarters:', error);
    return ['All Headquarters'];
  }
}

export async function clearAllPhoneCaches() {
  try {
    const keys = await AsyncStorage.getAllKeys();
    const cacheKeys = keys.filter((k) => k.startsWith('rll_phone_cache_') || k.startsWith('rll_mobile_cascading_') || k.startsWith('DISK_CACHE_'));
    if (cacheKeys.length > 0) {
      await AsyncStorage.multiRemove(cacheKeys);
      logger.info(`clearAllPhoneCaches: Cleared ${cacheKeys.length} stale phone cache keys.`);
    }
  } catch (e) {
    logger.warn(`clearAllPhoneCaches error: ${e}`);
  }
}

export async function clearAuthSession() {
  logger.info('clearAuthSession: Clearing user auth tokens and profiles from AsyncStorage.');
  await AsyncStorage.removeItem('rll_mobile_token');
  await AsyncStorage.removeItem('rll_mobile_user');
  await clearAllPhoneCaches();
  clearCachedToken();
  invalidateApiCache();
}

export async function fetchCascadingGroups(dateFrom?: string, dateTo?: string, period?: string, selectedHq?: string) {
  logger.info(`fetchCascadingGroups: Fetching active groups (dateFrom: ${dateFrom}, dateTo: ${dateTo}, period: ${period}, selectedHq: ${selectedHq})`);
  try {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (period) params.append('period', period);
    if (selectedHq && selectedHq !== 'All Headquarters') params.append('selected_hq', selectedHq);

    const queryStr = params.toString() ? `?${params.toString()}` : '';
    const res = await apiFetch(`/mobile/cascading/groups${queryStr}`);
    if (!res.ok) {
      logger.warn(`fetchCascadingGroups: API returned status ${res.status}`);
      return [];
    }
    const data = await res.json();
    return data || [];
  } catch (error) {
    logger.error('fetchCascadingGroups: Error fetching groups:', error);
    return [];
  }
}

export async function fetchGroupBrands(groupId: string, dateFrom?: string, dateTo?: string, period?: string, selectedHq?: string) {
  logger.info(`fetchGroupBrands: Fetching brand sales for group ${groupId}`);
  try {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (period) params.append('period', period);
    if (selectedHq && selectedHq !== 'All Headquarters') params.append('depot_name', selectedHq);

    const queryStr = params.toString() ? `?${params.toString()}` : '';
    const res = await apiFetch(`/mobile/cascading/groups/${encodeURIComponent(groupId)}/brands${queryStr}`);
    if (!res.ok) {
      logger.warn(`fetchGroupBrands: API returned status ${res.status}`);
      return [];
    }
    const data = await res.json();
    return data || [];
  } catch (error) {
    logger.error(`fetchGroupBrands: Error fetching brand sales for group ${groupId}:`, error);
    return [];
  }
}

export async function fetchGroupLicensees(groupId: string, dateFrom?: string, dateTo?: string, period?: string, selectedHq?: string) {
  logger.info(`fetchGroupLicensees: Fetching licensees for group ${groupId}`);
  try {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (period) params.append('period', period);
    if (selectedHq && selectedHq !== 'All Headquarters') params.append('depot_name', selectedHq);

    const queryStr = params.toString() ? `?${params.toString()}` : '';
    const res = await apiFetch(`/mobile/cascading/groups/${encodeURIComponent(groupId)}/licensees${queryStr}`);
    if (!res.ok) {
      logger.warn(`fetchGroupLicensees: API returned status ${res.status}`);
      return [];
    }
    const data = await res.json();
    return data || [];
  } catch (error) {
    logger.error(`fetchGroupLicensees: Error fetching licensees for group ${groupId}:`, error);
    return [];
  }
}

export async function fetchLicenseeBrandSales(licenseeId: string, dateFrom?: string, dateTo?: string, period?: string, selectedHq?: string) {
  logger.info(`fetchLicenseeBrandSales: Fetching brand sales for licensee ${licenseeId}`);
  try {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (period) params.append('period', period);
    if (selectedHq && selectedHq !== 'All Headquarters') params.append('depot_name', selectedHq);

    const queryStr = params.toString() ? `?${params.toString()}` : '';
    const res = await apiFetch(`/mobile/cascading/licensees/${encodeURIComponent(licenseeId)}/brand-sales${queryStr}`);
    if (!res.ok) {
      logger.warn(`fetchLicenseeBrandSales: API returned status ${res.status}`);
      return [];
    }
    const data = await res.json();
    return data || [];
  } catch (error) {
    logger.error(`fetchLicenseeBrandSales: Error fetching brand sales for licensee ${licenseeId}:`, error);
    return [];
  }
}

export async function fetchMobileCompanies(period: string = 'Daily', dateTo?: string, selectedHq: string = 'All Headquarters') {
  logger.info(`fetchMobileCompanies: period=${period}, dateTo=${dateTo}, selectedHq=${selectedHq}`);
  const cacheKey = `rll_phone_cache_companies_${period}_${selectedHq}_${dateTo || 'latest'}`;

  // Only use phone disk cache when dateTo is empty AND selectedHq is 'All Headquarters'
  if (!dateTo && selectedHq === 'All Headquarters') {
    try {
      const cachedStr = await AsyncStorage.getItem(cacheKey);
      if (cachedStr) {
        const cachedData = JSON.parse(cachedStr);
        if (cachedData && Array.isArray(cachedData.companies) && cachedData.companies.length > 0) {
          logger.info(`fetchMobileCompanies: Phone cache HIT for ${cacheKey}`);
          setTimeout(() => {
            fetchMobileCompaniesNetwork(period, dateTo, selectedHq, cacheKey).catch(() => {});
          }, 50);
          return cachedData;
        }
      }
    } catch (e) {
      logger.warn(`fetchMobileCompanies: Phone cache read error: ${e}`);
    }
  }

  return fetchMobileCompaniesNetwork(period, dateTo, selectedHq, cacheKey);
}

async function fetchMobileCompaniesNetwork(period: string, dateTo?: string, selectedHq: string = 'All Headquarters', cacheKey?: string) {
  if (activeCompaniesAbortController) {
    activeCompaniesAbortController.abort();
    logger.info('fetchMobileCompaniesNetwork: Aborted previous in-flight companies request.');
  }
  activeCompaniesAbortController = new AbortController();
  const signal = activeCompaniesAbortController.signal;

  try {
    const params = new URLSearchParams();
    params.append('period', period);
    if (dateTo) params.append('date', dateTo);
    if (selectedHq) params.append('selected_hq', selectedHq);

    const res = await apiFetch(`/mobile/companies?${params.toString()}`, { signal });
    if (!res.ok) {
      logger.warn(`fetchMobileCompaniesNetwork: API status ${res.status}`);
      return null;
    }
    const data = await res.json();
    if (!data || !Array.isArray(data.companies)) {
      return null;
    }

    if (cacheKey && data.companies.length > 0) {
      AsyncStorage.setItem(cacheKey, JSON.stringify(data)).catch(() => {});
    }
    return data;
  } catch (error: any) {
    const isAbort =
      error?.name === 'AbortError' ||
      (error?.message && (
        error.message.toLowerCase().includes('canceled') ||
        error.message.toLowerCase().includes('cancelled') ||
        error.message.toLowerCase().includes('aborted')
      ));

    if (isAbort) {
      logger.info('fetchMobileCompaniesNetwork: Request canceled successfully.');
      return null;
    }
    logger.error('fetchMobileCompaniesNetwork: Exception fetching companies:', error);
    return null;
  }
}

export async function fetchCompanyBrands(companyId: string, dateFrom?: string, dateTo?: string, selectedHq?: string) {
  logger.info(`fetchCompanyBrands: Fetching brand sales for company ${companyId} (dateFrom: ${dateFrom}, dateTo: ${dateTo}, hq: ${selectedHq})`);
  try {
    const params = new URLSearchParams();
    params.append('company_id', companyId);
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (selectedHq && selectedHq !== 'All Headquarters') params.append('hq_name', selectedHq);

    const token = await getAuthToken();
    const res = await apiFetch(`/mobile/cascading/company-brands?${params.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      logger.warn(`fetchCompanyBrands status error ${res.status}`);
      return [];
    }
    const data = await res.json();
    return data || [];
  } catch (error) {
    logger.error(`fetchCompanyBrands error for company ${companyId}:`, error);
    return [];
  }
}

export async function fetchBrandLicensees(brandId: string, dateFrom?: string, dateTo?: string, selectedHq?: string) {
  logger.info(`fetchBrandLicensees: Fetching licensee sales for brand ${brandId} (dateFrom: ${dateFrom}, dateTo: ${dateTo}, hq: ${selectedHq})`);
  try {
    const params = new URLSearchParams();
    params.append('brand_id', brandId);
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (selectedHq && selectedHq !== 'All Headquarters') params.append('hq_name', selectedHq);

    const token = await getAuthToken();
    const res = await apiFetch(`/mobile/cascading/brand-licensees?${params.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      logger.warn(`fetchBrandLicensees status error ${res.status}`);
      return [];
    }
    const data = await res.json();
    return data || [];
  } catch (error) {
    logger.error(`fetchBrandLicensees error for brand ${brandId}:`, error);
    return [];
  }
}

