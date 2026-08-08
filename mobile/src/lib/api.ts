const BASE_URL = 'http://localhost:8000/api/v1';

export async function loginMobileUser(email: string, password: string) {
  try {
    const res = await fetch(`${BASE_URL}/mobile/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      throw new Error('Authentication failed');
    }

    const data = await res.json();
    if (data.access_token) {
      localStorage.setItem('rll_mobile_token', data.access_token);
      localStorage.setItem('rll_mobile_user', JSON.stringify(data.user));
    }
    return data;
  } catch (error) {
    console.warn('Backend login fallback:', error);
    // Offline/Local Fallback
    const mockUser = {
      user_id: 'e8a27d14-3850-482a-9e12-852788028800',
      email: email || 'monalika.goel@workfloww.ai',
      first_name: email ? email.split('@')[0] : 'Monalika',
      last_name: 'Goel',
      role_name: 'admin',
      hq_location: 'All Headquarters',
    };
    const mockToken = 'demo-token-' + Date.now();
    localStorage.setItem('rll_mobile_token', mockToken);
    localStorage.setItem('rll_mobile_user', JSON.stringify(mockUser));
    return { access_token: mockToken, user: mockUser };
  }
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
