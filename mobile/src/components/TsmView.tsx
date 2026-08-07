import React, { useState } from 'react';
import { TSM, Period } from '../types';
import { formatNumber } from '../lib/utils';
import { UserCheck, Search } from 'lucide-react';
import { motion } from 'motion/react';

interface TsmViewProps {
  tsms: TSM[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
}

export const TsmView: React.FC<TsmViewProps> = ({
  tsms,
  period,
  scaleFactor,
  selectedHq,
}) => {
  const [searchTerm, setSearchTerm] = useState('');

  // Filter TSMs by HQ selection and Search Term
  const filteredTsms = tsms.filter((t) => {
    const matchHq =
      selectedHq === 'All Headquarters' ||
      (t.hqLocation && t.hqLocation.toLowerCase() === selectedHq.toLowerCase());
    const matchSearch =
      t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (t.hqLocation && t.hqLocation.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchHq && matchSearch;
  });

  return (
    <div className="space-y-3">
      {/* Search Input */}
      <div className="relative">
        <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
        <input
          type="text"
          placeholder="Search TSM name..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          id="tsm-search-input"
          className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-3 py-1.5 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#0F2042]"
        />
      </div>

      {/* TSM Cards List */}
      {filteredTsms.length === 0 ? (
        <div className="text-center py-8 bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-bold text-slate-700">No TSM found</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredTsms.map((tsm, idx) => {
            const raw = tsm.data[period];
            const tMetrics = {
              cases: Math.round(raw.cases * scaleFactor),
              bottles: Math.round(raw.bottles * scaleFactor),
            };

            return (
              <motion.div
                key={tsm.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, delay: idx * 0.03 }}
                id={`tsm-card-${tsm.id}`}
                className="p-3.5 rounded-2xl bg-white border border-slate-200/80 space-y-2 shadow-2xs"
              >
                {/* Header */}
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="w-8 h-8 rounded-xl bg-[#0F2042]/10 text-[#0F2042] flex items-center justify-center shrink-0">
                    <UserCheck className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-xs sm:text-sm font-bold text-slate-900 truncate">
                      {tsm.name}
                    </h4>
                    <p className="text-[10px] text-slate-400 font-medium">
                      Territory Sales Manager
                    </p>
                  </div>
                </div>

                {/* Total Metrics (Cases & Bottles) */}
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
    </div>
  );
};
