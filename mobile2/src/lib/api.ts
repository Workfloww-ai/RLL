import AsyncStorage from '@react-native-async-storage/async-storage';
import { BASE_URL } from '@env';
import { logger } from './logger';

export async function sendMobileOTP(phone: string, email: string = '') {
  logger.info(`sendMobileOTP: Requesting OTP for phone: ${phone}, email: ${email}`);
  try {
    const res = await fetch(`${BASE_URL}/mobile/send-otp`, {
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
    const res = await fetch(`${BASE_URL}/mobile/verify-otp`, {
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
    const res = await fetch(`${BASE_URL}/mobile/login`, {
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

  try {
    const query = new URLSearchParams({
      date_from: dateFrom,
      date_to: dateTo,
      period,
      selected_hq: selectedHq,
    });

    const res = await fetch(`${BASE_URL}/mobile/sales?${query.toString()}`, {
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
    logger.info('fetchMobileSales: Successfully retrieved sales metrics.');
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
    const res = await fetch(`${BASE_URL}/mobile/me`, {
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
    const res = await fetch(`${BASE_URL}/mobile/headquarters`, { headers });

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
