import React from 'react';
import { Package, Map, Users, LogOut, LayoutDashboard, Settings } from 'lucide-react';
import { ViewState } from '../types';

interface DashboardLayoutProps {
  currentView: ViewState;
  onViewChange: (view: ViewState) => void;
  onLogout?: () => void;
  userName?: string | null;
  children: React.ReactNode;
}

export default function DashboardLayout({ currentView, onViewChange, onLogout, userName, children }: DashboardLayoutProps) {
  const displayUserName = userName || 'Rahul Sharma';
  const userInitial = displayUserName.charAt(0).toUpperCase();
  const navItems = [
    { id: 'stock' as ViewState, label: 'Sales Upload', icon: Package },
    { id: 'territory' as ViewState, label: 'Territory Management', icon: Map },
    { id: 'headcount' as ViewState, label: 'User Management', icon: Users },
  ];

  return (
    <div className="flex h-screen bg-[#F4F7FA] font-sans text-slate-800 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-72 bg-[#004B87] flex flex-col shadow-xl shrink-0">
        <div className="p-6 mb-4">
          <div className="flex items-center gap-3">
            <img src="/images/rll.png" alt="RLL Logo" className="w-12 h-12 object-contain bg-white rounded p-0.5" />
            <h1 className="text-white font-bold tracking-tight text-xl">RLL ADMIN</h1>
          </div>
        </div>

        <nav className="flex-1 px-4 space-y-1">
          <div className="text-blue-200 text-[10px] uppercase font-bold tracking-widest px-2 mb-2">Operations</div>
          {navItems.map(item => (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors border-l-4 ${
                currentView === item.id 
                  ? 'bg-white/10 text-white border-[#ED1C24]' 
                  : 'text-blue-100 hover:bg-white/5 border-transparent'
              }`}
            >
              <item.icon className="w-5 h-5 shrink-0" />
              <span className="font-medium whitespace-nowrap text-left">{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="p-6 border-t border-white/10 space-y-1">
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium text-blue-100 hover:bg-white/5 transition-colors border-l-4 border-transparent text-sm">
            <Settings className="w-4 h-4" />
            Settings
          </button>
          <button 
            onClick={onLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium text-blue-200 hover:bg-white/5 transition-colors border-l-4 border-transparent text-sm mt-1"
          >
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-white border-b border-slate-200 h-16 flex items-center justify-between px-8 shadow-sm shrink-0">
          <div className="flex items-center gap-2 text-slate-500 text-sm font-medium">
            <span className="hover:text-[#004B87] cursor-pointer">Admin Panel</span>
            <span className="text-slate-300">/</span>
            <span className="text-[#004B87]">
              {navItems.find(i => i.id === currentView)?.label}
            </span>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 pl-4 border-l border-slate-200">
              <div className="text-right">
                <p className="text-xs font-bold text-slate-700 leading-none">{displayUserName}</p>
                <p className="text-[10px] text-slate-400 font-medium uppercase mt-1">Master Admin</p>
              </div>
              <div className="w-8 h-8 bg-slate-200 rounded-full border-2 border-white shadow-sm flex items-center justify-center text-slate-600 font-bold text-xs">
                {userInitial}
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-y-auto p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
