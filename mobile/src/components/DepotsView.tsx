import React, { useState } from 'react';
import { Depot, Period } from '../types';
import { formatNumber } from '../lib/utils';
import { MapPin, Search, ChevronRight, X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

interface DepotsViewProps {
  depots: Depot[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
}

export const DepotsView: React.FC<DepotsViewProps> = ({
  depots,
  period,
  scaleFactor,
  selectedHq,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeDepot, setActiveDepot] = useState<Depot | null>(null);

  // Filter depots by HQ and Search Term
  const filteredDepots = depots.filter((d) => {
    const matchHq = selectedHq === 'All Headquarters' || d.hqName.toLowerCase() === selectedHq.toLowerCase();
    const matchSearch =
      d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      d.hqName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (d.address && d.address.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchHq && matchSearch;
  });

  return (
    <div className="space-y-3">
      {/* Depot Search Input */}
      <div className="relative">
        <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
        <input
          type="text"
          placeholder="Search depots..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          id="depot-search-input"
          className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-3 py-1.5 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#0F2042]"
        />
      </div>

      {/* Depots Cards List */}
      {filteredDepots.length === 0 ? (
        <div className="text-center py-8 bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-bold text-slate-700">No depots found</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredDepots.map((depot, idx) => {
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

              {/* Brands Breakdown List inside this Depot (No grey category badges) */}
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
