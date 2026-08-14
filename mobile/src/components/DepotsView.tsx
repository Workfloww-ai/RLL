import React, { useState, useMemo, useEffect } from 'react';
import { Depot, Period } from '../types';
import { formatNumber } from '../lib/utils';
import { MapPin, Search, ChevronRight, X, ArrowUpDown, ChevronLeft } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

interface DepotsViewProps {
  depots: Depot[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
}

type SortOption = 'alpha-asc' | 'alpha-desc' | 'cases-desc' | 'cases-asc';

export const DepotsView: React.FC<DepotsViewProps> = ({
  depots,
  period,
  scaleFactor,
  selectedHq,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeDepot, setActiveDepot] = useState<Depot | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOption>('alpha-asc'); // Default: Alphabetical (A-Z)
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(15);

  // Filter and Sort depots (Default: A-Z Alphabetical)
  const sortedFilteredDepots = useMemo(() => {
    const filtered = depots.filter((d) => {
      const matchHq = selectedHq === 'All Headquarters' || d.hqName.toLowerCase() === selectedHq.toLowerCase();
      const matchSearch =
        d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        d.hqName.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (d.address && d.address.toLowerCase().includes(searchTerm.toLowerCase()));
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
  }, [depots, selectedHq, searchTerm, sortOrder, period, scaleFactor]);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, selectedHq, sortOrder, itemsPerPage]);

  const totalItems = sortedFilteredDepots.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / itemsPerPage));
  const validCurrentPage = Math.min(currentPage, totalPages);

  const paginatedDepots = useMemo(() => {
    const start = (validCurrentPage - 1) * itemsPerPage;
    return sortedFilteredDepots.slice(start, start + itemsPerPage);
  }, [sortedFilteredDepots, validCurrentPage, itemsPerPage]);

  return (
    <div className="space-y-3">
      {/* Controls Bar: Search + Sorting Selector */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search depots..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              id="depot-search-input"
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
            {Math.min(validCurrentPage * itemsPerPage, totalItems)} of {totalItems} depot(s)
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

      {/* Depots Cards List */}
      {paginatedDepots.length === 0 ? (
        <div className="text-center py-8 bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-bold text-slate-700">No depots found</p>
        </div>
      ) : (
        <div className="space-y-2">
          {paginatedDepots.map((depot, idx) => {
            const raw = depot.data[period];
            const dMetrics = {
              cases: Math.round(raw.cases * scaleFactor),
              bottles: Math.round(raw.bottles * scaleFactor),
            };

            return (
              <motion.div
                key={depot.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, delay: idx * 0.03 }}
                onClick={() => setActiveDepot(depot)}
                id={`depot-card-${depot.id}`}
                className="p-3.5 rounded-2xl bg-white border border-slate-200/80 hover:border-slate-300 transition-all cursor-pointer group space-y-2"
              >
                {/* Header */}
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <h4 className="text-xs sm:text-sm font-bold text-slate-900 group-hover:text-[#0F2042] transition-colors truncate">
                      {depot.name}
                    </h4>
                    <p className="text-[10px] text-slate-400 font-medium flex items-center gap-1 mt-0.5">
                      <MapPin className="w-2.5 h-2.5 text-[#0F2042]" />
                      HQ: {depot.hqName}
                    </p>
                  </div>

                  <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-[#0F2042] group-hover:translate-x-0.5 transition-all shrink-0" />
                </div>

                {/* Metrics 2 Columns */}
                <div className="grid grid-cols-2 gap-2 bg-slate-50 p-2 rounded-xl border border-slate-100 text-center">
                  <div>
                    <span className="text-[9px] font-semibold text-slate-400 uppercase block">CASES</span>
                    <span className="text-xs font-bold text-[#0F2042]">{formatNumber(dMetrics.cases)}</span>
                  </div>

                  <div>
                    <span className="text-[9px] font-semibold text-slate-400 uppercase block">BOTTLES</span>
                    <span className="text-xs font-bold text-slate-800">{formatNumber(dMetrics.bottles)}</span>
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

      {/* Depot Detail Modal */}
      <AnimatePresence>
        {activeDepot && (
          <div className="absolute inset-0 z-50 flex items-end justify-center bg-slate-950/60 backdrop-blur-xs">
            <div className="absolute inset-0" onClick={() => setActiveDepot(null)} />

            <motion.div
              initial={{ opacity: 0, y: 80 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 80 }}
              className="relative w-full bg-white rounded-t-3xl shadow-2xl border border-slate-200 max-h-[90%] flex flex-col overflow-hidden z-10"
            >
              {/* Modal Header */}
              <div className="p-4 bg-[#0F2042] text-white flex items-center justify-between gap-3 shrink-0">
                <div>
                  <h3 className="text-sm font-bold text-white leading-tight truncate">
                    {activeDepot.name}
                  </h3>
                  <p className="text-[11px] text-slate-300 font-medium mt-0.5">
                    HQ: {activeDepot.hqName}
                  </p>
                </div>

                <button
                  onClick={() => setActiveDepot(null)}
                  type="button"
                  className="w-7 h-7 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center shrink-0"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Brands Breakdown List inside this Depot */}
              <div className="p-4 overflow-y-auto space-y-2 flex-1">
                <div className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Depot Brand Sales ({period})
                </div>

                {activeDepot.brands.map((b) => {
                  const bRaw = b.data[period];
                  const bCases = Math.round(bRaw.cases * scaleFactor);
                  const bBottles = Math.round(bRaw.bottles * scaleFactor);

                  return (
                    <div
                      key={b.brandId}
                      className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 space-y-1.5"
                    >
                      <h5 className="text-xs font-bold text-slate-900 leading-snug">
                        {b.brandName}
                      </h5>

                      <div className="grid grid-cols-2 gap-2 bg-white p-1.5 rounded-lg border border-slate-200/60 text-center">
                        <div>
                          <span className="text-[9px] font-semibold text-slate-400 uppercase block">CASES</span>
                          <span className="text-xs font-bold text-[#0F2042]">{formatNumber(bCases)}</span>
                        </div>

                        <div>
                          <span className="text-[9px] font-semibold text-slate-400 uppercase block">BOTTLES</span>
                          <span className="text-xs font-bold text-slate-800">{formatNumber(bBottles)}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Modal Footer */}
              <div className="p-3 bg-slate-50 border-t border-slate-200/80 shrink-0 text-center">
                <button
                  onClick={() => setActiveDepot(null)}
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
