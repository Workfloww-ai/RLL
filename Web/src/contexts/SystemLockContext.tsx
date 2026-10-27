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
  lockType: 'sales_upload' | 'roster_upload' | 'cooldown' | null;
  lockReason: string | null;
  activeBatch: ActiveBatchInfo | null;
  isCooldownActive: boolean;
  cooldownRemainingSeconds: number;
  cooldownTotalSeconds: number;
  formattedCooldown: string;
  formattedCooldownLong: string;
  cooldownMessage: string;
}

export interface SystemLockContextType extends SystemLockState {
  refreshLockStatus: () => Promise<SystemLockState>;
  startCooldownManually: (seconds?: number, message?: string) => void;
}

const defaultState: SystemLockState = {
  isLocked: false,
  lockType: null,
  lockReason: null,
  activeBatch: null,
  isCooldownActive: false,
  cooldownRemainingSeconds: 0,
  cooldownTotalSeconds: 1800,
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

  const [cooldownTotalSeconds, setCooldownTotalSeconds] = useState<number>(() => {
    try {
      const tot = localStorage.getItem('rll_cooldown_total_seconds');
      if (tot) return parseInt(tot, 10);
    } catch (e) {}
    return 1800;
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

  const [cooldownMessage, setCooldownMessage] = useState<string>(() => {
    try {
      return localStorage.getItem('rll_cooldown_message') || '';
    } catch (e) {
      return '';
    }
  });
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
            localStorage.removeItem('rll_cooldown_total_seconds');
            localStorage.removeItem('rll_cooldown_message');
          } catch (e) {}
        }
        return next;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [cooldownRemaining > 0]);

  const startCooldownManually = useCallback((seconds: number = 1800, message?: string) => {
    const isSuccess = seconds > 600;
    const defaultMsg = isSuccess
      ? 'Upload completed successfully. 30-minute verification cooldown active.'
      : 'Validation issue detected. 10-minute rollback & purge buffer active.';
    let finalMsg = message || defaultMsg;
    if (isSuccess && (finalMsg.includes('10-minute') || finalMsg.includes('rollback'))) {
      finalMsg = defaultMsg;
    } else if (!isSuccess && finalMsg.includes('30-minute')) {
      finalMsg = defaultMsg;
    }

    setCooldownRemaining(seconds);
    setCooldownTotalSeconds(seconds);
    setCooldownMessage(finalMsg);
    try {
      localStorage.setItem('rll_cooldown_expiry_ms', String(Date.now() + seconds * 1000));
      localStorage.setItem('rll_cooldown_total_seconds', String(seconds));
      localStorage.setItem('rll_cooldown_message', finalMsg);
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
        let effectiveTotalSec = 1800;
        // Handle cooldown from backend
        const cooldownData = data.cooldown;
        if (cooldownData && cooldownData.is_active && cooldownData.remaining_seconds > 0) {
          const rem = Math.max(0, parseInt(cooldownData.remaining_seconds, 10));
          const totalSec = parseInt(cooldownData.cooldown_seconds, 10) || (rem > 600 ? 1800 : 600);
          newCooldownSec = rem;
          effectiveTotalSec = totalSec;
          setCooldownRemaining(rem);
          setCooldownTotalSeconds(totalSec);

          const isSuccess = totalSec > 600;
          let msg = cooldownData.message;
          if (!msg || (isSuccess && (msg.includes('10-minute') || msg.includes('rollback')))) {
            msg = 'Upload completed successfully. 30-minute verification cooldown active.';
          } else if (!isSuccess && msg.includes('30-minute')) {
            msg = 'Validation issue detected. 10-minute rollback & purge buffer active.';
          }

          setCooldownMessage(msg);
          try {
            localStorage.setItem('rll_cooldown_expiry_ms', String(Date.now() + rem * 1000));
            localStorage.setItem('rll_cooldown_total_seconds', String(totalSec));
            localStorage.setItem('rll_cooldown_message', msg);
          } catch (e) {}
        } else if (cooldownData && !cooldownData.is_active) {
          // Server explicitly confirms no cooldown active (or cooldown was reset)
          setCooldownRemaining(0);
          newCooldownSec = 0;
          try {
            localStorage.removeItem('rll_cooldown_expiry_ms');
            localStorage.removeItem('rll_cooldown_total_seconds');
            localStorage.removeItem('rll_cooldown_message');
          } catch (e) {}
        } else {
          // Fallback if cooldownData was not provided in response
          const expiryStr = localStorage.getItem('rll_cooldown_expiry_ms');
          if (expiryStr) {
            const rem = Math.max(0, Math.ceil((parseInt(expiryStr, 10) - Date.now()) / 1000));
            if (rem <= 0) {
              setCooldownRemaining(0);
              localStorage.removeItem('rll_cooldown_expiry_ms');
              localStorage.removeItem('rll_cooldown_total_seconds');
              localStorage.removeItem('rll_cooldown_message');
            } else {
              newCooldownSec = rem;
            }
          } else {
            setCooldownRemaining(0);
          }
        }

        // Keep localStorage upload record synchronized ONLY IF batch is actually in progress
        const batchStatus = (newBase.activeBatch?.status || '').toLowerCase();
        const isBatchLive = ['queued', 'running', 'processing', 'aggregating', 'validating', 'pending'].includes(batchStatus);

        if (newBase.isLocked && newBase.lockType === 'sales_upload' && newBase.activeBatch && isBatchLive) {
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
          // If system is unlocked or batch ended/failed/cancelled, wipe stale upload locks from browser storage
          localStorage.removeItem('rll_active_sales_upload');
        }

        const isCooldownActive = newCooldownSec > 0;
        const isSystemLocked = Boolean(newBase.isLocked || isCooldownActive);
        const effectiveLockType = newBase.isLocked ? newBase.lockType : (isCooldownActive ? 'cooldown' : null);
        const effectiveLockReason = newBase.isLocked 
          ? newBase.lockReason 
          : (isCooldownActive ? (cooldownMessageRef.current || `Upload cooldown active (${formatMMSS(newCooldownSec)} remaining). System is in Read-Only mode.`) : null);

        return {
          ...newBase,
          isLocked: isSystemLocked,
          lockType: effectiveLockType as any,
          lockReason: effectiveLockReason,
          isCooldownActive,
          cooldownRemainingSeconds: newCooldownSec,
          cooldownTotalSeconds: effectiveTotalSec,
          formattedCooldown: formatMMSS(newCooldownSec),
          formattedCooldownLong: formatLong(newCooldownSec),
          cooldownMessage: cooldownMessageRef.current,
        };
      }
    } catch (err) {
      // Ignore network errors during background polling
    }

    const isCooldownActive = cooldownRemainingRef.current > 0;
    const isSystemLocked = Boolean(lockBaseRef.current.isLocked || isCooldownActive);
    const effectiveLockType = lockBaseRef.current.isLocked ? lockBaseRef.current.lockType : (isCooldownActive ? 'cooldown' : null);
    const effectiveLockReason = lockBaseRef.current.isLocked 
      ? lockBaseRef.current.lockReason 
      : (isCooldownActive ? (cooldownMessageRef.current || `Upload cooldown active (${formatMMSS(cooldownRemainingRef.current)} remaining). System is in Read-Only mode.`) : null);

    return {
      ...lockBaseRef.current,
      isLocked: isSystemLocked,
      lockType: effectiveLockType as any,
      lockReason: effectiveLockReason,
      isCooldownActive,
      cooldownRemainingSeconds: cooldownRemainingRef.current,
      cooldownTotalSeconds: 1800,
      formattedCooldown: formatMMSS(cooldownRemainingRef.current),
      formattedCooldownLong: formatLong(cooldownRemainingRef.current),
      cooldownMessage: cooldownMessageRef.current,
    };
  }, []);

  useEffect(() => {
    // Initial fetch once on mount
    fetchLockStatus();

    const handleVisibilityChange = () => {
      if (!document.hidden) {
        fetchLockStatus();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleVisibilityChange);

    // Poll at a responsive 5-second interval when tab is active
    pollIntervalRef.current = setInterval(() => {
      if (!document.hidden) {
        fetchLockStatus();
      }
    }, 5000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleVisibilityChange);
    };
  }, [fetchLockStatus]);

  let hasLocalUpload = false;
  try {
    const localUploadRaw = localStorage.getItem('rll_active_sales_upload');
    if (localUploadRaw) {
      const parsed = JSON.parse(localUploadRaw);
      if (parsed && parsed.status === 'processing') {
        hasLocalUpload = true;
      }
    }
  } catch (e) {}

  const isCooldownActive = cooldownRemaining > 0;
  const isSystemLocked = Boolean(lockBase.isLocked || isCooldownActive || hasLocalUpload);
  const effectiveLockType = lockBase.isLocked 
    ? lockBase.lockType 
    : (hasLocalUpload ? 'sales_upload' : (isCooldownActive ? 'cooldown' : null));
  const effectiveLockReason = lockBase.isLocked 
    ? lockBase.lockReason 
    : (hasLocalUpload
        ? 'Sales data ingestion in progress. System is locked in Read-Only mode to maintain transactional integrity.'
        : (isCooldownActive ? (cooldownMessage || `Upload cooldown active (${formatMMSS(cooldownRemaining)} remaining). System is in Read-Only mode.`) : null));

  const stateValue: SystemLockState = {
    ...lockBase,
    isLocked: isSystemLocked,
    lockType: effectiveLockType as any,
    lockReason: effectiveLockReason,
    isCooldownActive,
    cooldownRemainingSeconds: cooldownRemaining,
    cooldownTotalSeconds,
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
