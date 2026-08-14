import React from 'react';
import { Company, Period } from '../types';
import { formatNumber } from '../lib/utils';
import { ChevronRight } from 'lucide-react';
import { motion } from 'motion/react';

interface CompanyCardProps {
  company: Company;
  period: Period;
  scaleFactor: number;
  maxVolume: number;
  onClick: () => void;
  index: number;
}

export const CompanyCard: React.FC<CompanyCardProps> = ({
  company,
  period,
  scaleFactor,
  onClick,
  index,
}) => {
  const rawData = company.data[period];
  const cases = Math.round(rawData.cases * scaleFactor);
  const bottles = Math.round(rawData.bottles * scaleFactor);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, delay: index * 0.02 }}
      onClick={onClick}
      id={`company-card-${company.id}`}
      className={`group bg-white rounded-2xl p-3.5 border transition-all duration-150 cursor-pointer ${
        company.isPinned
          ? 'border-[#0F2042]/30 bg-gradient-to-r from-slate-50 via-white to-white shadow-xs'
          : 'border-slate-200/80 hover:border-slate-300 hover:shadow-xs'
      }`}
    >
      {/* Header: Name + Pin Tag (No Initial Badge) */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <h3 className="font-bold text-xs sm:text-sm text-slate-900 truncate group-hover:text-[#0F2042] transition-colors">
              {company.name}
            </h3>
            {company.isPinned && (
              <span className="px-1.5 py-0.2 text-[9px] font-bold bg-[#0F2042] text-white rounded">
                Pinned
              </span>
            )}
          </div>
          <p className="text-[10px] text-slate-400 font-medium">
            {company.brands.length} {company.brands.length === 1 ? 'Brand' : 'Brands'}
          </p>
        </div>

        <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-[#0F2042] group-hover:translate-x-0.5 transition-all shrink-0" />
      </div>

      {/* Primary Metrics Row */}
      <div className="grid grid-cols-2 gap-2 bg-slate-50 p-2 rounded-xl border border-slate-100 text-center">
        <div>
          <span className="text-[9px] font-semibold text-slate-400 uppercase tracking-wider block">
            CASES
          </span>
          <span className="text-xs sm:text-sm font-black text-[#0F2042] block mt-0.5">
            {formatNumber(cases)}
          </span>
        </div>

        <div>
          <span className="text-[9px] font-semibold text-slate-400 uppercase tracking-wider block">
            BOTTLES
          </span>
          <span className="text-xs sm:text-sm font-bold text-slate-800 block mt-0.5">
            {formatNumber(bottles)}
          </span>
        </div>
      </div>
    </motion.div>
  );
};
