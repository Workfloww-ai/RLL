/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from 'react';
import DashboardLayout from './components/DashboardLayout';
import StockUpload from './pages/StockUpload';
import TerritoryManagement from './pages/TerritoryManagement';
import HeadcountManagement from './pages/HeadcountManagement';
import RoleManagement from './pages/RoleManagement';
import SystemSettings from './pages/SystemSettings';
import Login from './pages/Login';
import { ViewState } from './types';
import { API_BASE_URL } from './config';
import { logErrorToBackend } from './lib/logger';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    logErrorToBackend({
      source: 'frontend',
      error_message: error.toString(),
      stack_trace: errorInfo.componentStack || error.stack,
      context: { context_source: 'error_boundary' }
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 max-w-lg mx-auto my-12 bg-white border border-red-200 rounded-xl shadow-lg text-center font-sans">
          <div className="w-12 h-12 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto mb-4 font-bold text-xl">
            !
          </div>
          <h2 className="text-xl font-bold text-slate-800 mb-2">Something went wrong</h2>
          <p className="text-xs text-slate-500 mb-4">{this.state.error?.message || 'An unexpected error occurred.'}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="px-4 py-2 bg-[#004B87] text-white rounded text-xs font-bold hover:bg-blue-800 transition-colors"
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    return Boolean(localStorage.getItem('token'));
  });
  const [userName, setUserName] = useState<string | null>(() => {
    return localStorage.getItem('user_name');
  });
  const [currentView, setCurrentView] = useState<ViewState>(() => {
    const savedView = localStorage.getItem('current_view');
    return (savedView as ViewState) || 'stock';
  });

  useEffect(() => {
    async function verifySession() {
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      try {
        const res = await fetch(`${API_BASE_URL}/auth/me`, {
          method: 'GET',
          headers,
          credentials: 'include',
        });
        if (res.ok) {
          const data = await res.json();
          if (data && data.user) {
            const displayName = data.user.first_name 
              ? `${data.user.first_name} ${data.user.last_name || ''}`.trim()
              : (data.user.name || 'User');
            setUserName(displayName);
            setIsAuthenticated(true);
            localStorage.setItem('user_name', displayName);
          }
        } else if (res.status === 401) {
          setIsAuthenticated(false);
          setUserName(null);
          localStorage.removeItem('token');
          localStorage.removeItem('user_name');
        }
      } catch (err) {
        console.debug('Session verification notice:', err);
      }
    }
    verifySession();
  }, []);

  const handleViewChange = (view: ViewState) => {
    setCurrentView(view);
    localStorage.setItem('current_view', view);
  };

  const handleLogin = (name: string) => {
    setUserName(name);
    setIsAuthenticated(true);
    localStorage.setItem('user_name', name);
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch (e) {
      console.error('Logout error:', e);
    }
    setIsAuthenticated(false);
    setUserName(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user_name');
    localStorage.removeItem('current_view');
  };

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <ErrorBoundary>
      <DashboardLayout 
        currentView={currentView} 
        onViewChange={handleViewChange}
        userName={userName}
        onLogout={handleLogout}
      >
        {currentView === 'stock' && <StockUpload />}
        {currentView === 'territory' && <TerritoryManagement />}
        {currentView === 'headcount' && <HeadcountManagement />}
        {currentView === 'roles' && <RoleManagement />}
        {currentView === 'settings' && <SystemSettings />}
      </DashboardLayout>
    </ErrorBoundary>
  );
}

