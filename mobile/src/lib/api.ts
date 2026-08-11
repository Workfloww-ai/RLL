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

    if (!res.ok) {
      throw new Error('Sales fetch failed');
    }

    return await res.json();
  } catch (error) {
    console.warn('Backend sales fetch fallback to mock data:', error);
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

export async function fetchMobileCompanies() {
  const token = localStorage.getItem('rll_mobile_token');
  try {
    const res = await fetch(`${BASE_URL}/mobile/companies`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      throw new Error('Companies fetch failed');
    }

    return await res.json();
  } catch (error) {
    console.warn('Backend companies fetch fallback:', error);
    return null;
  }
}

export async function fetchBrandsByCompany(companyId: string) {
  const token = localStorage.getItem('rll_mobile_token');
  try {
    const res = await fetch(`${BASE_URL}/mobile/companies/${encodeURIComponent(companyId)}/brands`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      throw new Error('Brands fetch failed');
    }

    return await res.json();
  } catch (error) {
    console.warn('Backend company brands fetch fallback:', error);
    return null;
  }
}

export async function fetchMobileHeadquarters() {
  const token = localStorage.getItem('rll_mobile_token');
  try {
    const res = await fetch(`${BASE_URL}/mobile/headquarters`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      throw new Error('Headquarters fetch failed');
    }

    const data = await res.json();
    return data.headquarters || [];
  } catch (error) {
    console.warn('Backend headquarters fetch fallback:', error);
    return [
      'All Headquarters',
      'Ajmer',
      'Alwar',
      'Bikaner',
      'Jaipur',
      'Jodhpur',
      'Kota',
      'Sikar',
      'Sriganganagar',
      'Udaipur',
    ];
  }
}

