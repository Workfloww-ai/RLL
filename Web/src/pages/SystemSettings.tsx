import React, { useState, useEffect } from 'react';
import { Shield, Eye, Building2, RefreshCw, Lock, Bot, Save, CheckCircle2 } from 'lucide-react';
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
  const [savedDataRestrictionEnabled, setSavedDataRestrictionEnabled] = useState<boolean | null>(null);
  const [includeOthersEnabled, setIncludeOthersEnabled] = useState<boolean | null>(null);
  const [savedIncludeOthersEnabled, setSavedIncludeOthersEnabled] = useState<boolean | null>(null);
  const [chatbotEnabled, setChatbotEnabled] = useState<boolean | null>(null);
  const [savedChatbotEnabled, setSavedChatbotEnabled] = useState<boolean | null>(null);
  const [loadingSetting, setLoadingSetting] = useState<boolean>(true);
  const [savingSetting, setSavingSetting] = useState<boolean>(false);
  const [savingChatbot, setSavingChatbot] = useState<boolean>(false);
  const [savingOthers, setSavingOthers] = useState<boolean>(false);
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
        const isBotEnabled = String(data.chatbot_enabled).toLowerCase() !== 'false';
        setDataRestrictionEnabled(isRestricted);
        setSavedDataRestrictionEnabled(isRestricted);
        setIncludeOthersEnabled(isOthersIncluded);
        setSavedIncludeOthersEnabled(isOthersIncluded);
        setChatbotEnabled(isBotEnabled);
        setSavedChatbotEnabled(isBotEnabled);
      } else {
        setDataRestrictionEnabled(prev => prev ?? false);
        setSavedDataRestrictionEnabled(prev => prev ?? false);
        setIncludeOthersEnabled(prev => prev ?? true);
        setSavedIncludeOthersEnabled(prev => prev ?? true);
        setChatbotEnabled(prev => prev ?? true);
        setSavedChatbotEnabled(prev => prev ?? true);
      }
    } catch (e: any) {
      console.error('Error fetching settings:', e);
      setDataRestrictionEnabled(prev => prev ?? false);
      setSavedDataRestrictionEnabled(prev => prev ?? false);
      setIncludeOthersEnabled(prev => prev ?? true);
      setSavedIncludeOthersEnabled(prev => prev ?? true);
      setChatbotEnabled(prev => prev ?? true);
      setSavedChatbotEnabled(prev => prev ?? true);
    } finally {
      setLoadingSetting(false);
    }
  };

  const handleSaveRestriction = async () => {
    if (dataRestrictionEnabled === null) return;
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
          setting_value: String(dataRestrictionEnabled),
        }),
      });

      if (res.ok) {
        setSavedDataRestrictionEnabled(dataRestrictionEnabled);
        showToast(`TSM/ASE Data Restriction mode saved as ${dataRestrictionEnabled ? 'RESTRICTED (ON)' : 'LEADER VIEW (OFF)'}.`, 'success');
      } else {
        throw new Error('Failed to update setting');
      }
    } catch (e) {
      showToast('Failed to update system setting on server.', 'error');
    } finally {
      setSavingSetting(false);
    }
  };

  const handleSaveIncludeOthers = async () => {
    if (includeOthersEnabled === null) return;
    if (!isDeveloper) {
      showToast('Only Developer role can modify "Others" company inclusion setting.', 'error');
      return;
    }

    setSavingOthers(true);

    try {
      const token = localStorage.getItem('token');
      const res = await secureFetch(`${API_BASE_URL}/master-data/settings/include-others`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          include_others_in_sales: includeOthersEnabled
        }),
      });

      if (res.ok) {
        setSavedIncludeOthersEnabled(includeOthersEnabled);
        showToast(
          `"Others" company inclusion saved as ${includeOthersEnabled ? 'INCLUDED (ON)' : 'EXCLUDED (OFF)'}. Cache successfully refreshed.`,
          'success'
        );
      } else {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Failed to update include_others_in_sales setting');
      }
    } catch (e: any) {
      showToast(e.message || 'Failed to update "Others" company setting on server.', 'error');
    } finally {
      setSavingOthers(false);
    }
  };

  const handleSaveChatbotSetting = async () => {
    if (chatbotEnabled === null) return;
    if (!isDeveloper) {
      showToast('Only Developer role can modify AI Chatbot feature gate setting.', 'error');
      return;
    }
    setSavingChatbot(true);

    try {
      const token = localStorage.getItem('token');
      const res = await secureFetch(`${API_BASE_URL}/master-data/settings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          setting_key: 'chatbot_enabled',
          setting_value: String(chatbotEnabled),
        }),
      });

      if (res.ok) {
        setSavedChatbotEnabled(chatbotEnabled);
        showToast(
          `Sales AI Chatbot feature gate saved as ${chatbotEnabled ? 'ENABLED (ON)' : 'DISABLED (OFF)'}. Mobile and web instances updated.`,
          'success'
        );
      } else {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to update Chatbot feature gate setting');
      }
    } catch (e: any) {
      showToast(e.message || 'Failed to save Chatbot feature gate setting on server.', 'error');
    } finally {
      setSavingChatbot(false);
    }
  };

  const hasChatbotUnsavedChanges = chatbotEnabled !== null && savedChatbotEnabled !== null && chatbotEnabled !== savedChatbotEnabled;
  const hasOthersUnsavedChanges = includeOthersEnabled !== null && savedIncludeOthersEnabled !== null && includeOthersEnabled !== savedIncludeOthersEnabled;
  const hasRestrictionUnsavedChanges = dataRestrictionEnabled !== null && savedDataRestrictionEnabled !== null && dataRestrictionEnabled !== savedDataRestrictionEnabled;

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header Banner */}
      <div className="flex items-center justify-between bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 bg-[#0D3B8E]/10 text-[#0D3B8E] rounded-xl flex items-center justify-center font-bold">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">Security & Feature Configuration Settings</h2>
            <p className="text-xs text-slate-500">
              Manage real-time sales calculation parameters, AI Chatbot feature gating, and access control policies.
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
        {/* Developer-Only Feature Gate Cards */}
        {isDeveloper && (
          <>
            {/* Sales AI Chatbot Feature Gate Card */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between relative overflow-hidden">
              {hasChatbotUnsavedChanges && (
                <div className="absolute top-0 right-0 left-0 h-1 bg-amber-500 animate-pulse" />
              )}

              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2.5">
                    <Bot className="w-5 h-5 text-[#0D3B8E]" />
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">Sales AI Chatbot Feature Gate</h3>
                      <p className="text-[11px] text-slate-500 font-medium">Control mobile and web access to the AI Chatbot Assistant</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {hasChatbotUnsavedChanges && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                        Unsaved Changes
                      </span>
                    )}
                    <span
                      className={`px-2.5 py-1 rounded-full text-[10px] font-extrabold uppercase tracking-wider ${
                        chatbotEnabled ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-700'
                      }`}
                    >
                      {chatbotEnabled ? 'Enabled (ON)' : 'Disabled (OFF)'}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-slate-600 mb-6 leading-relaxed">
                  {chatbotEnabled ? (
                    <span>
                      <strong>ON (Enabled):</strong> The AI Chatbot floating action button (FAB) is <strong>active and visible</strong> on mobile devices and web endpoints. Users can perform natural language queries.
                    </span>
                  ) : (
                    <span>
                      <strong>OFF (Disabled):</strong> The AI Chatbot button is <strong>hidden across all mobile screens</strong> and backend query endpoints return forbidden notices.
                    </span>
                  )}
                </p>
              </div>

              <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-semibold text-slate-700">Chatbot Feature Gate Toggle</span>

                  {chatbotEnabled === null ? (
                    <div className="h-7 w-14 bg-slate-200 animate-pulse rounded-full"></div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setChatbotEnabled(!chatbotEnabled)}
                      disabled={loadingSetting || savingChatbot}
                      className="flex items-center gap-3 cursor-pointer group focus:outline-none"
                      title="Click to toggle Chatbot Feature Gate"
                    >
                      <span className={`text-xs font-bold transition-colors ${!chatbotEnabled ? 'text-slate-700' : 'text-slate-400'}`}>
                        OFF
                      </span>
                      <div
                        className={`relative inline-flex h-7 w-14 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                          chatbotEnabled ? 'bg-emerald-500' : 'bg-slate-300'
                        }`}
                      >
                        <span
                          className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                            chatbotEnabled ? 'translate-x-7' : 'translate-x-0'
                          }`}
                        />
                      </div>
                      <span className={`text-xs font-bold transition-colors ${chatbotEnabled ? 'text-emerald-700' : 'text-slate-400'}`}>
                        ON
                      </span>
                    </button>
                  )}
                </div>

                {/* Dedicated Save Button - ONLY visible when there are unsaved changes or saving */}
                {(hasChatbotUnsavedChanges || savingChatbot) && (
                  <button
                    type="button"
                    onClick={handleSaveChatbotSetting}
                    disabled={loadingSetting || savingChatbot || chatbotEnabled === null}
                    className="flex items-center gap-2 px-4 py-2 bg-[#0D3B8E] hover:bg-[#0b3279] text-white rounded-xl text-xs font-bold transition-all shadow-sm cursor-pointer ring-2 ring-[#0D3B8E]/20"
                    title="Click to save Chatbot feature gate setting"
                  >
                    {savingChatbot ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Saving...</span>
                      </>
                    ) : (
                      <>
                        <Save className="w-3.5 h-3.5" />
                        <span>Save Changes</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>

            {/* Developer-Controlled Include Others Company Toggle */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between relative overflow-hidden">
              {hasOthersUnsavedChanges && (
                <div className="absolute top-0 right-0 left-0 h-1 bg-amber-500 animate-pulse" />
              )}

              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2.5">
                    <Building2 className="w-5 h-5 text-[#0D3B8E]" />
                    <h3 className="text-sm font-bold text-slate-900">Include "Others" Company in Sales</h3>
                  </div>

                  <div className="flex items-center gap-2">
                    {hasOthersUnsavedChanges && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                        Unsaved Changes
                      </span>
                    )}
                    <span
                      className={`px-2.5 py-1 rounded-full text-[10px] font-extrabold uppercase tracking-wider ${
                        includeOthersEnabled ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-700'
                      }`}
                    >
                      {includeOthersEnabled ? 'Included (ON)' : 'Excluded (OFF)'}
                    </span>
                  </div>
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
                <div className="flex items-center gap-3">
                  <span className="text-xs font-semibold text-slate-700">Include "Others" Company</span>
                  
                  {includeOthersEnabled === null ? (
                    <div className="h-7 w-14 bg-slate-200 animate-pulse rounded-full"></div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setIncludeOthersEnabled(!includeOthersEnabled)}
                      disabled={loadingSetting || savingOthers}
                      className="flex items-center gap-3 cursor-pointer group focus:outline-none"
                      title="Click to toggle Others company inclusion"
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

                {/* Dedicated Save Button - ONLY visible when there are unsaved changes or saving */}
                {(hasOthersUnsavedChanges || savingOthers) && (
                  <button
                    type="button"
                    onClick={handleSaveIncludeOthers}
                    disabled={loadingSetting || savingOthers || includeOthersEnabled === null}
                    className="flex items-center gap-2 px-4 py-2 bg-[#0D3B8E] hover:bg-[#0b3279] text-white rounded-xl text-xs font-bold transition-all shadow-sm cursor-pointer ring-2 ring-[#0D3B8E]/20"
                    title="Click to save Others company inclusion setting"
                  >
                    {savingOthers ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        <span>Saving...</span>
                      </>
                    ) : (
                      <>
                        <Save className="w-3.5 h-3.5" />
                        <span>Save Changes</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </>
        )}

        {/* TSM / ASE Data Restriction Toggle */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between relative overflow-hidden">
          {hasRestrictionUnsavedChanges && (
            <div className="absolute top-0 right-0 left-0 h-1 bg-amber-500 animate-pulse" />
          )}

          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <Eye className="w-5 h-5 text-[#0D3B8E]" />
                <div>
                  <h3 className="text-sm font-bold text-slate-900">TSM & ASE Data Visibility Toggle</h3>
                  <p className="text-[11px] text-slate-500 font-medium">Control data access bounds for field TSM and ASE users</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {hasRestrictionUnsavedChanges && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                    Unsaved Changes
                  </span>
                )}
                <span
                  className={`px-2.5 py-1 rounded-full text-[10px] font-extrabold uppercase tracking-wider ${
                    dataRestrictionEnabled ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                  }`}
                >
                  {dataRestrictionEnabled ? 'Restricted View (ON)' : 'Leader View (OFF)'}
                </span>
              </div>
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
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold text-slate-700">Toggle Visibility Mode</span>
              
              {dataRestrictionEnabled === null ? (
                <div className="h-7 w-14 bg-slate-200 animate-pulse rounded-full"></div>
              ) : (
                <button
                  type="button"
                  onClick={() => setDataRestrictionEnabled(!dataRestrictionEnabled)}
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

            {/* Dedicated Save Button - ONLY visible when there are unsaved changes or saving */}
            {(hasRestrictionUnsavedChanges || savingSetting) && (
              <button
                type="button"
                onClick={handleSaveRestriction}
                disabled={loadingSetting || savingSetting || dataRestrictionEnabled === null}
                className="flex items-center gap-2 px-4 py-2 bg-[#0D3B8E] hover:bg-[#0b3279] text-white rounded-xl text-xs font-bold transition-all shadow-sm cursor-pointer ring-2 ring-[#0D3B8E]/20"
                title="Click to save TSM & ASE Data Visibility setting"
              >
                {savingSetting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <Save className="w-3.5 h-3.5" />
                    <span>Save Changes</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}



