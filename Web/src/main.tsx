import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import { ToastProvider } from './contexts/ToastContext.tsx';
import { SystemLockProvider } from './contexts/SystemLockContext.tsx';
import { initPosthog } from './lib/posthog.ts';
import './index.css';

// Initialize PostHog Web SDK with Autocapture & Session Replay
initPosthog();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <SystemLockProvider>
        <App />
      </SystemLockProvider>
    </ToastProvider>
  </StrictMode>,
);
