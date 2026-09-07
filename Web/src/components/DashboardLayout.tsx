import React from 'react';
import { Package, Map, Users, LogOut, Settings, Shield } from 'lucide-react';
import { ViewState } from '../types';

interface DashboardLayoutProps {
  currentView: ViewState;
  onViewChange: (view: ViewState) => void;
  onLogout?: () => void;
  userName?: string | null;
  children: React.ReactNode;
}

export default function DashboardLayout({ currentView, onViewChange, onLogout, userName, children }: DashboardLayoutProps) {
  const displayUserName = userName || 'Admin User';
  const userInitial = displayUserName.charAt(0).toUpperCase();
  const navItems = [
    { id: 'stock' as ViewState, label: 'Sales Upload', icon: Package },
    { id: 'territory' as ViewState, label: 'Territory Management', icon: Map },
    { id: 'headcount' as ViewState, label: 'User Management', icon: Users },
    { id: 'roles' as ViewState, label: 'Role Management', icon: Shield },
    { id: 'settings' as ViewState, label: 'Security & Settings', icon: Settings },
  ];

  return (
    <div className="flex h-screen bg-[#F8FAFC] font-sans text-slate-800 overflow-hidden selection:bg-[#0D3B8E] selection:text-white">
      {/* Sleek Royal Blue Sidebar */}
      <aside className="w-64 bg-[#0D3B8E] flex flex-col shrink-0 shadow-xl z-20">
        {/* Brand Header */}
        <div className="p-6 mb-2 flex items-center gap-3">
          <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center p-1.5 shadow-sm">
            <img src="/images/rll logo.svg" alt="RLL Logo" className="w-full h-full object-contain" />
          </div>
          <div>
            <h1 className="text-white font-extrabold tracking-tight text-lg leading-tight">RLL</h1>
            <p className="text-[10px] text-blue-200/80 font-medium tracking-wide">Admin Portal</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 space-y-1">
          <div className="text-blue-200/60 text-[10px] uppercase font-bold tracking-widest px-3 mb-2">Operations</div>
          {navItems.map(item => {
            const isActive = currentView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs transition-all duration-200 cursor-pointer ${
                  isActive 
                    ? 'bg-[#144DB8] text-white font-bold shadow-sm' 
                    : 'text-blue-100/80 hover:bg-white/10 hover:text-white font-medium'
                }`}
              >
                <item.icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-white' : 'text-blue-200/70'}`} />
                <span className="truncate text-left">{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Footer Actions */}
        <div className="p-3 border-t border-blue-900/40">
          <button 
            onClick={onLogout}
            className="w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold text-blue-100/80 hover:bg-red-500/20 hover:text-white transition-all duration-200 cursor-pointer"
          >
            <LogOut className="w-4 h-4 shrink-0 text-blue-200/70" />
            <span className="truncate text-left">Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Viewport */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Minimal White Topbar */}
        <header className="bg-white border-b border-slate-200/80 h-12 flex items-center justify-between px-6 shadow-2xs shrink-0 z-10">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400 font-medium hover:text-slate-600 transition-colors cursor-pointer">Admin Panel</span>
            <span className="text-slate-300">/</span>
            <span className="text-[#0D3B8E] font-bold">
              {navItems.find(i => i.id === currentView)?.label}
            </span>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="text-right">
              <p className="text-xs font-bold text-slate-900 leading-none">{displayUserName}</p>
              <p className="text-[9px] text-[#0D3B8E] font-bold uppercase tracking-wider mt-0.5">Admin</p>
            </div>
            <div className="w-7 h-7 bg-[#0D3B8E] text-white rounded-full font-bold text-xs flex items-center justify-center shadow-xs">
              {userInitial}
            </div>
          </div>
        </header>

        {/* Content Container */}
        <div className="flex-1 overflow-hidden p-4 max-w-7xl mx-auto w-full flex flex-col min-h-0">
          {children}
        </div>
      </main>
    </div>
  );
}
