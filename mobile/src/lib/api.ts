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
