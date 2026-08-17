import React, { useState, useMemo, useEffect } from 'react';
import { TSM, Period } from '../types';
import { formatNumber } from '../lib/utils';
import { UserCheck, Search, ChevronRight, X, Users, ArrowUpDown, ChevronLeft } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

interface TsmViewProps {
  tsms: TSM[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
}

type SortOption = 'alpha-asc' | 'alpha-desc' | 'cases-desc' | 'cases-asc';

export const TsmView: React.FC<TsmViewProps> = ({
  tsms,
  period,
  scaleFactor,
  selectedHq,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTsm, setActiveTsm] = useState<TSM | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOption>('alpha-asc'); // Default: Alphabetical (A-Z)
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(15);

  // Filter and Sort TSMs (Default: A-Z Alphabetical)
  const sortedFilteredTsms = useMemo(() => {
    const filtered = tsms.filter((t) => {
      const matchHq =
        selectedHq === 'All Headquarters' ||
        (t.hqLocation && t.hqLocation.toLowerCase() === selectedHq.toLowerCase());
      const matchSearch =
        t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (t.hqLocation && t.hqLocation.toLowerCase().includes(searchTerm.toLowerCase()));
      return matchHq && matchSearch;
    });

    return filtered.sort((a, b) => {
      if (sortOrder === 'alpha-asc') return a.name.localeCompare(b.name);
      if (sortOrder === 'alpha-desc') return b.name.localeCompare(a.name);

      const aCases = Math.round((a.data[period]?.cases || 0) * scaleFactor);
      const bCases = Math.round((b.data[period]?.cases || 0) * scaleFactor);
      if (sortOrder === 'cases-desc') return bCases - aCases;
      if (sortOrder === 'cases-asc') return aCases - bCases;

      return a.name.localeCompare(b.name);
    });
  }, [tsms, selectedHq, searchTerm, sortOrder, period, scaleFactor]);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, selectedHq, sortOrder, itemsPerPage]);

  const totalItems = sortedFilteredTsms.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / itemsPerPage));
  const validCurrentPage = Math.min(currentPage, totalPages);

  const paginatedTsms = useMemo(() => {
    const start = (validCurrentPage - 1) * itemsPerPage;
    return sortedFilteredTsms.slice(start, start + itemsPerPage);
  }, [sortedFilteredTsms, validCurrentPage, itemsPerPage]);

  return (
    <div className="space-y-3">
      {/* Controls Bar: Search + Sorting Selector */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search TSM name"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              id="tsm-search-input"
              className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-8 py-1.5 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#0F2042]"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="relative flex items-center shrink-0">
            <ArrowUpDown className="w-3 h-3 text-slate-500 absolute left-2.5 pointer-events-none" />
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as SortOption)}
              className="bg-white border border-slate-200 rounded-xl pl-7 pr-2 py-1.5 text-[11px] font-bold text-[#0F2042] focus:outline-none focus:border-[#0F2042]"
            >
              <option value="alpha-asc">A-Z (Name)</option>
              <option value="alpha-desc">Z-A (Name)</option>
              <option value="cases-desc">Highest Cases</option>
              <option value="cases-asc">Lowest Cases</option>
            </select>
          </div>
        </div>

        {/* Count & Page Size Selector */}
        <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium px-1">
          <span>
            Showing {totalItems === 0 ? 0 : (validCurrentPage - 1) * itemsPerPage + 1}-
            {Math.min(validCurrentPage * itemsPerPage, totalItems)} of {totalItems} TSM(s)
          </span>

          <div className="flex items-center gap-1">
            <span>Per page:</span>
            <select
              value={itemsPerPage}
              onChange={(e) => setItemsPerPage(Number(e.target.value))}
              className="bg-white border border-slate-200 rounded-lg px-1.5 py-0.5 text-[11px] font-bold text-slate-700 focus:outline-none"
            >
              <option value={10}>10</option>
              <option value={15}>15</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
          </div>
        </div>
      </div>

      {/* TSM Cards List */}
      {paginatedTsms.length === 0 ? (
        <div className="text-center py-8 bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-bold text-slate-700">No TSM found</p>
        </div>
      ) : (
        <div className="space-y-2">
          {paginatedTsms.map((tsm, idx) => {
            const raw = tsm.data[period];
            const tMetrics = {
              cases: Math.round(raw.cases * scaleFactor),
              bottles: Math.round(raw.bottles * scaleFactor),
            };
            const aseCount = tsm.ases?.length ?? 0;

            return (
              <motion.div
                key={tsm.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, delay: idx * 0.03 }}
                id={`tsm-card-${tsm.id}`}
                onClick={() => setActiveTsm(tsm)}
                className="p-3.5 rounded-2xl bg-white border border-slate-200/80 space-y-2 shadow-2xs cursor-pointer group hover:border-slate-300 transition-all"
              >
                {/* Header */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-8 h-8 rounded-xl bg-[#0F2042]/10 text-[#0F2042] flex items-center justify-center shrink-0">
                      <UserCheck className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <h4 className="text-xs sm:text-sm font-bold text-slate-900 truncate group-hover:text-[#0F2042] transition-colors">
                        {tsm.name}
                      </h4>
                      <p className="text-[10px] text-slate-400 font-medium">
                        {aseCount > 0
                          ? `${aseCount} ASE${aseCount !== 1 ? 's' : ''} assigned`
                          : 'Territory Sales Manager'}
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-[#0F2042] group-hover:translate-x-0.5 transition-all shrink-0" />
                </div>

                {/* Total Metrics */}
                <div className="grid grid-cols-2 gap-2 bg-slate-50 p-2 rounded-xl border border-slate-100 text-center">
                  <div>
                    <span className="text-[9px] font-semibold text-slate-400 uppercase tracking-wider block">
                      TOTAL CASES
                    </span>
                    <span className="text-xs font-bold text-[#0F2042]">
                      {formatNumber(tMetrics.cases)}
                    </span>
                  </div>
                  <div>
                    <span className="text-[9px] font-semibold text-slate-400 uppercase tracking-wider block">
                      TOTAL BOTTLES
                    </span>
                    <span className="text-xs font-bold text-slate-800">
                      {formatNumber(tMetrics.bottles)}
                    </span>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Pagination Controls Bar */}
      {totalItems > 0 && (
        <div className="flex items-center justify-between bg-white p-3 rounded-2xl border border-slate-200 shadow-xs text-xs">
          <button
            disabled={validCurrentPage <= 1}
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            className="flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-[#0F2042] hover:text-white text-[#0F2042] font-bold disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            <span>Prev</span>
          </button>

          <span className="font-bold text-[#0F2042]">
            Page {validCurrentPage} of {totalPages}
          </span>

          <button
            disabled={validCurrentPage >= totalPages}
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            className="flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-[#0F2042] hover:text-white text-[#0F2042] font-bold disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            <span>Next</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ASE Breakdown Bottom-Sheet Modal */}
      <AnimatePresence>
        {activeTsm && (
          <div className="absolute inset-0 z-50 flex items-end justify-center bg-slate-950/60 backdrop-blur-xs">
            <div className="absolute inset-0" onClick={() => setActiveTsm(null)} />

            <motion.div
              initial={{ opacity: 0, y: 80 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 80 }}
              transition={{ type: 'spring', damping: 28, stiffness: 300 }}
              id="tsm-ase-modal"
              className="relative w-full bg-white rounded-t-3xl shadow-2xl border border-slate-200 max-h-[90%] flex flex-col overflow-hidden z-10"
            >
              {/* Modal Header */}
              <div className="p-4 bg-[#0F2042] text-white shrink-0">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-bold text-white leading-tight">
                      {activeTsm.name}
                    </h2>
                    <p className="text-[11px] text-slate-300 font-medium mt-0.5">
                      {(activeTsm.ases?.length ?? 0) > 0
                        ? `${activeTsm.ases!.length} Assigned ASE${activeTsm.ases!.length !== 1 ? 's' : ''}`
                        : 'Territory Sales Manager'}
                    </p>
                  </div>

                  <button
                    onClick={() => setActiveTsm(null)}
                    id="close-tsm-modal-btn"
                    type="button"
                    className="w-7 h-7 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-all shrink-0"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* TSM Total Metrics Bar */}
                <div className="grid grid-cols-2 gap-2 mt-3 p-2 rounded-xl bg-black/25 border border-white/10 text-center">
                  <div>
                    <span className="text-[9px] font-semibold text-slate-300 uppercase block">
                      TOTAL CASES
                    </span>
                    <span className="text-xs sm:text-sm font-black text-white mt-0.5 block">
                      {formatNumber(Math.round(activeTsm.data[period].cases * scaleFactor))}
                    </span>
                  </div>
                  <div className="border-l border-white/10">
                    <span className="text-[9px] font-semibold text-slate-300 uppercase block">
                      TOTAL BOTTLES
                    </span>
                    <span className="text-xs sm:text-sm font-black text-white mt-0.5 block">
                      {formatNumber(Math.round(activeTsm.data[period].bottles * scaleFactor))}
                    </span>
                  </div>
                </div>
              </div>

              {/* Modal Body — ASE List */}
              <div className="p-4 overflow-y-auto space-y-2 flex-1">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5" />
                  ASE-wise Sales ({period})
                </div>

                {!activeTsm.ases || activeTsm.ases.length === 0 ? (
                  <div className="text-center py-8 text-slate-400 text-xs font-medium bg-slate-50 rounded-2xl border border-slate-100">
                    No ASEs assigned to this TSM
                  </div>
                ) : (
                  activeTsm.ases.map((ase) => {
                    const aseCases = Math.round((ase.data[period]?.cases ?? 0) * scaleFactor);
                    const aseBottles = Math.round((ase.data[period]?.bottles ?? 0) * scaleFactor);

                    return (
                      <div
                        key={ase.id}
                        id={`ase-card-${ase.id}`}
                        className="p-3 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-2"
                      >
                        {/* ASE Name */}
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-lg bg-[#0F2042]/10 text-[#0F2042] flex items-center justify-center shrink-0">
                            <UserCheck className="w-3.5 h-3.5" />
                          </div>
                          <h4 className="text-xs font-bold text-slate-900 leading-snug">
                            {ase.name}
                          </h4>
                        </div>

                        {/* ASE Metrics */}
                        <div className="grid grid-cols-2 gap-2 bg-white p-2 rounded-xl border border-slate-200/60 text-center">
                          <div>
                            <span className="text-[9px] font-semibold text-slate-400 uppercase block">
                              CASES
                            </span>
                            <span className="text-xs font-bold text-[#0F2042]">
                              {formatNumber(aseCases)}
                            </span>
                          </div>
                          <div>
                            <span className="text-[9px] font-semibold text-slate-400 uppercase block">
                              BOTTLES
                            </span>
                            <span className="text-xs font-bold text-slate-800">
                              {formatNumber(aseBottles)}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Footer Close Button */}
              <div className="p-3 bg-slate-50 border-t border-slate-200/80 shrink-0 text-center">
                <button
                  onClick={() => setActiveTsm(null)}
                  type="button"
                  className="w-full py-2 rounded-xl bg-[#0F2042] text-white font-semibold text-xs hover:bg-[#0A1428] transition-all"
                >
                  Close
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
