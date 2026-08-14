import React from 'react';
import { ViewMode } from '../types';
import { Building2, Layers, Users, User } from 'lucide-react';

interface FooterNavProps {
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
}

export const FooterNav: React.FC<FooterNavProps> = ({ viewMode, setViewMode }) => {
  return (
    <div className="bg-[#0A1428] text-white border-t border-white/10 px-2 py-2 flex items-center justify-around shrink-0 relative z-20 shadow-lg">
      <button
        onClick={() => setViewMode('companies')}
        id="footer-nav-companies"
        type="button"
        className={`flex flex-col items-center gap-0.5 py-1 px-3 rounded-xl transition-all ${
          viewMode === 'companies'
            ? 'bg-white text-[#0F2042] font-extrabold shadow-md scale-105'
            : 'text-slate-300 hover:text-white font-semibold'
        }`}
      >
        <Building2 className="w-4 h-4" />
        <span className="text-[10px] tracking-tight">Companies</span>
      </button>

      <button
        onClick={() => setViewMode('groups')}
        id="footer-nav-groups"
        type="button"
        className={`flex flex-col items-center gap-0.5 py-1 px-3 rounded-xl transition-all ${
          viewMode === 'groups' || viewMode === 'depots'
            ? 'bg-white text-[#0F2042] font-extrabold shadow-md scale-105'
            : 'text-slate-300 hover:text-white font-semibold'
        }`}
      >
        <Layers className="w-4 h-4" />
        <span className="text-[10px] tracking-tight">Groups</span>
      </button>

      <button
        onClick={() => setViewMode('tsm')}
        id="footer-nav-tsm"
        type="button"
        className={`flex flex-col items-center gap-0.5 py-1 px-3 rounded-xl transition-all ${
          viewMode === 'tsm'
            ? 'bg-white text-[#0F2042] font-extrabold shadow-md scale-105'
            : 'text-slate-300 hover:text-white font-semibold'
        }`}
      >
        <Users className="w-4 h-4" />
        <span className="text-[10px] tracking-tight">TSM</span>
      </button>

      <button
        onClick={() => setViewMode('profile')}
        id="footer-nav-profile"
        type="button"
        className={`flex flex-col items-center gap-0.5 py-1 px-3 rounded-xl transition-all ${
          viewMode === 'profile'
            ? 'bg-white text-[#0F2042] font-extrabold shadow-md scale-105'
            : 'text-slate-300 hover:text-white font-semibold'
        }`}
      >
        <User className="w-4 h-4" />
        <span className="text-[10px] tracking-tight">Profile</span>
      </button>
    </div>
  );
};
