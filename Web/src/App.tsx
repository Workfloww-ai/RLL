/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import DashboardLayout from './components/DashboardLayout';
import StockUpload from './pages/StockUpload';
import TerritoryManagement from './pages/TerritoryManagement';
import HeadcountManagement from './pages/HeadcountManagement';
import Login from './pages/Login';
import { ViewState } from './types';

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userName, setUserName] = useState<string | null>(null);
  const [currentView, setCurrentView] = useState<ViewState>('stock');

  if (!isAuthenticated) {
    return <Login onLogin={(name) => {
      setUserName(name);
      setIsAuthenticated(true);
    }} />;
  }

  return (
    <DashboardLayout 
      currentView={currentView} 
      onViewChange={setCurrentView}
      userName={userName}
      onLogout={() => {
        setIsAuthenticated(false);
        setUserName(null);
        localStorage.removeItem('token');
      }}
    >
      {currentView === 'stock' && <StockUpload />}
      {currentView === 'territory' && <TerritoryManagement />}
      {currentView === 'headcount' && <HeadcountManagement />}
    </DashboardLayout>
  );
}

