import React, { useRef } from 'react';
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
  latestSaleDate?: string;
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
  latestSaleDate,
}) => {
  const periods: Period[] = ['Daily', 'MTD', 'YTD'];
  const singleDateRef = useRef<HTMLInputElement>(null);
  const dateFromRef = useRef<HTMLInputElement>(null);
  const dateToRef = useRef<HTMLInputElement>(null);

  const openPicker = (ref: React.RefObject<HTMLInputElement | null>) => {
    if (ref.current) {
      try {
        if ('showPicker' in ref.current) {
          ref.current.showPicker();
        } else {
          ref.current.focus();
        }
      } catch {
        ref.current.focus();
      }
    }
  };

  const handlePeriodChange = (p: Period) => {
    setPeriod(p);
    const activeDate = dateTo || dateFrom || latestSaleDate || new Date().toISOString().split('T')[0];
    const year = activeDate.substring(0, 4);
    const month = activeDate.substring(5, 7);

    if (p === 'MTD') {
      setDateFrom(`${year}-${month}-01`);
      setDateTo(activeDate);
    } else if (p === 'YTD') {
      const m = parseInt(month, 10);
      const y = parseInt(year, 10);
      const fyStartYear = m >= 4 ? y : y - 1;
      setDateFrom(`${fyStartYear}-04-01`);
      setDateTo(activeDate);
    } else if (p === 'Daily') {
      setDateFrom(activeDate);
      setDateTo(activeDate);
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
          <div
            onClick={() => openPicker(singleDateRef)}
            className="col-span-5 flex items-center justify-center bg-white/10 hover:bg-white/15 active:bg-white/20 transition-all rounded-lg px-2 py-1 border border-white/15 text-[10px] cursor-pointer"
          >
            <div className="flex items-center gap-1.5 min-w-0 justify-center w-full cursor-pointer">
              <Calendar className="w-3 h-3 text-slate-300 shrink-0 pointer-events-none" />
              <input
                ref={singleDateRef}
                type="date"
                value={dateFrom}
                onKeyDown={(e) => e.preventDefault()}
                onClick={(e) => {
                  e.stopPropagation();
                  openPicker(singleDateRef);
                }}
                onChange={(e) => {
                  const val = e.target.value;
                  if (val) {
                    setDateFrom(val);
                    setDateTo(val);
                  }
                }}
                id="header-date-single"
                className="bg-transparent text-white font-bold focus:outline-none cursor-pointer text-[10px] text-center w-full"
              />
            </div>
          </div>
        ) : (
          <div className="col-span-7 flex items-center justify-between gap-1 bg-white/10 rounded-lg px-2 py-1 border border-white/15 text-[10px]">
            {/* From Date Box */}
            <div
              onClick={() => openPicker(dateFromRef)}
              className="flex items-center gap-1 min-w-0 cursor-pointer hover:bg-white/10 px-1 py-0.5 rounded transition-all"
            >
              <Calendar className="w-3 h-3 text-slate-300 shrink-0 pointer-events-none" />
              <input
                ref={dateFromRef}
                type="date"
                value={dateFrom}
                onKeyDown={(e) => e.preventDefault()}
                onClick={(e) => {
                  e.stopPropagation();
                  openPicker(dateFromRef);
                }}
                onChange={(e) => {
                  if (e.target.value) setDateFrom(e.target.value);
                }}
                id="header-date-from"
                className="bg-transparent text-white font-bold w-[78px] focus:outline-none cursor-pointer text-[10px]"
              />
            </div>

            <span className="text-slate-400 font-bold select-none">-</span>

            {/* To Date Box */}
            <div
              onClick={() => openPicker(dateToRef)}
              className="flex items-center gap-1 min-w-0 cursor-pointer hover:bg-white/10 px-1 py-0.5 rounded transition-all"
            >
              <Calendar className="w-3 h-3 text-slate-300 shrink-0 pointer-events-none" />
              <input
                ref={dateToRef}
                type="date"
                value={dateTo}
                onKeyDown={(e) => e.preventDefault()}
                onClick={(e) => {
                  e.stopPropagation();
                  openPicker(dateToRef);
                }}
                onChange={(e) => {
                  if (e.target.value) setDateTo(e.target.value);
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
