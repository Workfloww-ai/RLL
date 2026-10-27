import React, { useState, useRef, useEffect } from 'react';
import { UploadCloud, FileText, CheckCircle2, AlertCircle, Database, RefreshCw, Server, X, Check, Clock, Lock } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { FileUploadState } from '../types';
import { API_BASE_URL } from '../config';
import { useSystemLock } from '../contexts/SystemLockContext';
import { useToast } from '../contexts/ToastContext';

interface FileUploadProps {
  title: string;
  instructions: string[];
  accept?: string;
  uploadEndpoint?: string;
  onUploadStart?: (fileName: string) => void;
  onUploadComplete?: (fileName: string) => void;
  onErrorOccurred?: (batchId?: string | number) => void;
}

function formatLaymanShortError(msg: string): string {
  if (!msg) return 'Validation error';
  const rowMatch = msg.match(/\[Row\s*#?(\d+)\]/i);
  const rowNum = rowMatch ? `Row #${rowMatch[1]}` : '';

  const valMatch = msg.match(/'(.*?)'/);
  const val = valMatch ? valMatch[1] : '';

  if (msg.includes('UNMAPPED_ASE')) {
    return `${rowNum ? rowNum + ': ' : ''}Unregistered ASE Personnel — '${val || 'Unknown'}'`;
  }
  if (msg.includes('UNMAPPED_TSM')) {
    return `${rowNum ? rowNum + ': ' : ''}Unregistered ASM/TSM Personnel — '${val || 'Unknown'}'`;
  }
  if (msg.includes('UNMAPPED_LICENSEE')) {
    return `${rowNum ? rowNum + ': ' : ''}Unmapped Licensee — '${val || 'Unknown'}'`;
  }
  if (msg.includes('UNMAPPED_DEPOT')) {
    return `${rowNum ? rowNum + ': ' : ''}Unmapped Depot — '${val || 'Unknown'}'`;
  }
  if (msg.includes('UNMAPPED_BRAND')) {
    return `${rowNum ? rowNum + ': ' : ''}Unmapped Brand — '${val || 'Unknown'}'`;
  }
  if (msg.includes('UNMAPPED_COMPANY')) {
    return `${rowNum ? rowNum + ': ' : ''}Unmapped Company — '${val || 'Unknown'}'`;
  }
  if (msg.includes('UNMAPPED_HQ')) {
    return `${rowNum ? rowNum + ': ' : ''}Unmapped Headquarters — '${val || 'Unknown'}'`;
  }
  if (msg.includes('MISSING_ASE_TSM_MAPPING')) {
    return `${rowNum ? rowNum + ': ' : ''}Missing Approved Manager for ASE — '${val || 'Unknown'}'`;
  }
  if (msg.includes('ASE_TSM_MAPPING_MISMATCH')) {
    return `${rowNum ? rowNum + ': ' : ''}Reporting Line Mismatch for ASE — '${val || 'Unknown'}'`;
  }
  if (msg.includes('INVALID_CASE')) {
    return `${rowNum ? rowNum + ': ' : ''}Invalid Case Quantity`;
  }
  if (msg.includes('DATE_ERROR')) {
    return `${rowNum ? rowNum + ': ' : ''}Invalid Date Format — '${val || 'Unparseable Date'}'`;
  }

  let cleanMsg = msg.replace(/^Upload validation failed for \d+ issue\(s\):\s*/i, '').trim() || msg;
  cleanMsg = cleanMsg.replace(/\[Row\s*#?\d+\]\s*/i, '');
  return rowNum ? `${rowNum}: ${cleanMsg}` : cleanMsg;
}

export function formatFriendlyStatusMessage(msg: string): string {
  if (!msg) return 'Processing data...';
  let clean = msg;
  clean = clean.replace(/into table\s*['"][a-z0-9_]+['"]/gi, '');
  clean = clean.replace(/table\s*['"][a-z0-9_]+['"]/gi, '');
  clean = clean.replace(/raw_sales_upload/gi, 'sales data');
  clean = clean.replace(/sales_fact/gi, 'sales records');
  clean = clean.replace(/user_sales_fact/gi, 'user metrics');
  clean = clean.replace(/dashboard_summary_daily/gi, 'analytics');
  clean = clean.replace(/Completed bulk insert of/gi, 'Saved');
  clean = clean.replace(/Bulk inserting/gi, 'Saving');
  clean = clean.replace(/Ingesting\s+[a-z0-9_]+:/gi, 'Saving records:');
  clean = clean.replace(/\s{2,}/g, ' ').trim();
  return clean;
}

export default function FileUpload({ title, instructions, accept = ".xlsx, .xls, .xlsb, .csv, .numbers", uploadEndpoint, onUploadStart, onUploadComplete, onErrorOccurred }: FileUploadProps) {
  const { 
    isLocked, 
    lockType, 
    lockReason, 
    activeBatch,
    isCooldownActive,
    cooldownRemainingSeconds,
    cooldownTotalSeconds,
    cooldownMessage,
    formattedCooldown,
    formattedCooldownLong,
    startCooldownManually,
    refreshLockStatus
  } = useSystemLock();
  const { showToast } = useToast();
  const [isCancelling, setIsCancelling] = useState(false);
  const [showRollbackConfirm, setShowRollbackConfirm] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const [uploadState, setUploadState] = useState<FileUploadState>(() => {
    if (!uploadEndpoint) {
      try {
        const raw = localStorage.getItem('rll_active_sales_upload');
        if (raw) {
          const stored = JSON.parse(raw);
          const st = (stored?.status || '').toLowerCase();
          if (stored && stored.batchId && (st === 'processing' || st === 'queued' || st === 'running' || !st)) {
            const startMs = stored.startTimestampMs || Date.now();
            const elapsed = Math.max(1, Math.floor((Date.now() - startMs) / 1000));
            return {
              status: 'processing',
              progress: stored.progress || 45,
              fileName: stored.fileName || 'Sales Data Sheet',
              batchId: stored.batchId,
              uploadStartTime: stored.uploadStartTime || 'Recently',
              elapsedSeconds: elapsed,
              statusMessage: stored.remarks || 'Saving data rows into database...'
            };
          }
        }

        const lockRaw = localStorage.getItem('rll_system_lock_base');
        if (lockRaw) {
          const lockObj = JSON.parse(lockRaw);
          if (lockObj && lockObj.isLocked && lockObj.lockType === 'sales_upload' && lockObj.activeBatch) {
            const b = lockObj.activeBatch;
            return {
              status: 'processing',
              progress: 45,
              fileName: b.file_name || 'Sales Data Sheet',
              batchId: b.batch_id,
              uploadStartTime: 'Recently',
              elapsedSeconds: 5,
              statusMessage: b.remarks || 'Saving data rows into database...'
            };
          }
        }
      } catch (e) {}
    }
    return { status: 'idle', progress: 0 };
  });

  useEffect(() => {
    if ((uploadState.status === 'uploading' || uploadState.status === 'processing') && uploadState.fileName && onUploadStart) {
      onUploadStart(uploadState.fileName);
    }
  }, []);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const startPollingBatchStatus = (
    batchId: number | string, 
    fileName: string, 
    startTimeFormatted: string, 
    startTimestampMs: number
  ) => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
    }

    if (!uploadEndpoint) {
      localStorage.setItem('rll_active_sales_upload', JSON.stringify({
        batchId: String(batchId),
        fileName,
        uploadStartTime: startTimeFormatted,
        startTimestampMs,
        status: 'processing'
      }));
    }

    let pollAttempts = 0;
    const maxPollAttempts = 9000; // Allow up to 150 minutes polling for massive monthly files (500k+ rows)

    pollTimerRef.current = setInterval(async () => {
      pollAttempts += 1;
      const elapsed = Math.max(1, Math.floor((Date.now() - startTimestampMs) / 1000));

      try {
        const token = localStorage.getItem('token');
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch(`${API_BASE_URL}/uploads/batches/${batchId}`, { headers });
        if (!res.ok) {
          if (res.status === 404 || res.status === 400) {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            localStorage.removeItem('rll_active_sales_upload');
            localStorage.removeItem('rll_system_lock_base');
            setUploadState({ status: 'idle', progress: 0 });
            return;
          }
          if (pollAttempts >= maxPollAttempts) {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            localStorage.removeItem('rll_active_sales_upload');
            localStorage.removeItem('rll_system_lock_base');
            setUploadState({
              status: 'error',
              progress: 0,
              fileName,
              batchId,
              uploadStartTime: startTimeFormatted,
              elapsedSeconds: elapsed,
              errorMessage: 'Timed out waiting for database confirmation from backend.'
            });
          }
          return;
        }

        const batchInfo = await res.json();
        const statusMain = (batchInfo.status || '').toLowerCase();
        const statusUpload = (batchInfo.upload_status || '').toLowerCase();

        const isSuccess = ['loaded', 'completed', 'success'].includes(statusMain) || ['loaded', 'completed', 'success'].includes(statusUpload);
        const isFailed = statusMain === 'failed' || statusUpload === 'failed';
        const isCancelled = statusMain === 'cancelled' || statusUpload === 'cancelled';
        const isNotFound = statusMain === 'not_found' || statusUpload === 'not_found';

        if (isNotFound || isCancelled) {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          if (!uploadEndpoint) localStorage.removeItem('rll_active_sales_upload');
          setUploadState({ status: 'idle', progress: 0 });
          return;
        }

        const imported = batchInfo.imported_rows ?? batchInfo.row_count ?? 0;
        const total = batchInfo.row_count ?? 0;

        // Calculate progress percentage
        let currentProgress = 40;
        if (total > 0 && imported > 0) {
          currentProgress = Math.min(95, 40 + Math.floor((imported / total) * 55));
        } else {
          currentProgress = Math.min(92, 40 + Math.floor(pollAttempts * 1.5));
        }

        if (isSuccess) {
          // Backend has confirmed all data is completely saved in database!
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          if (!uploadEndpoint) localStorage.removeItem('rll_active_sales_upload');
          startCooldownManually(1800, 'Upload completed successfully. 30-minute verification cooldown active.');
          const finalTimeSec = batchInfo.processing_time_seconds && batchInfo.processing_time_seconds > 0 
            ? batchInfo.processing_time_seconds 
            : elapsed;

          setUploadState({
            status: 'success',
            progress: 100,
            fileName,
            batchId,
            importedRows: imported,
            failedRows: batchInfo.failed_rows ?? 0,
            duplicateRows: batchInfo.duplicate_rows ?? 0,
            processingTimeSeconds: finalTimeSec,
            uploadStartTime: startTimeFormatted,
            elapsedSeconds: elapsed,
            statusMessage: batchInfo.remarks || 'All Records Successfully Verified & Saved!'
          });
          if (onUploadComplete) onUploadComplete(fileName);
        } else if (isFailed) {
          // Background ingestion encountered errors
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          if (!uploadEndpoint) localStorage.removeItem('rll_active_sales_upload');
          startCooldownManually(600, 'Validation issue detected. 10-minute rollback & purge buffer active.');

          // Fetch error logs for detail if available
          let logs: string[] = [];
          try {
            const logsRes = await fetch(`${API_BASE_URL}/uploads/batches/${batchId}/logs`, { headers });
            if (logsRes.ok) {
              const logsData = await logsRes.json();
              if (Array.isArray(logsData)) {
                logs = logsData.map((l: any) => l.error_message || l.column_name || 'Validation error');
              }
            }
          } catch (logErr) {
            console.error('Error fetching logs:', logErr);
          }

          setUploadState({
            status: 'error',
            progress: 0,
            fileName,
            batchId,
            uploadStartTime: startTimeFormatted,
            elapsedSeconds: elapsed,
            errorMessage: batchInfo.remarks || 'Database insertion failed due to data validation errors.',
            errorLogs: logs
          });
          if (onErrorOccurred) onErrorOccurred(batchId);
        } else {
          // Still processing/pending in database
          if (!uploadEndpoint) {
            localStorage.setItem('rll_active_sales_upload', JSON.stringify({
              batchId: String(batchId),
              fileName,
              uploadStartTime: startTimeFormatted,
              startTimestampMs,
              status: 'processing',
              elapsedSeconds: elapsed
            }));
          }

          setUploadState({
            status: 'processing',
            progress: currentProgress,
            fileName,
            batchId,
            uploadStartTime: startTimeFormatted,
            elapsedSeconds: elapsed,
            statusMessage: batchInfo.remarks || 'Saving data rows into database...'
          });

          if (pollAttempts >= maxPollAttempts) {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            if (!uploadEndpoint) localStorage.removeItem('rll_active_sales_upload');
            setUploadState({
              status: 'error',
              progress: 0,
              fileName,
              batchId,
              uploadStartTime: startTimeFormatted,
              elapsedSeconds: elapsed,
              errorMessage: 'Database ingestion exceeded timeout limit. Click "Check Live DB Status" below to verify if completed.'
            });
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
        if (pollAttempts >= maxPollAttempts) {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          if (!uploadEndpoint) localStorage.removeItem('rll_active_sales_upload');
          setUploadState({
            status: 'error',
            progress: 0,
            fileName,
            batchId,
            uploadStartTime: startTimeFormatted,
            elapsedSeconds: elapsed,
            errorMessage: 'Network error while checking database status.'
          });
        }
      }
    }, 1000);
  };

  // 1. Immediately resume polling if component mounted into 'processing' state
  useEffect(() => {
    if (uploadEndpoint) return;
    if (uploadState.status === 'processing' && uploadState.batchId && !pollTimerRef.current) {
      let stored: any = null;
      try {
        const raw = localStorage.getItem('rll_active_sales_upload');
        if (raw) stored = JSON.parse(raw);
      } catch (e) {}
      const startMs = stored?.startTimestampMs || (Date.now() - (uploadState.elapsedSeconds || 0) * 1000);
      startPollingBatchStatus(
        uploadState.batchId,
        uploadState.fileName || 'Sales Data Sheet',
        uploadState.uploadStartTime || 'Recently',
        startMs
      );
    }
  }, []);

  // 2. Reactively switch to processing if activeBatch arrives from SystemLockContext
  useEffect(() => {
    if (uploadEndpoint) return;
    if (activeBatch && lockType === 'sales_upload') {
      const bStatus = (activeBatch.status || '').toLowerCase();
      const isLive = ['queued', 'running', 'processing', 'aggregating', 'validating', 'pending'].includes(bStatus);
      if (!isLive) return;

      if (uploadState.status !== 'processing') {
        const bId = activeBatch.batch_id;
        const fName = activeBatch.file_name || 'Sales Data Sheet';
        let stored: any = null;
        try {
          const raw = localStorage.getItem('rll_active_sales_upload');
          if (raw) stored = JSON.parse(raw);
        } catch (e) {}

        const startMs = stored?.startTimestampMs || (activeBatch.created_at ? new Date(activeBatch.created_at).getTime() : Date.now());
        const timeFormatted = stored?.uploadStartTime || (activeBatch.created_at ? new Date(activeBatch.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) : 'Recently');
        const elapsed = Math.max(1, Math.floor((Date.now() - startMs) / 1000));

        setUploadState({
          status: 'processing',
          progress: 45,
          fileName: fName,
          batchId: bId,
          uploadStartTime: timeFormatted,
          elapsedSeconds: elapsed,
          statusMessage: activeBatch.remarks || 'Saving data rows into database...'
        });

        startPollingBatchStatus(bId, fName, timeFormatted, startMs);
      }
    }
  }, [activeBatch, lockType, uploadEndpoint]);

  // 3. Full mount verification with backend endpoints
  useEffect(() => {
    let isMounted = true;

    async function checkActiveUploadOnMount() {
      if (uploadEndpoint) return; // Dedicated to sales upload recovery

      try {
        let stored: any = null;
        try {
          const raw = localStorage.getItem('rll_active_sales_upload');
          if (raw) stored = JSON.parse(raw);
        } catch (e) {}

        let activeBatchData = activeBatch;
        if (!activeBatchData) {
          const token = localStorage.getItem('token');
          const headers: Record<string, string> = {};
          if (token) headers['Authorization'] = `Bearer ${token}`;
          const res = await fetch(`${API_BASE_URL}/uploads/active-batch`, { headers });
          if (res.ok) {
            const data = await res.json();
            if (data && data.active && data.batch) {
              activeBatchData = data.batch;
            }
          }
        }

        if (activeBatchData && isMounted) {
          const bId = activeBatchData.batch_id;
          const fName = activeBatchData.source_file || activeBatchData.file_name || stored?.fileName || 'Sales Data Sheet';
          const startMs = stored?.startTimestampMs || (activeBatchData.created_at ? new Date(activeBatchData.created_at).getTime() : Date.now());
          const timeFormatted = stored?.uploadStartTime || (activeBatchData.created_at ? new Date(activeBatchData.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) : 'Recently');
          const elapsed = Math.max(1, Math.floor((Date.now() - startMs) / 1000));

          setUploadState({
            status: 'processing',
            progress: 45,
            fileName: fName,
            batchId: bId,
            uploadStartTime: timeFormatted,
            elapsedSeconds: elapsed,
            statusMessage: activeBatchData.remarks || 'Saving data rows into database...'
          });

          startPollingBatchStatus(bId, fName, timeFormatted, startMs);
          return;
        }

        if (stored && stored.batchId && isMounted) {
          const token = localStorage.getItem('token');
          const headers: Record<string, string> = {};
          if (token) headers['Authorization'] = `Bearer ${token}`;

          const res = await fetch(`${API_BASE_URL}/uploads/batches/${stored.batchId}`, { headers });
          if (!res.ok) {
            if (res.status === 404 || res.status === 400) {
              localStorage.removeItem('rll_active_sales_upload');
              localStorage.removeItem('rll_system_lock_base');
              setUploadState({ status: 'idle', progress: 0 });
            }
            return;
          }

          const batchInfo = await res.json();
          const statusMain = (batchInfo.status || '').toLowerCase();
          const statusUpload = (batchInfo.upload_status || '').toLowerCase();
          const isSuccess = ['loaded', 'completed', 'success'].includes(statusMain) || ['loaded', 'completed', 'success'].includes(statusUpload);
          const isFailed = statusMain === 'failed' || statusUpload === 'failed';
          const elapsed = Math.max(1, Math.floor((Date.now() - (stored.startTimestampMs || Date.now())) / 1000));

          if (isSuccess) {
            const imported = batchInfo.imported_rows ?? batchInfo.row_count ?? 0;
            setUploadState({
              status: 'success',
              progress: 100,
              fileName: stored.fileName || batchInfo.file_name || batchInfo.source_file,
              batchId: stored.batchId,
              importedRows: imported,
              failedRows: batchInfo.failed_rows ?? 0,
              duplicateRows: batchInfo.duplicate_rows ?? 0,
              processingTimeSeconds: batchInfo.processing_time_seconds || elapsed,
              uploadStartTime: stored.uploadStartTime,
              elapsedSeconds: elapsed,
              statusMessage: batchInfo.remarks || 'All Records Successfully Verified & Saved!'
            });
            localStorage.removeItem('rll_active_sales_upload');
            startCooldownManually(1800, 'Upload completed successfully. 30-minute verification cooldown active.');
            if (onUploadComplete) onUploadComplete(stored.fileName);
            return;
          } else if (isFailed) {
            startCooldownManually(600, 'Validation issue detected. 10-minute rollback & purge buffer active.');
            setUploadState({
              status: 'error',
              progress: 0,
              fileName: stored.fileName,
              batchId: stored.batchId,
              uploadStartTime: stored.uploadStartTime,
              elapsedSeconds: elapsed,
              errorMessage: batchInfo.remarks || 'Database insertion failed due to data validation errors.'
            });
            localStorage.removeItem('rll_active_sales_upload');
            if (onErrorOccurred) onErrorOccurred(stored.batchId);
            return;
          } else if (statusMain === 'cancelled' || statusUpload === 'cancelled' || statusMain === 'not_found' || statusUpload === 'not_found') {
            localStorage.removeItem('rll_active_sales_upload');
            localStorage.removeItem('rll_system_lock_base');
            setUploadState({ status: 'idle', progress: 0 });
            return;
          } else {
            // Batch is actively processing in background - maintain state and resume polling
            const imported = batchInfo.imported_rows ?? batchInfo.row_count ?? 0;
            const total = batchInfo.row_count ?? 0;
            let currProg = 45;
            if (total > 0 && imported > 0) {
              currProg = Math.min(95, 40 + Math.floor((imported / total) * 55));
            }
            const timeFormatted = stored.uploadStartTime || (batchInfo.created_at ? new Date(batchInfo.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) : 'Recently');
            const fName = stored.fileName || batchInfo.file_name || batchInfo.source_file || 'Sales Data Sheet';
            const startMs = stored.startTimestampMs || (batchInfo.created_at ? new Date(batchInfo.created_at).getTime() : (Date.now() - elapsed * 1000));

            setUploadState({
              status: 'processing',
              progress: currProg,
              fileName: fName,
              batchId: stored.batchId,
              uploadStartTime: timeFormatted,
              elapsedSeconds: elapsed,
              statusMessage: batchInfo.remarks || 'Saving data rows into database...'
            });
            startPollingBatchStatus(stored.batchId, fName, timeFormatted, startMs);
            return;
          }
        }
        // If no active upload in localStorage, check /uploads/latest to see if a recent upload succeeded
        if (!uploadEndpoint && isMounted) {
          const token = localStorage.getItem('token');
          const headers: Record<string, string> = {};
          if (token) headers['Authorization'] = `Bearer ${token}`;
          try {
            const resLatest = await fetch(`${API_BASE_URL}/uploads/latest`, { headers });
            if (resLatest.ok) {
              const latestData = await resLatest.json();
              const stMain = (latestData?.status || '').toLowerCase();
              const isSucc = ['loaded', 'completed', 'success'].includes(stMain);
              if (isSucc && latestData.created_at) {
                const diffMs = Date.now() - new Date(latestData.created_at).getTime();
                // If created or finished within the last 60 minutes, display success state
                if (diffMs < 60 * 60 * 1000) {
                  const imported = latestData.imported_rows ?? latestData.row_count ?? 0;
                  setUploadState({
                    status: 'success',
                    progress: 100,
                    fileName: latestData.source_file || latestData.file_name || 'IMFL Data May-26.xlsb',
                    batchId: latestData.batch_id,
                    importedRows: imported,
                    failedRows: latestData.failed_rows ?? 0,
                    duplicateRows: latestData.duplicate_rows ?? 0,
                    processingTimeSeconds: latestData.processing_time_seconds,
                    uploadStartTime: new Date(latestData.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }),
                    statusMessage: latestData.remarks || 'All Records Successfully Verified & Saved!'
                  });
                  return;
                }
              }
            }
          } catch (eLatest) {
            console.warn('Notice checking latest upload batch on mount:', eLatest);
          }
        }
      } catch (err) {
        console.warn('Active batch mount restoration notice:', err);
      }
    }

    checkActiveUploadOnMount();

    return () => {
      isMounted = false;
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [uploadEndpoint]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0 && uploadState.status !== 'uploading' && uploadState.status !== 'processing' && !isLocked && !isCooldownActive) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const formatDuration = (sec?: number) => {
    if (sec === undefined || sec === null || sec < 1) return '< 1s';
    if (sec < 60) return `${sec}s`;
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}m ${s.toString().padStart(2, '0')}s`;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0 && !isLocked && !isCooldownActive) {
      const selectedFile = e.target.files[0];
      e.target.value = '';
      processFile(selectedFile);
    }
  };

  const checkBatchStatusDirectly = async () => {
    const id = uploadState.batchId;
    if (!id) return;
    try {
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${API_BASE_URL}/uploads/batches/${id}`, { headers });
      if (!res.ok) return;
      const batchInfo = await res.json();
      const statusMain = (batchInfo.status || '').toLowerCase();
      const statusUpload = (batchInfo.upload_status || '').toLowerCase();
      const isSuccess = ['loaded', 'completed', 'success'].includes(statusMain) || ['loaded', 'completed', 'success'].includes(statusUpload);

      if (isSuccess) {
        startCooldownManually(1800, 'Upload completed successfully. 30-minute verification cooldown active.');
        const imported = batchInfo.imported_rows ?? batchInfo.row_count ?? 0;
        setUploadState({
          status: 'success',
          progress: 100,
          fileName: uploadState.fileName || batchInfo.file_name || batchInfo.source_file,
          batchId: id,
          importedRows: imported,
          failedRows: batchInfo.failed_rows ?? 0,
          duplicateRows: batchInfo.duplicate_rows ?? 0,
          processingTimeSeconds: batchInfo.processing_time_seconds || uploadState.elapsedSeconds || 0,
          uploadStartTime: uploadState.uploadStartTime,
          elapsedSeconds: uploadState.elapsedSeconds,
          statusMessage: batchInfo.remarks || 'All Records Successfully Verified & Saved!'
        });
        if (onUploadComplete) onUploadComplete(uploadState.fileName || batchInfo.file_name);
      } else {
        const startTs = Date.now() - (uploadState.elapsedSeconds || 0) * 1000;
        startPollingBatchStatus(id, uploadState.fileName || 'Uploaded Sheet', uploadState.uploadStartTime || 'Just now', startTs);
      }
    } catch (e) {
      console.error('Manual status check error:', e);
    }
  };

  const processFile = async (file: File) => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    const startMs = Date.now();
    const timeFormatted = new Date().toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });

    if (onUploadStart) {
      onUploadStart(file.name);
    }

    setUploadState({
      status: 'uploading',
      progress: 15,
      fileName: file.name,
      uploadStartTime: timeFormatted,
      elapsedSeconds: 0,
      statusMessage: 'Uploading file to backend server...'
    });

    try {
      const token = localStorage.getItem('token');
      const formData = new FormData();
      formData.append('file', file);

      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const targetUrl = uploadEndpoint || `${API_BASE_URL}/uploads/`;

      const response = await fetch(targetUrl, {
        method: 'POST',
        headers,
        body: formData,
        signal: abortCtrl.signal
      });

      if (!response.ok) {
        const errorText = await response.text();
        let detail = 'Upload failed';
        try {
          const parsed = JSON.parse(errorText);
          detail = parsed.detail || detail;
        } catch {
          detail = errorText || detail;
        }
        throw new Error(detail);
      }

      const data = await response.json();

      if (uploadEndpoint) {
        startCooldownManually(1800, 'Upload completed successfully. 30-minute verification cooldown active.');
        setUploadState({
          status: 'success',
          progress: 100,
          fileName: file.name,
          uploadStartTime: timeFormatted,
          elapsedSeconds: Math.floor((Date.now() - startMs) / 1000),
          importedRows: data.imported_count || 0,
          statusMessage: data.message || 'Excel roster data successfully imported and mapped across database tables.'
        });
        if (onUploadComplete) onUploadComplete(file.name);
        return;
      }

      const batchId = data.batch_id ?? data.upload_batch_id ?? data.id;

      if (!batchId) {
        setUploadState({
          status: 'success',
          progress: 100,
          fileName: file.name,
          uploadStartTime: timeFormatted,
          elapsedSeconds: Math.floor((Date.now() - startMs) / 1000),
          statusMessage: data.remarks || data.message || 'File upload completed.'
        });
        if (onUploadComplete) onUploadComplete(file.name);
        return;
      }

      // Transition to processing state & start polling backend until DB insertion confirmed
      setUploadState({
        status: 'processing',
        progress: 35,
        fileName: file.name,
        batchId,
        uploadStartTime: timeFormatted,
        elapsedSeconds: Math.floor((Date.now() - startMs) / 1000),
        statusMessage: data.remarks || 'File received. Backend is parsing data and writing into database...'
      });

      startPollingBatchStatus(batchId, file.name, timeFormatted, startMs);

    } catch (error: any) {
      if (error?.name === 'AbortError') {
        console.log('Upload aborted by user');
        return;
      }
      console.error('Upload error:', error);
      if (!uploadEndpoint) localStorage.removeItem('rll_active_sales_upload');
      setUploadState({
        status: 'error',
        progress: 0,
        fileName: file.name,
        uploadStartTime: timeFormatted,
        elapsedSeconds: Math.floor((Date.now() - startMs) / 1000),
        errorMessage: error.message || 'File upload failed. Please verify backend connection and try again.'
      });
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const resetUpload = () => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    localStorage.removeItem('rll_active_sales_upload');
    localStorage.removeItem('rll_system_lock_base');
    setUploadState({ status: 'idle', progress: 0 });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleCancelUpload = async () => {
    if (isCancelling) return;
    setIsCancelling(true);

    // 1. Abort in-flight network upload if active
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    // 2. Clear status poller immediately
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    const currentBatchId = uploadState.batchId || (() => {
      try {
        const raw = localStorage.getItem('rll_active_sales_upload');
        return raw ? JSON.parse(raw).batchId : null;
      } catch { return null; }
    })() || (activeBatch as any)?.batch_id;

    try {
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
      };

      const cancelUrl = currentBatchId
        ? `${API_BASE_URL}/uploads/batches/${currentBatchId}/cancel`
        : `${API_BASE_URL}/uploads/cancel-active`;

      const res = await fetch(cancelUrl, {
        method: 'POST',
        headers
      });

      if (!res.ok && currentBatchId && res.status !== 401 && res.status !== 403) {
        // Fallback to cancel-active
        await fetch(`${API_BASE_URL}/uploads/cancel-active`, {
          method: 'POST',
          headers
        }).catch(() => {});
      }

      showToast("Upload cancelled. In-flight execution stopped and partial records rolled back to 0.", "info");
    } catch (err) {
      console.error("Error cancelling upload:", err);
      showToast("Upload cancellation requested. Resetting dropzone.", "warning");
    } finally {
      setIsCancelling(false);
      resetUpload();
      startCooldownManually(600, 'Upload cancelled and rolled back. 10-minute cleanup buffer active.');
      try {
        if (refreshLockStatus) await refreshLockStatus();
      } catch (e) {}
      if (onErrorOccurred && currentBatchId) {
        onErrorOccurred(currentBatchId);
      }
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
      {/* Upload Dropzone Container */}
      <div className={`lg:col-span-2 rounded-2xl border shadow-2xs p-7 flex flex-col min-h-[360px] transition-all duration-200 ${
        uploadState.status === 'error' ? 'bg-rose-50/20 border-rose-200/90' : 'bg-white border-slate-200/80'
      }`}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-slate-900 tracking-tight">{title}</h2>
          {uploadState.status === 'success' && (
            <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-700 text-[10px] font-bold rounded-full border border-emerald-200">
              <Check size={12} /> Saved in DB
            </span>
          )}
          {uploadState.status === 'error' && (
            <span className="flex items-center gap-1.5 px-3 py-1 bg-rose-50 text-rose-700 text-[10px] font-bold rounded-full border border-rose-200">
              <AlertCircle size={12} /> Errors Found in Excel
            </span>
          )}
        </div>

        <div 
          className={`border-2 border-dashed rounded-xl flex-1 flex flex-col items-center justify-center p-8 transition-all duration-200 ${
            uploadState.status === 'idle' ? (
              isLocked ? 'border-amber-200 bg-amber-50/20 cursor-not-allowed opacity-90' :
              isCooldownActive ? 'border-amber-300 bg-amber-50/25 cursor-not-allowed' :
              'border-slate-200 bg-slate-50/50 hover:bg-blue-50/20 hover:border-[#0D3B8E] cursor-pointer group'
            ) : 
            uploadState.status === 'processing' ? 'border-amber-300 bg-amber-50/30' :
            uploadState.status === 'success' ? 'border-emerald-300 bg-emerald-50/30' :
            'border-rose-300 bg-rose-50/30'
          }`}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={() => uploadState.status === 'idle' && !isLocked && !isCooldownActive && fileInputRef.current?.click()}
        >
          <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            accept={accept}
            onChange={handleFileChange}
            disabled={isLocked || isCooldownActive}
          />

          <AnimatePresence mode="wait">
            {uploadState.status === 'idle' && (
              <motion.div 
                key="idle"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96 }}
                className="flex flex-col items-center text-center w-full"
              >
                {isCooldownActive || lockType === 'cooldown' ? (() => {
                  const totalCd = cooldownTotalSeconds || (cooldownRemainingSeconds > 600 ? 1800 : 600);
                  const isCleanupCd = totalCd <= 600;

                  return (
                    <div className="flex flex-col items-center text-center max-w-md mx-auto py-2">
                      <div className="relative mb-3">
                        <div className="w-16 h-16 bg-amber-500/10 border-2 border-amber-300 text-amber-600 rounded-full flex items-center justify-center shadow-inner">
                          <Clock className="w-8 h-8 animate-pulse text-amber-600" />
                        </div>
                        <div className="absolute -bottom-1 -right-1 bg-amber-600 text-white rounded-full p-1 shadow-xs">
                          <Lock size={12} />
                        </div>
                      </div>

                      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-100 text-amber-900 text-xs font-bold rounded-full border border-amber-300 mb-2">
                        <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                        {isCleanupCd ? '10-Minute Cooldown Active • Rollback & Purge Buffer' : '30-Minute Cooldown Active • Read-Only Mode'}
                      </span>

                      <h3 className="text-base font-extrabold text-slate-900 tracking-tight">
                        Upload will be enabled in {formattedCooldownLong || formattedCooldown}
                      </h3>

                      {/* Digital Onscreen Countdown Clock */}
                      <div className="my-3 px-6 py-2.5 bg-slate-900 text-amber-400 rounded-2xl shadow-md border border-slate-800 flex items-center gap-3">
                        <Clock size={20} className="text-amber-400/80 animate-spin" style={{ animationDuration: '6s' }} />
                        <span className="text-3xl font-black font-mono tracking-widest text-amber-400 drop-shadow-xs">
                          {formattedCooldown}
                        </span>
                        <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider border-l border-slate-700 pl-3 text-left">
                          Time<br />Remaining
                        </span>
                      </div>

                      {/* Progress bar towards completion */}
                      <div className="w-full max-w-xs bg-slate-200 rounded-full h-2 overflow-hidden my-1 border border-slate-300/60">
                        <div 
                          className="bg-gradient-to-r from-amber-500 to-amber-600 h-2 rounded-full transition-all duration-1000 ease-linear"
                          style={{ 
                            width: `${Math.min(100, Math.max(0, Math.round(((totalCd - cooldownRemainingSeconds) / totalCd) * 100)))}%` 
                          }}
                        />
                      </div>

                      <p className="text-xs text-slate-500 mt-2 max-w-sm font-medium leading-relaxed">
                        {isCleanupCd 
                          ? (cooldownMessage && !cooldownMessage.includes('30-minute') ? cooldownMessage : 'A validation issue occurred. Database rollback and record purge are running in the background. Next upload will be unlocked in 10 minutes.') 
                          : (cooldownMessage && !cooldownMessage.includes('10-minute') && !cooldownMessage.includes('rollback') ? cooldownMessage : 'All sales uploads, roster imports, and user modifications are locked in Read-Only mode for 30 minutes following an upload to protect database integrity.')}
                      </p>

                      {/* Disabled "Click here to upload" button */}
                      <button 
                        disabled={true}
                        className="mt-4 px-5 py-2.5 bg-slate-100 text-slate-400 border border-slate-200 rounded-xl text-xs font-bold cursor-not-allowed flex items-center gap-2 shadow-2xs"
                      >
                        <Lock size={13} className="text-amber-500" />
                        Click here to upload (Disabled - {formattedCooldownLong} remaining)
                      </button>
                    </div>
                  );
                })() : isLocked ? (
                  <>
                    <div className="w-14 h-14 bg-amber-500/10 text-amber-600 rounded-full flex items-center justify-center mb-3">
                      <Database className="w-7 h-7" />
                    </div>
                    <p className="text-sm text-slate-800 font-bold">Upload Temporarily Locked</p>
                    <p className="text-xs text-amber-700 mt-1 max-w-sm font-medium">
                      {lockReason || 'Another ingestion process is active.'} Only one upload or modification can run at a time to prevent conflicts.
                    </p>
                  </>
                ) : (
                  <>
                    <div className="w-14 h-14 bg-[#0D3B8E]/8 text-[#0D3B8E] rounded-full flex items-center justify-center mb-3 group-hover:scale-110 group-hover:bg-[#0D3B8E] group-hover:text-white transition-all duration-200">
                      <UploadCloud className="w-7 h-7" />
                    </div>
                    <p className="text-sm text-slate-800 font-bold">Click here to upload or drag Excel file</p>
                    <p className="text-xs text-slate-400 mt-1 font-medium">Accepted formats: {accept}</p>
                  </>
                )}
              </motion.div>
            )}

            {uploadState.status === 'uploading' && (
              <motion.div 
                key="uploading"
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center w-full max-w-md mx-auto text-center"
              >
                <div className="w-12 h-12 bg-[#0D3B8E]/10 text-[#0D3B8E] rounded-full flex items-center justify-center mb-3 animate-pulse">
                  <FileText size={24} />
                </div>
                <p className="text-sm text-slate-900 font-bold mb-1 truncate max-w-sm">Uploading {uploadState.fileName}...</p>
                {uploadState.uploadStartTime && (
                  <p className="text-[11px] text-slate-400 font-medium mb-2 flex items-center justify-center gap-1">
                    <Clock size={11} /> Started: {uploadState.uploadStartTime}
                  </p>
                )}
                <p className="text-xs text-slate-500 mb-3">{formatFriendlyStatusMessage(uploadState.statusMessage)}</p>
                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                  <motion.div 
                    className="h-full bg-[#0D3B8E] rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${uploadState.progress}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
                <p className="text-slate-500 text-xs mt-2 font-bold">{uploadState.progress}%</p>
                <button
                  type="button"
                  onClick={() => setShowRollbackConfirm(true)}
                  disabled={isCancelling}
                  className="mt-2.5 px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold rounded-lg transition-colors border border-slate-200 inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  title="Cancel upload"
                >
                  <X size={12} /> Cancel Upload
                </button>
              </motion.div>
            )}

            {uploadState.status === 'processing' && (
              <motion.div 
                key="processing"
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center w-full max-w-lg mx-auto text-center py-2"
              >
                <div className="relative mb-3">
                  <div className="w-14 h-14 bg-amber-500/10 border border-amber-200 text-amber-600 rounded-2xl flex items-center justify-center">
                    <Database size={28} className="animate-pulse" />
                  </div>
                  <div className="absolute -bottom-1 -right-1 bg-amber-500 text-white rounded-full p-1 shadow-xs">
                    <RefreshCw size={12} className="animate-spin" />
                  </div>
                </div>

                <h3 className="text-sm font-bold text-slate-900">Processing Data Ingestion...</h3>

                {/* Sheet Details & Live Timer */}
                <div className="flex flex-wrap items-center justify-center gap-2 mt-2.5 mb-2">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-100 text-slate-800 text-xs font-bold rounded-lg border border-slate-200 truncate max-w-[260px]">
                    <FileText size={13} className="text-[#0D3B8E] shrink-0" />
                    <span className="truncate">{uploadState.fileName}</span>
                  </span>
                  {uploadState.uploadStartTime && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-50 text-blue-700 text-[11px] font-semibold rounded-lg border border-blue-200">
                      <Clock size={12} />
                      Started: {uploadState.uploadStartTime}
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-50 text-amber-800 text-[11px] font-bold rounded-lg border border-amber-200">
                    <RefreshCw size={11} className="animate-spin text-amber-600" />
                    Elapsed: {formatDuration(uploadState.elapsedSeconds)}
                  </span>
                </div>

                <p className="text-xs text-slate-500 mt-1 max-w-md font-medium">{formatFriendlyStatusMessage(uploadState.statusMessage)}</p>

                <button
                  type="button"
                  onClick={() => setShowRollbackConfirm(true)}
                  disabled={isCancelling}
                  className="mt-2.5 px-3.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-semibold rounded-lg transition-colors border border-rose-200 inline-flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-2xs"
                  title="Stop execution and rollback this upload"
                >
                  {isCancelling ? (
                    <>
                      <RefreshCw size={12} className="animate-spin text-rose-600" />
                      <span>Stopping & Rolling Back...</span>
                    </>
                  ) : (
                    <>
                      <X size={13} className="text-rose-600" />
                      <span>Cancel & Rollback Ingestion</span>
                    </>
                  )}
                </button>

                <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden mt-4">
                  <motion.div 
                    className="h-full bg-[#0D3B8E] rounded-full"
                    initial={{ width: '30%' }}
                    animate={{ width: `${uploadState.progress}%` }}
                    transition={{ duration: 0.4 }}
                  />
                </div>
              </motion.div>
            )}

            {uploadState.status === 'success' && (
              <motion.div 
                key="success"
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center w-full max-w-xl mx-auto text-center"
              >
                <div className="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mb-3">
                  <CheckCircle2 size={28} />
                </div>
                <h3 className="text-sm font-bold text-slate-900">Database Confirmation Received!</h3>
                <p className="text-xs text-slate-500 mt-0.5 font-medium">{uploadState.fileName} is fully saved in database.</p>

                <div className="mt-4 w-full grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 bg-slate-50 border border-slate-200/80 rounded-xl text-center">
                  <div className="p-2.5 bg-white rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Sheet Name</p>
                    <p className="text-xs font-bold text-slate-800 mt-1 truncate" title={uploadState.fileName}>
                      {uploadState.fileName || '—'}
                    </p>
                  </div>
                  <div className="p-2.5 bg-white rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Saved Rows</p>
                    <p className="text-base font-bold text-emerald-700 mt-0.5">
                      {uploadState.importedRows ? uploadState.importedRows.toLocaleString() : '—'}
                    </p>
                  </div>
                  <div className="p-2.5 bg-white rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Upload Time</p>
                    <p className="text-xs font-bold text-slate-700 mt-1 flex items-center justify-center gap-1">
                      <Clock size={11} className="text-slate-400" />
                      {uploadState.uploadStartTime || 'Just now'}
                    </p>
                  </div>
                  <div className="p-2.5 bg-white rounded-lg border border-slate-100">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Time Taken</p>
                    <p className="text-base font-bold text-slate-700 mt-0.5 flex items-center justify-center gap-1">
                      {formatDuration(uploadState.processingTimeSeconds || uploadState.elapsedSeconds)}
                    </p>
                  </div>
                </div>

                {isCooldownActive ? (
                  <div className="flex flex-col items-center mt-5 gap-2">
                    <button 
                      disabled={true}
                      className="px-5 py-2.5 bg-slate-100 text-slate-400 border border-slate-200 rounded-xl transition-colors text-xs font-bold shadow-2xs cursor-not-allowed flex items-center gap-2"
                    >
                      <Lock size={13} className="text-amber-500" />
                      Upload Another File (Enabled in {formattedCooldown})
                    </button>
                    <span className="text-[11px] text-amber-700 font-semibold flex items-center gap-1">
                      <Clock size={12} className="text-amber-600" /> 
                      {cooldownTotalSeconds <= 600 ? '10-Minute' : '30-Minute'} cooldown active • Next upload enabled in {formattedCooldownLong}
                    </span>
                  </div>
                ) : (
                  <button 
                    onClick={(e) => { e.stopPropagation(); resetUpload(); }}
                    className="mt-5 px-5 py-2.5 bg-[#0D3B8E] hover:bg-[#0A2F73] text-white rounded-xl transition-colors text-xs font-bold shadow-xs cursor-pointer"
                  >
                    Upload Another File
                  </button>
                )}
              </motion.div>
            )}

            {uploadState.status === 'error' && (
              <motion.div 
                key="error"
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center w-full max-w-xl mx-auto text-center"
              >
                <div className="w-12 h-12 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center mb-2">
                  <AlertCircle size={28} />
                </div>
                <h3 className="text-sm font-bold text-rose-900">Database Ingestion Notice</h3>

                {/* Sheet Details & Upload Time */}
                <div className="flex flex-wrap items-center justify-center gap-2 mt-2 mb-2">
                  {uploadState.fileName && (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-white border border-rose-200 text-slate-800 text-xs font-bold rounded-lg shadow-2xs truncate max-w-[260px]">
                      <FileText size={12} className="text-rose-600 shrink-0" />
                      <span className="truncate">{uploadState.fileName}</span>
                    </span>
                  )}
                  {uploadState.uploadStartTime && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-rose-50 border border-rose-200 text-rose-700 text-[11px] font-semibold rounded-lg">
                      <Clock size={11} />
                      Started: {uploadState.uploadStartTime}
                    </span>
                  )}
                  {uploadState.elapsedSeconds !== undefined && uploadState.elapsedSeconds > 0 && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-rose-50 border border-rose-200 text-rose-700 text-[11px] font-semibold rounded-lg">
                      Duration: {formatDuration(uploadState.elapsedSeconds)}
                    </span>
                  )}
                </div>

                <p className="text-xs text-rose-700 mt-1 max-w-md font-semibold">
                  {uploadState.errorMessage?.includes('[Errno 35]') 
                    ? 'Connection buffer stalled during insertion. The database was momentarily saturated.'
                    : (uploadState.errorLogs && uploadState.errorLogs.length > 0
                        ? `Upload rejected due to ${uploadState.errorLogs.length} unmapped issue(s). Data safely held to prevent corruption.`
                        : (uploadState.errorMessage ? formatLaymanShortError(uploadState.errorMessage) : 'Upload rejected due to mapping errors.'))}
                </p>

                {uploadState.errorLogs && uploadState.errorLogs.length > 0 && (
                  <div className="mt-3 w-full bg-rose-50/80 border border-rose-200 rounded-xl p-3 text-left max-h-36 overflow-y-auto">
                    <p className="text-[10px] font-bold text-rose-800 uppercase tracking-wider mb-1">
                      Detected Issues ({uploadState.errorLogs.length}):
                    </p>
                    <ul className="list-disc list-inside text-xs text-rose-700 space-y-1">
                      {uploadState.errorLogs.slice(0, 5).map((log, i) => (
                        <li key={i} className="truncate font-semibold">{formatLaymanShortError(log)}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {isCooldownActive && (
                  <div className="mt-3.5 inline-flex items-center gap-2 px-3.5 py-2 bg-amber-50 border border-amber-300/80 rounded-xl text-amber-900 text-xs font-semibold shadow-2xs">
                    <Clock size={14} className="text-amber-600 animate-spin shrink-0" style={{ animationDuration: '6s' }} />
                    <span>Upload locked for 10-minute rollback & cleanup buffer ({formattedCooldown} remaining)</span>
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-center gap-2.5 mt-4">
                  <button 
                    onClick={async (e) => {
                      e.stopPropagation();
                      const bId = uploadState.batchId;
                      try {
                        const token = localStorage.getItem('token');
                        const headers: Record<string, string> = {};
                        if (token) headers['Authorization'] = `Bearer ${token}`;
                        const endpoint = bId ? `${API_BASE_URL}/uploads/batches/${bId}` : `${API_BASE_URL}/uploads/latest`;
                        const res = await fetch(endpoint, { headers });
                        if (res.ok) {
                          const data = await res.json();
                          const stMain = (data?.status || '').toLowerCase();
                          if (['loaded', 'completed', 'success'].includes(stMain)) {
                            const imported = data.imported_rows ?? data.row_count ?? 0;
                            setUploadState({
                              status: 'success',
                              progress: 100,
                              fileName: data.source_file || uploadState.fileName || 'IMFL Data May-26.xlsb',
                              batchId: data.batch_id || bId,
                              importedRows: imported,
                              failedRows: data.failed_rows ?? 0,
                              duplicateRows: data.duplicate_rows ?? 0,
                              processingTimeSeconds: data.processing_time_seconds || uploadState.elapsedSeconds,
                              uploadStartTime: uploadState.uploadStartTime || 'Recently',
                              statusMessage: data.remarks || 'All Records Successfully Verified & Saved!'
                            });
                            startCooldownManually(1800, 'Upload completed successfully. 30-minute verification cooldown active.');
                            return;
                          }
                        }
                      } catch (errCheck) {
                        console.error('Failed to check live DB status:', errCheck);
                      }
                      resetUpload();
                    }}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl transition-colors text-xs font-bold cursor-pointer shadow-xs flex items-center gap-1.5"
                  >
                    <CheckCircle2 size={13} />
                    Check Live DB Status
                  </button>
                  <button 
                    onClick={(e) => { e.stopPropagation(); resetUpload(); }}
                    className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl transition-colors text-xs font-bold cursor-pointer"
                  >
                    {isCooldownActive ? 'Dismiss & View Cooldown Status' : 'Try Uploading Again'}
                  </button>
                  <button 
                    onClick={(e) => { 
                      e.stopPropagation(); 
                      const el = document.getElementById('unified-error-section');
                      if (el) el.scrollIntoView({ behavior: 'smooth' });
                    }}
                    className="px-4 py-2 bg-white border border-rose-200 text-rose-700 hover:bg-rose-50 rounded-xl transition-colors text-xs font-bold cursor-pointer shadow-2xs"
                  >
                    Inspect in Diagnostics Center ↓
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Instructions Card */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-2xs p-7">
        <h2 className="text-sm font-bold text-slate-900 mb-5 tracking-tight">Upload Instructions</h2>
        <ul className="space-y-4">
          {instructions.map((inst, idx) => (
            <li key={idx} className="flex items-start gap-3">
              <span className="w-6 h-6 bg-slate-100 text-slate-600 rounded-lg shrink-0 flex items-center justify-center text-[10px] font-bold">
                {String(idx + 1).padStart(2, '0')}
              </span>
              <p className="text-xs text-slate-600 leading-relaxed pt-0.5 font-medium">{inst}</p>
            </li>
          ))}
        </ul>

        <button className="mt-7 w-full py-3 px-4 bg-[#0D3B8E] hover:bg-[#0A2F73] active:scale-[0.99] text-white rounded-xl text-xs font-bold shadow-md shadow-[#0D3B8E]/15 transition-all duration-200 cursor-pointer flex items-center justify-center gap-2">
          Download Template
        </button>
      </div>

      {/* Rollback Confirmation Modal Popup */}
      <AnimatePresence>
        {showRollbackConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 text-center relative overflow-hidden"
            >
              <div className="w-14 h-14 bg-rose-100 text-rose-600 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-rose-200 shadow-inner">
                <AlertCircle className="w-7 h-7 text-rose-600" />
              </div>

              <h3 className="text-base font-extrabold text-slate-900 mb-2">
                Confirm Cancellation & Rollback
              </h3>

              <div className="bg-rose-50 border border-rose-200/80 rounded-xl p-3.5 my-3 text-center">
                <p className="text-sm font-bold text-rose-800 leading-snug">
                  Do you surely want to rollback? All your records will be lost.
                </p>
              </div>

              <p className="text-xs text-slate-500 mb-6 leading-relaxed">
                Ongoing ingestion will be stopped immediately. Any partial or temporary rows will be safely purged from the database.
              </p>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setShowRollbackConfirm(false)}
                  disabled={isCancelling}
                  className="flex-1 py-2.5 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition-colors cursor-pointer border border-slate-200"
                >
                  No, Keep Uploading
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    setShowRollbackConfirm(false);
                    await handleCancelUpload();
                  }}
                  disabled={isCancelling}
                  className="flex-1 py-2.5 px-4 bg-rose-600 hover:bg-rose-700 active:scale-[0.98] text-white text-xs font-bold rounded-xl transition-all cursor-pointer shadow-md shadow-rose-600/25 flex items-center justify-center gap-1.5"
                >
                  <X size={14} />
                  Yes, Rollback
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
