import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode, useRef } from 'react';
import { API_BASE_URL } from '../config';

export interface ActiveBatchInfo {
  batch_id: string;
  file_name?: string;
  source_file?: string;
  status: string;
  remarks?: string;
  total_rows?: number;
  imported_rows?: number;
  created_at?: string;
}

export interface SystemLockState {
  isLocked: boolean;
  lockType: 'sales_upload' | 'roster_upload' | null;
  lockReason: string | null;
  activeBatch: ActiveBatchInfo | null;
  isCooldownActive: boolean;
  cooldownRemainingSeconds: number;
  formattedCooldown: string;
  formattedCooldownLong: string;
  cooldownMessage: string;
}

export interface SystemLockContextType extends SystemLockState {
  refreshLockStatus: () => Promise<SystemLockState>;
  startCooldownManually: (seconds?: number) => void;
}

const defaultState: SystemLockState = {
  isLocked: false,
  lockType: null,
  lockReason: null,
  activeBatch: null,
  isCooldownActive: false,
  cooldownRemainingSeconds: 0,
  formattedCooldown: '00:00',
  formattedCooldownLong: '0s',
  cooldownMessage: '',
};

const SystemLockContext = createContext<SystemLockContextType>({
  ...defaultState,
  refreshLockStatus: async () => defaultState,
  startCooldownManually: () => {},
});

export function useSystemLock() {
  return useContext(SystemLockContext);
}

