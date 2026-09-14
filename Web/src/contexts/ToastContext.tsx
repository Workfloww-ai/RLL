import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { X, CheckCircle, AlertTriangle, Info, AlertCircle } from 'lucide-react';

import { logErrorToBackend } from '../lib/logger';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastContextType {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = useCallback((message: string, type: ToastType = 'success') => {
    const id = Math.random().toString(36).substr(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);

    if (type === 'error') {
      logErrorToBackend({
        source: 'frontend',
        error_message: message,
        context: { context_source: 'toast' }
      });
    }

    // Auto-dismiss for success and info
    if (type === 'success' || type === 'info') {
      setTimeout(() => {
        removeToast(id);
      }, 4000);
    }
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map((toast) => (
          <ToastNotification 
            key={toast.id} 
            toast={toast} 
            onClose={() => removeToast(toast.id)} 
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastNotification({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const [isClosing, setIsClosing] = useState(false);

  const handleClose = () => {
    setIsClosing(true);
    setTimeout(() => {
      onClose();
    }, 300); // Wait for exit animation
  };

  const getToastStyles = (type: ToastType) => {
    switch (type) {
      case 'success':
        return {
          bg: 'bg-emerald-50 border-emerald-200',
          text: 'text-emerald-800',
          icon: <CheckCircle className="h-5 w-5 text-emerald-500" />,
        };
      case 'error':
        return {
          bg: 'bg-red-50 border-red-200',
          text: 'text-red-800',
          icon: <AlertCircle className="h-5 w-5 text-red-500" />,
        };
      case 'warning':
        return {
          bg: 'bg-amber-50 border-amber-200',
          text: 'text-amber-800',
          icon: <AlertTriangle className="h-5 w-5 text-amber-500" />,
        };
      case 'info':
      default:
        return {
          bg: 'bg-blue-50 border-blue-200',
          text: 'text-blue-800',
          icon: <Info className="h-5 w-5 text-blue-500" />,
        };
    }
  };

  const styles = getToastStyles(toast.type);
  const requireManualClose = toast.type === 'error' || toast.type === 'warning';

  return (
    <div
      className={`pointer-events-auto flex w-full items-start gap-3 rounded-lg border p-4 shadow-lg transition-all duration-300 ${
        isClosing ? 'translate-x-full opacity-0' : 'translate-x-0 opacity-100'
      } ${styles.bg}`}
    >
      <div className="flex-shrink-0 mt-0.5">{styles.icon}</div>
      <div className={`flex-1 text-sm font-medium ${styles.text}`}>
        {toast.message}
      </div>
      {requireManualClose && (
        <button
          onClick={handleClose}
          className={`flex-shrink-0 rounded-md p-1 transition-colors hover:bg-black/5 ${styles.text}`}
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
