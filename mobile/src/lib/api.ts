const BASE_URL = 'http://localhost:8000/api/v1';

export async function sendMobileOTP(phone: string, email: string = '') {
  const res = await fetch(`${BASE_URL}/mobile/send-otp`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ phone, email }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to send OTP verification code.');
  }

  return await res.json();
}

export async function verifyMobileOTP(phone: string, otp: string, email: string = '') {
  const res = await fetch(`${BASE_URL}/mobile/verify-otp`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ phone, otp, email }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Invalid or expired 4-digit OTP code.');
  }

  const data = await res.json();
  if (data.access_token) {
    localStorage.setItem('rll_mobile_token', data.access_token);
    localStorage.setItem('rll_mobile_user', JSON.stringify(data.user));
  }
  return data;
}

export async function loginMobileUser(email: string, password: string) {
  const res = await fetch(`${BASE_URL}/mobile/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Authentication failed. Invalid email or password.');
  }

  const data = await res.json();
  if (data.access_token) {
    localStorage.setItem('rll_mobile_token', data.access_token);
    localStorage.setItem('rll_mobile_user', JSON.stringify(data.user));
  }
  return data;
}

export async function fetchMobileSales(
  dateFrom: string,
  dateTo: string,
  period: string,
  selectedHq: string
) {
  const token = localStorage.getItem('rll_mobile_token');
  if (!token) return null;

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
      localStorage.removeItem('rll_mobile_token');
      localStorage.removeItem('rll_mobile_user');
      return null;
    }

    if (!res.ok) {
      throw new Error('Sales fetch failed');
    }

    return await res.json();
  } catch (error) {
    console.error('Backend sales fetch error:', error);
    return null;
  }
}

export async function fetchUserProfile() {
  const token = localStorage.getItem('rll_mobile_token');
  if (!token) return null;
  try {
    const res = await fetch(`${BASE_URL}/mobile/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (res.status === 401) {
      localStorage.removeItem('rll_mobile_token');
      localStorage.removeItem('rll_mobile_user');
      return null;
    }
    if (!res.ok) return null;
    const data = await res.json();
    if (data && data.email) {
      localStorage.setItem('rll_mobile_user', JSON.stringify(data));
    }
    return data;
  } catch (error) {
    console.warn('Backend user profile fetch failed:', error);
    return null;
  }
}

export async function fetchMobileHeadquarters() {
  const token = localStorage.getItem('rll_mobile_token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(`${BASE_URL}/mobile/headquarters`, { headers });

    if (!res.ok) {
      throw new Error(`Headquarters fetch failed with status ${res.status}`);
    }

    const data = await res.json();
    return data.headquarters || [];
  } catch (error) {
    console.error('Backend headquarters fetch error:', error);
    return ['All Headquarters'];
  }
}
