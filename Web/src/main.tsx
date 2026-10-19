import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import { ToastProvider } from './contexts/ToastContext.tsx';
import { SystemLockProvider } from './contexts/SystemLockContext.tsx';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <SystemLockProvider>
        <App />
      </SystemLockProvider>
    </ToastProvider>
  </StrictMode>,
);
