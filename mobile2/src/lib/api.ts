import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { logger } from './logger';

let envBaseUrl: string | undefined;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const dotenv = require('@env');
  envBaseUrl = dotenv.BASE_URL;
} catch {
  envBaseUrl = undefined;
}

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
  // 1. Explicit env override if set
  const envUrl = envBaseUrl || process.env.EXPO_PUBLIC_API_URL || process.env.REACT_NATIVE_API_URL;
  if (envUrl && envUrl !== 'undefined' && envUrl.trim() !== '') {
    return formatBaseUrl(envUrl);
  }

  // 2. Localhost via ADB reverse (fastest and most reliable for physical Android device & emulator)
  if (Platform.OS === 'android') {
    return 'http://localhost:8000/api/v1';
  }

  // 3. Automatically derive computer's Wi-Fi IP from Metro bundler hostUri for iOS / Metro
  const hostUri = Constants.expoConfig?.hostUri || Constants.manifest2?.extra?.expoGo?.developer?.tool;
  if (hostUri) {
    const hostIp = hostUri.split(':')[0];
    if (hostIp && hostIp !== 'localhost' && hostIp !== '127.0.0.1') {
      return `http://${hostIp}:8000/api/v1`;
    }
  }

  // 4. Default to localhost
  return 'http://localhost:8000/api/v1';
}

export const BASE_URL = getApiBaseUrl();

export async function apiFetch(endpointPath: string, init?: RequestInit): Promise<Response> {
  const cleanPath = endpointPath.startsWith('/') ? endpointPath : `/${endpointPath}`;
  const url = `${BASE_URL}${cleanPath}`;
  logger.info(`apiFetch: ${init?.method || 'GET'} ${url}`);
  return await fetch(url, init);
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
    }
    logger.info(`loginMobileUser: Success. Session loaded for email: ${email}`);
    return data;
  } catch (error) {
    logger.error(`loginMobileUser: Exception while authenticating email: ${email}`, error);
    throw error;
  }
}

export async function fetchMobileSales(
  dateFrom: string,
  dateTo: string,
  period: string,
  selectedHq: string
) {
  logger.info(`fetchMobileSales: Fetching sales data (period: ${period}, hq: ${selectedHq}, from: ${dateFrom}, to: ${dateTo})`);
  const token = await AsyncStorage.getItem('rll_mobile_token');
  if (!token) {
    logger.warn('fetchMobileSales: Missing authentication token.');
    return null;
  }

  const startTime = Date.now();
  try {
    const query = new URLSearchParams({
      date_from: dateFrom,
      date_to: dateTo,
      period,
      selected_hq: selectedHq,
    });

    const res = await apiFetch(`/mobile/sales?${query.toString()}`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (res.status === 401) {
      logger.warn('fetchMobileSales: Unauthorized (401). Clearing session.');
      await AsyncStorage.removeItem('rll_mobile_token');
      await AsyncStorage.removeItem('rll_mobile_user');
      return null;
    }

    if (!res.ok) {
      logger.warn(`fetchMobileSales: API error status ${res.status}`);
      throw new Error('Sales fetch failed');
    }

    const data = await res.json();
    const fetchDuration = Date.now() - startTime;
    data._fetchTimeMs = fetchDuration;

    let totCases = 0;
    let totBtl = 0;
    if (Array.isArray(data.companies)) {
      data.companies.forEach((c: any) => {
        const pData = c.data?.[period] || c.data?.Daily || { cases: 0, bottles: 0 };
        totCases += pData.cases || 0;
        totBtl += pData.bottles || 0;
      });
    }

    logger.info(`📊 [SALES FETCH] Period=${period} | HQ=${selectedHq} | Records=${data.record_count || 0} | Total Cases=${totCases.toLocaleString()} | Total Bottles=${totBtl.toLocaleString()}`);
    logger.info(`⚡ [TIMING] Total Fetch = ${fetchDuration}ms | Backend Process = ${data.process_time_ms ?? 'N/A'}ms`);
    return data;
  } catch (error) {
    logger.error('fetchMobileSales: Exception while retrieving sales data', error);
    return null;
  }
}

export async function fetchUserProfile() {
  logger.info('fetchUserProfile: Checking for active mobile session...');
  const token = await AsyncStorage.getItem('rll_mobile_token');
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
  const token = await AsyncStorage.getItem('rll_mobile_token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const res = await apiFetch('/mobile/headquarters', { headers });

    if (!res.ok) {
      logger.warn(`fetchMobileHeadquarters: API returned status ${res.status}`);
      throw new Error(`Headquarters fetch failed with status ${res.status}`);
    }

    const data = await res.json();
    const hqs = data.headquarters || [];
    logger.info(`fetchMobileHeadquarters: Successfully retrieved ${hqs.length} headquarters.`);
    return hqs;
  } catch (error) {
    logger.error('fetchMobileHeadquarters: Exception fetching headquarters:', error);
    return ['All Headquarters'];
  }
}

export async function clearAuthSession() {
  logger.info('clearAuthSession: Clearing user auth tokens and profiles from AsyncStorage.');
  await AsyncStorage.removeItem('rll_mobile_token');
  await AsyncStorage.removeItem('rll_mobile_user');
}

export async function fetchCascadingGroups(dateFrom?: string, dateTo?: string, period?: string) {
  logger.info(`fetchCascadingGroups: Fetching active groups (dateFrom: ${dateFrom}, dateTo: ${dateTo}, period: ${period})`);
  try {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (period) params.append('period', period);

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

export async function fetchGroupLicensees(groupId: string, dateFrom?: string, dateTo?: string, period?: string) {
  logger.info(`fetchGroupLicensees: Fetching licensees for group ${groupId}`);
  try {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (period) params.append('period', period);

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

export async function fetchLicenseeBrandSales(licenseeId: string, dateFrom?: string, dateTo?: string, period?: string) {
  logger.info(`fetchLicenseeBrandSales: Fetching brand sales for licensee ${licenseeId}`);
  try {
    const params = new URLSearchParams();
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (period) params.append('period', period);

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
