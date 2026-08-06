import React, { useState, useMemo } from 'react';
import { Period, ViewMode, Company } from './types';
import {
  INITIAL_COMPANIES,
  INITIAL_DEPOTS,
  INITIAL_TSMS,
  HEADQUARTERS_LIST,
} from './data/mockData';
import { calculateDateFactor, formatNumber } from './lib/utils';
import { Header } from './components/Header';
import { FooterNav } from './components/FooterNav';
import { CompanyCard } from './components/CompanyCard';
import { DepotsView } from './components/DepotsView';
import { TsmView } from './components/TsmView';
import { BrandModal } from './components/BrandModal';
import {
  Search,
  Wifi,
  Battery,
  Signal,
  ShieldAlert,
  X,
} from 'lucide-react';

export default function App() {
  const [period, setPeriod] = useState<Period>('Daily');
  const [dateFrom, setDateFrom] = useState<string>('2026-08-01');
  const [dateTo, setDateTo] = useState<string>('2026-08-06');
  const [viewMode, setViewMode] = useState<ViewMode>('companies');
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Headquarter selection state
  const [selectedHq, setSelectedHq] = useState<string>('All Headquarters');

  // Dynamic date multiplier
  const scaleFactor = useMemo(() => {
    return calculateDateFactor(dateFrom, dateTo, period);
  }, [dateFrom, dateTo, period]);

  // Filter companies: Exclude any "Others" if required, or match Image 1 list
  const filteredCompanies = useMemo(() => {
    return INITIAL_COMPANIES.filter((c) => {
      // Headquarter Filter
      if (selectedHq !== 'All Headquarters' && c.hqLocation) {
        if (c.hqLocation.toLowerCase() !== selectedHq.toLowerCase()) {
          return false;
        }
      }

      if (!searchQuery.trim()) return true;

      const q = searchQuery.toLowerCase();
      const matchCompany = c.name.toLowerCase().includes(q);
      const matchBrands = c.brands.some((b) => b.name.toLowerCase().includes(q));

      return matchCompany || matchBrands;
    });
  }, [searchQuery, selectedHq]);

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
            <Signal className="w-3 h-3 text-white" />
            <Wifi className="w-3 h-3 text-white" />
            <Battery className="w-3.5 h-3.5 text-white" />
          </div>
        </div>

        {/* Minimal Streamlined Dashboard Header Component */}
        <Header
          period={period}
          setPeriod={setPeriod}
          dateFrom={dateFrom}
          setDateFrom={setDateFrom}
          dateTo={dateTo}
          setDateTo={setDateTo}
          selectedHq={selectedHq}
          setSelectedHq={setSelectedHq}
          headquartersList={HEADQUARTERS_LIST}
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
              depots={INITIAL_DEPOTS}
              period={period}
              scaleFactor={scaleFactor}
              selectedHq={selectedHq}
            />
          )}

          {/* VIEW 3: TSM TAB */}
          {viewMode === 'tsm' && (
            <TsmView
              tsms={INITIAL_TSMS}
              period={period}
              scaleFactor={scaleFactor}
              selectedHq={selectedHq}
            />
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
      </main>
    </div>
  );
}
