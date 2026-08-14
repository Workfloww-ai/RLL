import React, { useState, useMemo, useEffect } from 'react';
import { Period, ViewMode, Company } from './types';
import { calculateDateFactor, formatNumber } from './lib/utils';
import { Header } from './components/Header';
import { FooterNav } from './components/FooterNav';
import { CompanyCard } from './components/CompanyCard';
import { DepotsView } from './components/DepotsView';
import { TsmView } from './components/TsmView';
import { BrandModal } from './components/BrandModal';
import { LoginScreen } from './components/LoginScreen';
import { ProfileScreen } from './features/profile/ProfileScreen';
import { GroupCascadingSalesScreen } from './features/sales/GroupCascadingSalesScreen';
import { fetchMobileSales, fetchUserProfile, fetchMobileHeadquarters } from './lib/api';
import {
  Search,
  Wifi,
  Battery,
  Signal,
  ShieldAlert,
  X,
  LogOut,
} from 'lucide-react';

export default function App() {
  const [user, setUser] = useState<any>(() => {
    const saved = localStorage.getItem('rll_mobile_user');
    return saved ? JSON.parse(saved) : null;
  });

  const [period, setPeriod] = useState<Period>('MTD');
  const [dateFrom, setDateFrom] = useState<string>('2026-05-01');
  const [dateTo, setDateTo] = useState<string>('2026-05-31');
  const [viewMode, setViewMode] = useState<ViewMode>('companies');
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedHq, setSelectedHq] = useState<string>('All Headquarters');
  const [headquartersList, setHeadquartersList] = useState<string[]>(['All Headquarters']);
  const [apiData, setApiData] = useState<any>(null);

  // 1. Fetch headquarters list on mount
  useEffect(() => {
    fetchMobileHeadquarters().then((hqs) => {
      if (hqs && hqs.length > 0) {
        setHeadquartersList(hqs);
      }
    });
  }, []);

  // 2. Sync user profile on mount / token change
  useEffect(() => {
    const token = localStorage.getItem('rll_mobile_token');
    if (!token) {
      if (user) setUser(null);
      return;
    }

    fetchUserProfile().then((profile) => {
      if (profile && (profile.email || profile.phone || profile.user_id)) {
        setUser(profile);
      } else if (!localStorage.getItem('rll_mobile_token')) {
        setUser(null);
      }
    });
  }, []);

  // 3. On first load, fetch with no dates to discover latest_sale_date, then set it once
  useEffect(() => {
    const token = localStorage.getItem('rll_mobile_token');
    if (!token) return;
    if (dateFrom || dateTo) return; // already initialized — don't reset

    fetchMobileSales('', '', period, selectedHq).then((res) => {
      if (res) {
        setApiData(res);
        if (res.latest_sale_date) {
          setDateFrom(res.latest_sale_date);
          setDateTo(res.latest_sale_date);
        }
      } else if (!localStorage.getItem('rll_mobile_token')) {
        setUser(null);
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Boolean(localStorage.getItem('rll_mobile_token'))]);

  // 4. Fetch sales data whenever filters change (after dates are initialized)
  useEffect(() => {
    const token = localStorage.getItem('rll_mobile_token');
    if (!token) return;
    if (!dateFrom || !dateTo) return; // wait for initialization

    fetchMobileSales(dateFrom, dateTo, period, selectedHq).then((res) => {
      if (res) {
        setApiData(res);
      } else if (!localStorage.getItem('rll_mobile_token')) {
        setUser(null);
      }
    });
  }, [dateFrom, dateTo, period, selectedHq]);

  const handleLogout = () => {
    localStorage.removeItem('rll_mobile_token');
    localStorage.removeItem('rll_mobile_user');
    setUser(null);
    setViewMode('companies');
  };

  // Exact database metrics scale factor (always 1 for true unscaled database records)
  const scaleFactor = 1;

  // Filter companies: Use live API fetched companies (HQ filtering applied on backend)
  const filteredCompanies = useMemo(() => {
    const rawCompanies: Company[] = (apiData && apiData.companies) ? apiData.companies : [];

    return rawCompanies.filter((c) => {
      if (!searchQuery.trim()) return true;

      const q = searchQuery.toLowerCase();
      const matchCompany = c.name.toLowerCase().includes(q);
      const matchBrands = c.brands && c.brands.some((b) => (b.name || b.brand_name || '').toLowerCase().includes(q));

      return matchCompany || matchBrands;
    });
  }, [searchQuery, apiData]);

  // Sort companies: Pinned (RLL then Diageo/In brew) at top, remaining sorted alphabetically ascending (A-Z)
  const sortedCompanies = useMemo(() => {
    const list = [...filteredCompanies];

    list.sort((a, b) => {
      const getPinnedRank = (c: Company) => {
        const id = c.id.toLowerCase();
        const name = c.name.toLowerCase();
        if (id === 'rll' || name === 'rll') return 1;
        if (id === 'diageo-inbrew' || name.includes('diageo')) return 2;
        if (c.isPinned) return 3;
        return 99;
      };

      const rankA = getPinnedRank(a);
      const rankB = getPinnedRank(b);

      if (rankA !== rankB) {
        return rankA - rankB;
      }

      // Remaining companies (or same rank) sorted in ascending alphabetical order (A-Z)
      return a.name.localeCompare(b.name);
    });

    return list;
  }, [filteredCompanies]);

  // Find max volume among companies for relative bar scaling
  const maxVolume = useMemo(() => {
    if (sortedCompanies.length === 0) return 1;
    return Math.max(
      ...sortedCompanies.map((c) => c.data[period].bl * scaleFactor)
    );
  }, [sortedCompanies, period, scaleFactor]);

  // Total summary for header indicator bar (Cases & Bottles)
  const totalSummary = useMemo(() => {
    return sortedCompanies.reduce(
      (acc, c) => {
        const d = c.data[period];
        return {
          cases: acc.cases + Math.round(d.cases * scaleFactor),
          bottles: acc.bottles + Math.round(d.bottles * scaleFactor),
        };
      },
      { cases: 0, bottles: 0 }
    );
  }, [sortedCompanies, period, scaleFactor]);

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col items-center justify-start p-2 sm:p-6 transition-colors">
      {/* Main Mobile Frame Container */}
      <main className="w-full transition-all duration-300 bg-[#FAFAFA] rounded-[38px] shadow-2xl border-4 border-slate-800/20 overflow-hidden flex flex-col relative max-w-[400px] aspect-[9/16] my-auto min-h-[780px]">
        {/* Simulated Phone Status Bar */}
        <div className="bg-[#0F2042] text-white/90 px-6 pt-3 pb-1 flex items-center justify-between text-[11px] font-semibold tracking-tight select-none shrink-0">
          <span>09:41</span>
          <div className="w-20 h-4 bg-black/30 rounded-full mx-auto" />
          <div className="flex items-center gap-1.5">
            {user && (
              <button
                onClick={handleLogout}
                title="Logout"
                className="hover:text-amber-400 transition-colors mr-1 cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5 text-white/80 hover:text-amber-400" />
              </button>
            )}
            <Signal className="w-3 h-3 text-white" />
            <Wifi className="w-3 h-3 text-white" />
            <Battery className="w-3.5 h-3.5 text-white" />
          </div>
        </div>

        {!user ? (
          <LoginScreen
            onLoginSuccess={(u) => {
              setUser(u);
              setViewMode('companies');
            }}
          />
        ) : (
          <>

            {/* Minimal Streamlined Dashboard Header Component */}
            {viewMode !== 'profile' && (
              <>
                <Header
                  period={period}
                  setPeriod={setPeriod}
                  dateFrom={dateFrom}
                  setDateFrom={setDateFrom}
                  dateTo={dateTo}
                  setDateTo={setDateTo}
                  selectedHq={selectedHq}
                  setSelectedHq={setSelectedHq}
                  headquartersList={headquartersList}
                  latestSaleDate={apiData?.latest_sale_date}
                />

                {/* Sleek Aggregate Quick Metrics Banner */}
                <div className="bg-white border-b border-slate-200 px-4 py-2 flex items-center justify-between shrink-0 shadow-2xs">
                  <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-600" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      {period} Total
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs font-semibold">
                    <span className="text-[#0F2042] font-black">
                      {formatNumber(totalSummary.cases)} <span className="font-normal text-slate-400 text-[10px]">cases</span>
                    </span>
                    <span className="text-slate-300">•</span>
                    <span className="text-slate-700 font-bold">
                      {formatNumber(totalSummary.bottles)} <span className="font-normal text-slate-400 text-[10px]">btl</span>
                    </span>
                  </div>
                </div>
              </>
            )}

            {/* Scrollable Main Content Area */}
            <div className="flex-1 p-3 overflow-y-auto space-y-3">
              {/* VIEW 1: COMPANIES LIST */}
              {viewMode === 'companies' && (
                <div className="space-y-2.5">
                  {/* Minimal Search Input */}
                  <div className="relative w-full">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Search brand"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      id="dashboard-search-input"
                      className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-8 py-1.5 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#0F2042] transition-all shadow-xs"
                    />
                    {searchQuery && (
                      <button
                        onClick={() => setSearchQuery('')}
                        type="button"
                        className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>

                  {/* Active Filters Pill Bar (If HQ selected or search active) */}
                  {(selectedHq !== 'All Headquarters' || searchQuery) && (
                    <div className="flex items-center gap-1.5 flex-wrap text-[10px]">
                      {selectedHq !== 'All Headquarters' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#0F2042]/10 text-[#0F2042] font-semibold">
                          HQ: {selectedHq}
                          <X
                            className="w-3 h-3 cursor-pointer hover:opacity-75"
                            onClick={() => setSelectedHq('All Headquarters')}
                          />
                        </span>
                      )}
                      {searchQuery && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold">
                          "{searchQuery}"
                          <X
                            className="w-3 h-3 cursor-pointer hover:opacity-75"
                            onClick={() => setSearchQuery('')}
                          />
                        </span>
                      )}
                    </div>
                  )}

                  {/* Company Cards Render */}
                  {sortedCompanies.length === 0 ? (
                    <div className="text-center py-10 px-4 bg-white rounded-2xl border border-slate-200 shadow-xs">
                      <ShieldAlert className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                      <p className="text-xs font-bold text-slate-700">No companies found</p>
                      <p className="text-[10px] text-slate-400 mt-1">
                        Try clearing search or HQ filter
                      </p>
                      <button
                        onClick={() => {
                          setSearchQuery('');
                          setSelectedHq('All Headquarters');
                        }}
                        type="button"
                        className="mt-3 px-3 py-1.5 rounded-lg bg-[#0F2042] text-white text-xs font-semibold"
                      >
                        Reset Filters
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {sortedCompanies.map((company, idx) => (
                        <CompanyCard
                          key={company.id}
                          company={company}
                          period={period}
                          scaleFactor={scaleFactor}
                          maxVolume={maxVolume}
                          onClick={() => setSelectedCompany(company)}
                          index={idx}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* VIEW 2: DEPOTS TAB */}
              {viewMode === 'depots' && (
                <DepotsView
                  depots={(apiData && apiData.depots) ? apiData.depots : []}
                  period={period}
                  scaleFactor={scaleFactor}
                  selectedHq={selectedHq}
                />
              )}

              {/* VIEW 3: TSM TAB */}
              {viewMode === 'tsm' && (
                <TsmView
                  tsms={(apiData && apiData.tsms) ? apiData.tsms : []}
                  period={period}
                  scaleFactor={scaleFactor}
                  selectedHq={selectedHq}
                />
              )}

              {/* VIEW 4: GROUPS TAB (CASCADING GROUP -> LICENSEE -> BRAND SALES) */}
              {viewMode === 'groups' && (
                <GroupCascadingSalesScreen
                  dateFrom={dateFrom}
                  dateTo={dateTo}
                  period={period}
                />
              )}

              {/* VIEW 5: PROFILE TAB */}
              {viewMode === 'profile' && (
                <ProfileScreen user={user} onLogout={handleLogout} />
              )}
            </div>

            {/* BOTTOM NAVIGATION FOOTER */}
            <FooterNav viewMode={viewMode} setViewMode={setViewMode} />

            {/* Bottom Smartphone Navigation Home Indicator */}
            <div className="py-1.5 bg-[#0A1428] flex items-center justify-center shrink-0">
              <div className="w-28 h-1 bg-white/30 rounded-full" />
            </div>

            {/* Minimal Flashcard Modal for Brand Breakdown */}
            <BrandModal
              company={selectedCompany}
              period={period}
              scaleFactor={scaleFactor}
              onClose={() => setSelectedCompany(null)}
            />
          </>
        )}
      </main>
    </div>
  );
}
