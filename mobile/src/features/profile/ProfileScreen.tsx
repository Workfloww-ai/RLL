import React from 'react';
import { User, Phone, Mail, Shield, Store, LogOut, CheckCircle2 } from 'lucide-react';

interface ProfileScreenProps {
  user: any;
  onLogout: () => void;
}

export const ProfileScreen: React.FC<ProfileScreenProps> = ({ user, onLogout }) => {
  const firstName = user?.first_name || user?.name?.split(' ')[0] || 'Executive';
  const lastName = user?.last_name || user?.name?.split(' ').slice(1).join(' ') || '';
  const fullName = `${firstName} ${lastName}`.trim() || user?.name || 'Account Holder';
  const email = user?.email || 'N/A';
  const phone = user?.phone;
  const designation = user?.role_name || user?.role || 'Territory Sales Manager (TSM)';
  const depotName = user?.depot_name || user?.depotName || user?.depot || user?.hq_location || 'Jaipur Central Depot';

  const initials = `${firstName.charAt(0)}${lastName ? lastName.charAt(0) : ''}`.toUpperCase() || 'U';

  return (
    <div className="flex-1 overflow-y-auto bg-slate-50 p-4 space-y-4">
      {/* Top Profile Header Card */}
      <div className="bg-gradient-to-br from-[#0F2042] to-[#1E3A70] text-white rounded-2xl p-5 shadow-lg border border-slate-700/50 relative overflow-hidden">
        <div className="absolute -right-6 -bottom-6 w-28 h-28 bg-white/5 rounded-full blur-xl pointer-events-none" />
        
        <div className="flex items-center gap-4 relative z-10">
          <div className="w-16 h-16 rounded-2xl bg-amber-500 text-slate-950 font-black text-xl flex items-center justify-center shadow-md border-2 border-amber-300 shrink-0">
            {initials}
          </div>

          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-extrabold text-white truncate tracking-tight">
              {fullName}
            </h2>
          </div>
        </div>
      </div>

      {/* Account Info Details Card */}
      <div className="bg-white rounded-2xl p-4 shadow-xs border border-slate-200 space-y-3">
        <h3 className="text-xs font-black uppercase tracking-wider text-slate-400 px-1">
          Account Details
        </h3>

        <div className="space-y-2.5 text-xs">
          {/* Phone Number */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-100">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center shrink-0">
                <Phone className="w-4 h-4" />
              </div>
              <div>
                <span className="text-[10px] text-slate-400 font-semibold block">Phone Number</span>
                <span className="font-bold text-slate-800">{phone}</span>
              </div>
            </div>
          </div>

          {/* Email Address */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-100">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-700 flex items-center justify-center shrink-0">
                <Mail className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <span className="text-[10px] text-slate-400 font-semibold block">Email Address</span>
                <span className="font-bold text-slate-800 truncate block max-w-[200px]">{email}</span>
              </div>
            </div>
          </div>

          {/* Designation */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-100">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center shrink-0">
                <Shield className="w-4 h-4" />
              </div>
              <div>
                <span className="text-[10px] text-slate-400 font-semibold block">Designation</span>
                <span className="font-bold text-slate-800">{designation}</span>
              </div>
            </div>
          </div>

          {/* Depot Assigned */}
          <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-100">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-700 flex items-center justify-center shrink-0">
                <Store className="w-4 h-4" />
              </div>
              <div>
                <span className="text-[10px] text-slate-400 font-semibold block">Belongs to Depot</span>
                <span className="font-bold text-slate-800">{depotName}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sign Out Action Button */}
      <div className="pt-1">
        <button
          onClick={onLogout}
          type="button"
          id="profile-sign-out-btn"
          className="w-full bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 font-bold py-3 rounded-2xl text-xs flex items-center justify-center gap-2 shadow-xs transition-all cursor-pointer active:scale-98"
        >
          <LogOut className="w-4 h-4 text-red-600" />
          <span>Sign Out of Account</span>
        </button>
      </div>

      <div className="text-center text-[10px] text-slate-400 py-1">
        Rajasthan Liquor Limited • Mobile Portal v1.0
      </div>
    </div>
  );
};
