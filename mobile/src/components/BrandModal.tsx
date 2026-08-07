import React, { useState } from 'react';
import { Company, Period } from '../types';
import { formatNumber } from '../lib/utils';
import { X, Search } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

interface BrandModalProps {
  company: Company | null;
  period: Period;
  scaleFactor: number;
  onClose: () => void;
}

export const BrandModal: React.FC<BrandModalProps> = ({
  company,
  period,
  scaleFactor,
  onClose,
}) => {
  const [searchTerm, setSearchTerm] = useState('');

  if (!company) return null;

  const rawCompanyData = company.data[period];
  const companyMetrics = {
    cases: Math.round(rawCompanyData.cases * scaleFactor),
    bottles: Math.round(rawCompanyData.bottles * scaleFactor),
  };

  // Filter brands based on search
  const filteredBrands = company.brands.filter((b) =>
    b.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <AnimatePresence>
      <div className="absolute inset-0 z-50 flex items-end justify-center bg-slate-950/60 backdrop-blur-xs">
        {/* Click outside backdrop */}
        <div className="absolute inset-0" onClick={onClose} />

        {/* Modal Window Container */}
        <motion.div
          initial={{ opacity: 0, y: 80 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 80 }}
          transition={{ type: 'spring', damping: 28, stiffness: 300 }}
          id="company-brand-modal"
          className="relative w-full bg-white rounded-t-3xl shadow-2xl border border-slate-200 max-h-[90%] flex flex-col overflow-hidden z-10"
        >
          {/* Header */}
          <div className="p-4 bg-[#0F2042] text-white shrink-0">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-bold text-white leading-tight">
                  {company.name}
                </h2>
                <p className="text-[11px] text-slate-300 font-medium mt-0.5">
                  {company.brands.length} Active {company.brands.length === 1 ? 'Brand' : 'Brands'}
                </p>
              </div>

              <button
                onClick={onClose}
                id="close-modal-btn"
                type="button"
                className="w-7 h-7 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-all shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Metrics Bar */}
            <div className="grid grid-cols-2 gap-2 mt-3 p-2 rounded-xl bg-black/25 border border-white/10 text-center">
              <div>
                <span className="text-[9px] font-semibold text-slate-300 uppercase block">
                  CASES
                </span>
                <span className="text-xs sm:text-sm font-black text-white mt-0.5 block">
                  {formatNumber(companyMetrics.cases)}
                </span>
              </div>

              <div className="border-l border-white/10">
                <span className="text-[9px] font-semibold text-slate-300 uppercase block">
                  BOTTLES
                </span>
                <span className="text-xs sm:text-sm font-black text-white mt-0.5 block">
                  {formatNumber(companyMetrics.bottles)}
                </span>
              </div>
            </div>
          </div>

          {/* Modal Body: Brand List */}
          <div className="p-4 overflow-y-auto space-y-3 flex-1">
            {/* Search input for brands */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search brand"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                id="brand-search-input"
                className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-1.5 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#0F2042]"
              />
            </div>

            {/* Scrollable list of brand cards without category badges */}
            {filteredBrands.length === 0 ? (
              <div className="text-center py-6 text-slate-400 text-xs font-medium">
                No brands match "{searchTerm}"
              </div>
            ) : (
              filteredBrands.map((brand) => {
                const rawBData = brand.data[period];
                const bCases = Math.round(rawBData.cases * scaleFactor);
                const bBottles = Math.round(rawBData.bottles * scaleFactor);

                return (
                  <div
                    key={brand.id}
                    id={`brand-card-${brand.id}`}
                    className="p-3 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="text-xs font-bold text-slate-900 leading-snug">
                        {brand.name}
                      </h4>
                    </div>

                    <div className="grid grid-cols-2 gap-2 bg-white p-2 rounded-xl border border-slate-200/60 text-center">
                      <div>
                        <span className="text-[9px] font-semibold text-slate-400 uppercase block">
                          CASES
                        </span>
                        <span className="text-xs font-bold text-[#0F2042]">
                          {formatNumber(bCases)}
                        </span>
                      </div>

                      <div>
                        <span className="text-[9px] font-semibold text-slate-400 uppercase block">
                          BOTTLES
                        </span>
                        <span className="text-xs font-bold text-slate-800">
                          {formatNumber(bBottles)}
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
              onClick={onClose}
              type="button"
              className="w-full py-2 rounded-xl bg-[#0F2042] text-white font-semibold text-xs hover:bg-[#0A1428] transition-all"
            >
              Close
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
