import React from 'react';
import { Period } from '../types';
import { Calendar, MapPin } from 'lucide-react';

interface HeaderProps {
  period: Period;
  setPeriod: (period: Period) => void;
  dateFrom: string;
  setDateFrom: (date: string) => void;
  dateTo: string;
  setDateTo: (date: string) => void;
  selectedHq: string;
  setSelectedHq: (hq: string) => void;
  headquartersList: string[];
}

export const Header: React.FC<HeaderProps> = ({
  period,
  setPeriod,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  selectedHq,
  setSelectedHq,
  headquartersList,
}) => {
  const periods: Period[] = ['Daily', 'MTD', 'YTD'];
  const TODAY = '2026-05-31';

  const handlePeriodChange = (p: Period) => {
    setPeriod(p);
    if (p === 'MTD') {
      setDateFrom('2026-05-01');
      setDateTo(TODAY);
    } else if (p === 'YTD') {
      setDateFrom('2026-04-01');
      setDateTo(TODAY);
    } else if (p === 'Daily') {
      setDateFrom(TODAY);
      setDateTo(TODAY);
    }
  };

  return (
    <header className="bg-[#0F2042] text-white rounded-b-2xl shadow-md px-3.5 py-3 shrink-0 space-y-2.5">
      {/* Row 1: Logo & Title + Period Pills */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <img
            src="/images/rll.png"
            alt="RLL Logo"
            className="w-7 h-7 object-contain bg-white rounded-lg p-0.5 shrink-0 border border-white/20 shadow-xs"
          />
          <div>
            <h1 className="text-sm font-bold text-white tracking-tight leading-none">
              Sales Dashboard
            </h1>
            <p className="text-[10px] text-slate-300 font-medium leading-tight mt-0.5">
              Rajasthan
            </p>
          </div>
        </div>

        {/* Minimal Period Switcher Segment */}
        <div className="flex items-center bg-black/25 p-0.5 rounded-lg border border-white/10">
          {periods.map((p) => (
            <button
              key={p}
              onClick={() => handlePeriodChange(p)}
              id={`period-btn-${p.toLowerCase()}`}
              type="button"
              className={`py-1 px-2.5 rounded-md text-[11px] font-bold transition-all ${
                period === p
                  ? 'bg-white text-[#0F2042] shadow-xs'
                  : 'text-slate-300 hover:text-white'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Row 2: Inline Controls Bar (All HQ Dropdown & Date Selection) */}
      <div className="grid grid-cols-12 gap-2 bg-black/20 p-2 rounded-xl border border-white/10 text-xs">
        {/* Headquarters Dropdown */}
        <div className={`${period === 'Daily' ? 'col-span-7' : 'col-span-5'} relative flex items-center bg-white/10 rounded-lg px-2 py-1 border border-white/15`}>
          <MapPin className="w-3.5 h-3.5 text-slate-300 shrink-0 mr-1" />
          <select
            value={selectedHq}
            onChange={(e) => setSelectedHq(e.target.value)}
            id="header-hq-select"
            className="w-full bg-transparent text-white font-semibold text-[11px] focus:outline-none cursor-pointer appearance-none truncate pr-2"
          >
            {headquartersList.map((hq) => (
              <option key={hq} value={hq} className="bg-[#0F2042] text-white">
                {hq}
              </option>
            ))}
          </select>
        </div>

        {/* Date Selector: Single Date for Daily (col-span-5), Range for MTD/YTD (col-span-7) */}
        {period === 'Daily' ? (
          <div className="col-span-5 flex items-center justify-center bg-white/10 rounded-lg px-2 py-1 border border-white/15 text-[10px]">
            <div className="flex items-center gap-1.5 min-w-0 justify-center w-full">
              <Calendar className="w-3 h-3 text-slate-300 shrink-0" />
              <input
                type="date"
                value={dateFrom}
                max={TODAY}
                onChange={(e) => {
                  const val = e.target.value;
                  setDateFrom(val);
                  setDateTo(val);
                }}
                id="header-date-single"
                className="bg-transparent text-white font-bold focus:outline-none cursor-pointer text-[10px] text-center w-full"
              />
            </div>
          </div>
        ) : (
          <div className="col-span-7 flex items-center justify-between gap-1 bg-white/10 rounded-lg px-2 py-1 border border-white/15 text-[10px]">
            <div className="flex items-center gap-1 min-w-0">
              <Calendar className="w-3 h-3 text-slate-300 shrink-0" />
              <input
                type="date"
                value={dateFrom}
                max={TODAY}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                }}
                id="header-date-from"
                className="bg-transparent text-white font-bold w-[78px] focus:outline-none cursor-pointer text-[10px]"
              />
            </div>
            <span className="text-slate-400 font-bold">-</span>
            <div className="flex items-center min-w-0">
              <input
                type="date"
                value={dateTo}
                max={TODAY}
                onChange={(e) => {
                  setDateTo(e.target.value);
                }}
                id="header-date-to"
                className="bg-transparent text-white font-bold w-[78px] focus:outline-none cursor-pointer text-[10px]"
              />
            </div>
          </div>
        )}
      </div>
    </header>
  );
};
