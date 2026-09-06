import React, { useState, useEffect } from 'react';
import { Shield, Eye, AlertTriangle, CheckCircle, RefreshCw } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { useToast } from '../contexts/ToastContext';

export default function SystemSettings() {
  const [dataRestrictionEnabled, setDataRestrictionEnabled] = useState<boolean | null>(null);
  const [loadingSetting, setLoadingSetting] = useState<boolean>(true);
  const [savingSetting, setSavingSetting] = useState<boolean>(false);
  const abortControllerRef = React.useRef<AbortController | null>(null);
  const { showToast } = useToast();

  useEffect(() => {
    fetchSettings();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const fetchSettings = async () => {
    setLoadingSetting(true);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
      const res = await fetch(`${API_BASE_URL}/master-data/settings`, { 
        headers,
        signal: controller.signal
      });
      if (res.ok) {
        const data = await res.json();
        const isEnabled = data.tsm_ase_data_restriction_enabled === 'true';
        setDataRestrictionEnabled(isEnabled);
      }
    } catch (e: any) {
      if (e.name === 'AbortError') {
        console.log('Request was intentionally cancelled');
      } else {
        console.error('Network or Server Error:', e);
      }
    } finally {
      if (abortControllerRef.current === controller) {
        setLoadingSetting(false);
      }
    }
  };

  const handleToggleRestriction = async () => {
    if (dataRestrictionEnabled === null) return;
    
    // Optimistic UI Update
    const previousValue = dataRestrictionEnabled;
    const newValue = !dataRestrictionEnabled;
    setDataRestrictionEnabled(newValue);
    setSavingSetting(true);

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/master-data/settings`, {
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
      // Revert Optimistic Update
      setDataRestrictionEnabled(previousValue);
      showToast('Failed to update system setting on server.', 'error');
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
            <h2 className="text-base font-bold text-slate-900">Security & Access Control Settings</h2>
            <p className="text-xs text-slate-500">
              Manage real-time data visibility controls and zero-trust security policies.
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

      {/* Settings Panel */}
      <div className="max-w-2xl">
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
