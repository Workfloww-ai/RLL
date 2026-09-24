import React, { useState, useEffect } from 'react';
import { Shield, Eye, Building2, RefreshCw, Lock } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { useToast } from '../contexts/ToastContext';
import { secureFetch } from '../lib/apiClient';

function getUserRoleFromStorage(): string {
  try {
    const storedUserStr = localStorage.getItem('user');
    if (storedUserStr) {
      const u = JSON.parse(storedUserStr);
      const r = (u.role_name || u.role || '').toLowerCase();
      if (r) return r;
    }
  } catch (e) {}

  try {
    const token = localStorage.getItem('token');
    if (token) {
      const base64Url = token.split('.')[1];
      if (base64Url) {
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const payload = JSON.parse(atob(base64));
        const r = (payload.role || payload.role_name || '').toLowerCase();
        if (r) return r;
      }
    }
  } catch (e) {}

  return '';
}

export default function SystemSettings() {
  const [dataRestrictionEnabled, setDataRestrictionEnabled] = useState<boolean | null>(null);
  const [includeOthersEnabled, setIncludeOthersEnabled] = useState<boolean | null>(null);
  const [loadingSetting, setLoadingSetting] = useState<boolean>(true);
  const [savingSetting, setSavingSetting] = useState<boolean>(false);
  const [userRole, setUserRole] = useState<string>(() => getUserRoleFromStorage());
  const { showToast } = useToast();

  useEffect(() => {
    async function loadRole() {
      const existing = getUserRoleFromStorage();
      if (existing) {
        setUserRole(existing);
        return;
      }
      try {
        const token = localStorage.getItem('token');
        const headers: Record<string, string> = token ? { 'Authorization': `Bearer ${token}` } : {};
        const res = await secureFetch(`${API_BASE_URL}/auth/me`, { headers });
        if (res.ok) {
          const meData = await res.json();
          if (meData?.user) {
            localStorage.setItem('user', JSON.stringify(meData.user));
            const r = (meData.user.role_name || meData.user.role || '').toLowerCase();
            if (r) setUserRole(r);
          }
        }
      } catch (e) {
        console.error('Error fetching current user role:', e);
      }
    }

    loadRole();
    fetchSettings();
  }, []);

  const isDeveloper = userRole === 'developer';

  const fetchSettings = async () => {
    setLoadingSetting(true);
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
      const res = await secureFetch(`${API_BASE_URL}/master-data/settings`, { headers });
      if (res.ok) {
        const data = await res.json();
        const isRestricted = data.tsm_ase_data_restriction_enabled === 'true';
        const isOthersIncluded = String(data.include_others_in_sales).toLowerCase() !== 'false';
        setDataRestrictionEnabled(isRestricted);
        setIncludeOthersEnabled(isOthersIncluded);
      } else {
        setDataRestrictionEnabled(prev => prev ?? false);
        setIncludeOthersEnabled(prev => prev ?? true);
      }
    } catch (e: any) {
      console.error('Error fetching settings:', e);
      setDataRestrictionEnabled(prev => prev ?? false);
      setIncludeOthersEnabled(prev => prev ?? true);
    } finally {
      setLoadingSetting(false);
    }
  };

  const handleToggleRestriction = async () => {
    if (dataRestrictionEnabled === null) return;
    
    const previousValue = dataRestrictionEnabled;
    const newValue = !dataRestrictionEnabled;
    setDataRestrictionEnabled(newValue);
    setSavingSetting(true);

    try {
      const token = localStorage.getItem('token');
      const res = await secureFetch(`${API_BASE_URL}/master-data/settings`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          setting_key: 'tsm_ase_data_restriction_enabled',
          setting_value: String(newValue),
        }),
      });

      if (res.ok) {
        showToast(`TSM/ASE Data Restriction mode updated to ${newValue ? 'RESTRICTED (ON)' : 'LEADER VIEW (OFF)'}.`, 'success');
      } else {
        throw new Error('Failed to update setting');
      }
    } catch (e) {
      setDataRestrictionEnabled(previousValue);
      showToast('Failed to update system setting on server.', 'error');
    } finally {
      setSavingSetting(false);
    }
  };

  const handleToggleIncludeOthers = async () => {
    if (includeOthersEnabled === null) return;
    if (!isDeveloper) {
      showToast('Only Developer role can modify "Others" company inclusion setting.', 'error');
      return;
    }

    const previousValue = includeOthersEnabled;
    const newValue = !includeOthersEnabled;
    setIncludeOthersEnabled(newValue);
    setSavingSetting(true);

    try {
      const token = localStorage.getItem('token');
      const res = await secureFetch(`${API_BASE_URL}/master-data/settings/include-others`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          include_others_in_sales: newValue
        }),
      });

      if (res.ok) {
        showToast(
          `"Others" company inclusion updated to ${newValue ? 'INCLUDED (ON)' : 'EXCLUDED (OFF)'}. Cache successfully refreshed.`,
          'success'
        );
      } else {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Failed to update include_others_in_sales setting');
      }
    } catch (e: any) {
      setIncludeOthersEnabled(previousValue);
      showToast(e.message || 'Failed to update "Others" company setting on server.', 'error');
    } finally {
      setSavingSetting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header Banner */}
      <div className="flex items-center justify-between bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 bg-[#0D3B8E]/10 text-[#0D3B8E] rounded-xl flex items-center justify-center font-bold">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">Security & Sales Configuration Settings</h2>
            <p className="text-xs text-slate-500">
              Manage real-time sales calculation parameters, company inclusion rules, and access control policies.
            </p>
          </div>
        </div>

        <button
          onClick={fetchSettings}
          disabled={loadingSetting}
          className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loadingSetting ? 'animate-spin' : ''}`} />
          <span>Refresh Settings</span>
        </button>
      </div>

      {/* Settings Grid */}
      <div className="max-w-3xl space-y-6">
        {/* Developer-Controlled Include Others Company Toggle */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <Building2 className="w-5 h-5 text-[#0D3B8E]" />
                <h3 className="text-sm font-bold text-slate-900">Include "Others" Company in Sales</h3>
              </div>
              <span
                className={`px-2.5 py-1 rounded-full text-[10px] font-extrabold uppercase tracking-wider ${
                  includeOthersEnabled ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-700'
                }`}
              >
                {includeOthersEnabled ? 'Included (ON)' : 'Excluded (OFF)'}
              </span>
            </div>

            <p className="text-xs text-slate-600 mb-6 leading-relaxed">
              {includeOthersEnabled ? (
                <span>
                  <strong>ON (Included):</strong> "Others" company data is <strong>currently included</strong> in all sales analytics, HQ totals, depot metrics, TSM/ASE calculations, daily/MTD/YTD totals, and API responses.
                </span>
              ) : (
                <span>
                  <strong>OFF (Excluded):</strong> "Others" company data is <strong>currently excluded</strong> from all sales calculations across PostgreSQL RPCs, APIs, and cached summaries.
                </span>
              )}
            </p>
          </div>

          <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-700">Include "Others" Company</span>
              {!isDeveloper && (
                <span className="flex items-center gap-1 text-[11px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                  <Lock className="w-3 h-3" />
                  Developer Role Required
                </span>
              )}
            </div>
            
            {includeOthersEnabled === null ? (
              <div className="h-7 w-14 bg-slate-200 animate-pulse rounded-full"></div>
            ) : (
              <button
                type="button"
                onClick={handleToggleIncludeOthers}
                disabled={loadingSetting || savingSetting || !isDeveloper}
                className={`flex items-center gap-3 cursor-pointer group focus:outline-none ${!isDeveloper ? 'opacity-50 cursor-not-allowed' : ''}`}
                title={isDeveloper ? 'Click to toggle "Others" company inclusion' : 'Developer role required to change this setting'}
              >
                <span className={`text-xs font-bold transition-colors ${!includeOthersEnabled ? 'text-slate-700' : 'text-slate-400'}`}>
                  OFF
                </span>
                <div
                  className={`relative inline-flex h-7 w-14 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                    includeOthersEnabled ? 'bg-emerald-500' : 'bg-slate-300'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                      includeOthersEnabled ? 'translate-x-7' : 'translate-x-0'
                    }`}
                  />
                </div>
                <span className={`text-xs font-bold transition-colors ${includeOthersEnabled ? 'text-emerald-700' : 'text-slate-400'}`}>
                  ON
                </span>
              </button>
            )}
          </div>
        </div>

        {/* TSM / ASE Data Restriction Toggle */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <Eye className="w-5 h-5 text-[#0D3B8E]" />
                <h3 className="text-sm font-bold text-slate-900">TSM & ASE Data Visibility Toggle</h3>
              </div>
              <span
                className={`px-2.5 py-1 rounded-full text-[10px] font-extrabold uppercase tracking-wider ${
                  dataRestrictionEnabled ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                }`}
              >
                {dataRestrictionEnabled ? 'Restricted View (ON)' : 'Leader View (OFF)'}
              </span>
            </div>

            <p className="text-xs text-slate-600 mb-6 leading-relaxed">
              {dataRestrictionEnabled ? (
                <span>
                  <strong>ON (Restricted View):</strong> TSM and ASE users in the mobile app can view <strong>only data assigned to their specific TSM/ASE ID and assigned depots</strong>.
                </span>
              ) : (
                <span>
                  <strong>OFF (Leader View):</strong> TSM and ASE users in the mobile app will see <strong>full company-wide sales data</strong> identically to the Leader & Admin view.
                </span>
              )}
            </p>
          </div>

          <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">Toggle Visibility Mode</span>
            
            {dataRestrictionEnabled === null ? (
              <div className="h-7 w-14 bg-slate-200 animate-pulse rounded-full"></div>
            ) : (
              <button
                type="button"
                onClick={handleToggleRestriction}
                disabled={loadingSetting || savingSetting}
                className="flex items-center gap-3 cursor-pointer group focus:outline-none"
                title="Click to toggle between Restricted View (ON) and Leader View (OFF)"
              >
                <span className={`text-xs font-bold transition-colors ${!dataRestrictionEnabled ? 'text-slate-700' : 'text-slate-400'}`}>
                  Leader (OFF)
                </span>
                <div
                  className={`relative inline-flex h-7 w-14 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                    dataRestrictionEnabled ? 'bg-emerald-500' : 'bg-slate-300'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                      dataRestrictionEnabled ? 'translate-x-7' : 'translate-x-0'
                    }`}
                  />
                </div>
                <span className={`text-xs font-bold transition-colors ${dataRestrictionEnabled ? 'text-emerald-700' : 'text-slate-400'}`}>
                  Restricted (ON)
                </span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