function formatMMSS(sec: number): string {
  if (sec <= 0) return '00:00';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

function formatLong(sec: number): string {
  if (sec <= 0) return '0s';
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s < 10 ? '0' : ''}${s}s`;
}

export function SystemLockProvider({ children }: { children: ReactNode }) {
  const [lockBase, setLockBase] = useState<{
    isLocked: boolean;
    lockType: 'sales_upload' | 'roster_upload' | null;
    lockReason: string | null;
    activeBatch: ActiveBatchInfo | null;
  }>(() => {
    try {
      const saved = localStorage.getItem('rll_system_lock_base');
      if (saved) return JSON.parse(saved);
    } catch (e) {}
    return {
      isLocked: false,
      lockType: null,
      lockReason: null,
      activeBatch: null,
    };
  });

  const [cooldownRemaining, setCooldownRemaining] = useState<number>(() => {
    try {
      const expiry = localStorage.getItem('rll_cooldown_expiry_ms');
      if (expiry) {
        const remaining = Math.max(0, Math.ceil((parseInt(expiry, 10) - Date.now()) / 1000));
        return remaining;
      }
    } catch (e) {}
    return 0;
  });

  const [cooldownMessage, setCooldownMessage] = useState<string>('');
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Keep refs for latest values so fetchLockStatus never re-creates or triggers effect cascades
  const cooldownRemainingRef = useRef(cooldownRemaining);
  cooldownRemainingRef.current = cooldownRemaining;
  const lockBaseRef = useRef(lockBase);
  lockBaseRef.current = lockBase;
  const cooldownMessageRef = useRef(cooldownMessage);
  cooldownMessageRef.current = cooldownMessage;

  // 1-second interval ticker for smooth local countdown (purely local, no network)
  useEffect(() => {
    if (cooldownRemaining <= 0) return;

    const timer = setInterval(() => {
      setCooldownRemaining(prev => {
        const next = Math.max(0, prev - 1);
        if (next === 0) {
          try {
            localStorage.removeItem('rll_cooldown_expiry_ms');
          } catch (e) {}
        }
        return next;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [cooldownRemaining > 0]);

  const startCooldownManually = useCallback((seconds: number = 1800) => {
    setCooldownRemaining(seconds);
    try {
      localStorage.setItem('rll_cooldown_expiry_ms', String(Date.now() + seconds * 1000));
    } catch (e) {}
  }, []);

  const fetchLockStatus = useCallback(async (): Promise<SystemLockState> => {
    try {
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${API_BASE_URL}/system/lock-status`, { headers });
      if (res.ok) {
        const data = await res.json();
        const newBase = {
          isLocked: Boolean(data.is_locked),
          lockType: (data.lock_type as 'sales_upload' | 'roster_upload') || null,
          lockReason: data.lock_reason || null,
          activeBatch: data.active_batch || null,
        };

        setLockBase(newBase);
        try {
          localStorage.setItem('rll_system_lock_base', JSON.stringify(newBase));
        } catch (e) {}

        let newCooldownSec = 0;
        // Handle cooldown from backend
        const cooldownData = data.cooldown;
        if (cooldownData && cooldownData.is_active && cooldownData.remaining_seconds > 0) {
          const rem = Math.max(0, parseInt(cooldownData.remaining_seconds, 10));
          newCooldownSec = rem;
          setCooldownRemaining(rem);
          setCooldownMessage(cooldownData.message || 'Upload cooldown active.');
          try {
            localStorage.setItem('rll_cooldown_expiry_ms', String(Date.now() + rem * 1000));
          } catch (e) {}
        } else {
          // If server confirmed no cooldown active
          const expiryStr = localStorage.getItem('rll_cooldown_expiry_ms');
          if (expiryStr) {
            const rem = Math.max(0, Math.ceil((parseInt(expiryStr, 10) - Date.now()) / 1000));
            if (rem <= 0) {
              setCooldownRemaining(0);
              localStorage.removeItem('rll_cooldown_expiry_ms');
            } else {
              newCooldownSec = rem;
            }
          } else {
            setCooldownRemaining(0);
          }
        }

        // Keep localStorage upload record synchronized
        if (newBase.isLocked && newBase.lockType === 'sales_upload' && newBase.activeBatch) {
          const currentStored = localStorage.getItem('rll_active_sales_upload');
          let existingData: any = {};
          try {
            if (currentStored) existingData = JSON.parse(currentStored);
          } catch (e) {}

          const batchId = newBase.activeBatch.batch_id;
          const fileName = newBase.activeBatch.file_name;
          const startTimestampMs = existingData.startTimestampMs || (newBase.activeBatch.created_at ? new Date(newBase.activeBatch.created_at).getTime() : Date.now());
          const uploadStartTime = existingData.uploadStartTime || (newBase.activeBatch.created_at ? new Date(newBase.activeBatch.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) : 'Recently');

          localStorage.setItem('rll_active_sales_upload', JSON.stringify({
            batchId,
            fileName,
            startTimestampMs,
            uploadStartTime,
            status: newBase.activeBatch.status || 'processing',
            remarks: newBase.activeBatch.remarks,
            totalRows: newBase.activeBatch.total_rows,
            importedRows: newBase.activeBatch.imported_rows
          }));
        } else {
          // If system is unlocked or batch ended, wipe stale upload locks from browser storage
          localStorage.removeItem('rll_active_sales_upload');
          localStorage.removeItem('rll_system_lock_base');
        }

        const isCooldownActive = newCooldownSec > 0;
        return {
          ...newBase,
          isCooldownActive,
          cooldownRemainingSeconds: newCooldownSec,
          formattedCooldown: formatMMSS(newCooldownSec),
          formattedCooldownLong: formatLong(newCooldownSec),
          cooldownMessage: cooldownMessageRef.current,
        };
      }
    } catch (err) {
      // Ignore network errors during background polling
    }

    const isCooldownActive = cooldownRemainingRef.current > 0;
    return {
      ...lockBaseRef.current,
      isCooldownActive,
      cooldownRemainingSeconds: cooldownRemainingRef.current,
      formattedCooldown: formatMMSS(cooldownRemainingRef.current),
      formattedCooldownLong: formatLong(cooldownRemainingRef.current),
      cooldownMessage: cooldownMessageRef.current,
    };
  }, []);

  useEffect(() => {
    // Initial fetch once on mount
    fetchLockStatus();

    // Poll at a healthy 10-second interval
    pollIntervalRef.current = setInterval(() => {
      fetchLockStatus();
    }, 10000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [fetchLockStatus]);

  const isCooldownActive = cooldownRemaining > 0;
  const stateValue: SystemLockState = {
    ...lockBase,
    isCooldownActive,
    cooldownRemainingSeconds: cooldownRemaining,
    formattedCooldown: formatMMSS(cooldownRemaining),
    formattedCooldownLong: formatLong(cooldownRemaining),
    cooldownMessage,
  };

  return (
    <SystemLockContext.Provider value={{ ...stateValue, refreshLockStatus: fetchLockStatus, startCooldownManually }}>
      {children}
    </SystemLockContext.Provider>
  );
}
