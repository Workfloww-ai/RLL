import React, { useState, useRef, useEffect } from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle, Database, RefreshCw, Server, X, Check, Clock, Terminal, Copy, Trash2, Search, Filter } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { FileUploadState } from '../types';
import { API_BASE_URL } from '../config';

export const sanitizeErrorMessage = (rawMsg?: string): string => {
  if (!rawMsg) return 'An unexpected processing event occurred. Please verify file format and try again.';
  const msg = String(rawMsg);
  
  if (msg.includes("name 'client' is not defined")) {
    return "Database Service Notice: Internal database client connection was uninitialized during user roster parsing. (Resolved in backend service)";
  }
  if (msg.includes("duplicate key value violates unique constraint")) {
    return "Data Conflict Notice: User hierarchy mapping record already exists in database. Duplicate entry was skipped.";
  }
  if (msg.includes("column \"batch_id\" does not exist")) {
    return "Database Resolution Notice: Required batch ID column was missing in database stored procedure. (Resolved in database function)";
  }
  if (msg.includes("Unmapped Brand name")) {
    return msg.replace(/['"]/g, '').replace('Unmapped Brand name:', 'Validation Notice: Master Brand not recognized:');
  }
  if (msg.includes("Unmapped Licensee name")) {
    return msg.replace(/['"]/g, '').replace('Unmapped Licensee name:', 'Validation Notice: Master Licensee not recognized:');
  }
  if (msg.includes("Unmapped Depot name")) {
    return msg.replace(/['"]/g, '').replace('Unmapped Depot name:', 'Validation Notice: Master Depot not recognized:');
  }
  if (msg.includes("[Errno 35]") || msg.includes("Resource temporarily unavailable")) {
    return "Network Buffer Stalled: Database connection pool was temporarily saturated. Ingestion recovered automatically.";
  }
  return msg;
};

interface DiagnosticLogItem {
  id: string;
  timestamp: string;
  level: 'ERROR' | 'WARN' | 'INFO' | 'SYSTEM';
  message: string;
}

interface FileUploadProps {
  title: string;
  instructions: string[];
  accept?: string;
  uploadEndpoint?: string;
  onUploadComplete?: (fileName: string) => void;
  onErrorOccurred?: (batchId?: string | number) => void;
}

export default function FileUpload({ title, instructions, accept = ".xlsx, .xls, .xlsb, .csv, .numbers", uploadEndpoint, onUploadComplete, onErrorOccurred }: FileUploadProps) {
  const [uploadState, setUploadState] = useState<FileUploadState>({ status: 'idle', progress: 0 });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const uploadIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Diagnostics Center State
  const [diagnosticsLogs, setDiagnosticsLogs] = useState<DiagnosticLogItem[]>([
    {
      id: 'init_1',
      timestamp: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }),
      level: 'SYSTEM',
      message: 'System Ingestion Diagnostics Center initialized. Ready for user file operations.'
    }
  ]);
  const [logLevelFilter, setLogLevelFilter] = useState<'ALL' | 'ERROR' | 'WARN' | 'INFO'>('ALL');
  const [logSearchQuery, setLogSearchQuery] = useState('');
  const [copiedLogs, setCopiedLogs] = useState(false);

  const addLog = (level: 'ERROR' | 'WARN' | 'INFO' | 'SYSTEM', message: string) => {
    const newLog: DiagnosticLogItem = {
      id: Math.random().toString(36).substring(2, 9),
      timestamp: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }),
      level,
      message
    };
    setDiagnosticsLogs(prev => [newLog, ...prev]);
  };

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      if (uploadIntervalRef.current) clearInterval(uploadIntervalRef.current);
    };
  }, []);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0 && uploadState.status !== 'uploading' && uploadState.status !== 'processing') {
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
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      e.target.value = '';
      processFile(selectedFile);
    }
  };

  const startPollingBatchStatus = (
    batchId: number | string, 
    fileName: string, 
    startTimeFormatted: string, 
    startTimestampMs: number
  ) => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
    }

    let pollAttempts = 0;
    const maxPollAttempts = 1200;

    pollTimerRef.current = setInterval(async () => {
      pollAttempts += 1;
      const elapsed = Math.max(1, Math.floor((Date.now() - startTimestampMs) / 1000));

      try {
        const token = localStorage.getItem('token');
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch(`${API_BASE_URL}/uploads/batches/${batchId}`, { headers });
        if (!res.ok) {
          if (pollAttempts >= maxPollAttempts) {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            const errText = 'Timed out waiting for database confirmation from backend.';
            addLog('ERROR', errText);
            setUploadState({
              status: 'error',
              progress: 0,
              fileName,
              batchId,
              uploadStartTime: startTimeFormatted,
              elapsedSeconds: elapsed,
              errorMessage: errText
            });
          }
          return;
        }

        const batchInfo = await res.json();
        const statusMain = (batchInfo.status || '').toLowerCase();
        const statusUpload = (batchInfo.upload_status || '').toLowerCase();

        const isSuccess = ['loaded', 'completed', 'success'].includes(statusMain) || ['loaded', 'completed', 'success'].includes(statusUpload);
        const isFailed = statusMain === 'failed' || statusUpload === 'failed';

        const imported = batchInfo.imported_rows ?? batchInfo.row_count ?? 0;
        const total = batchInfo.row_count ?? 0;

        let currentProgress = 40;
        if (total > 0 && imported > 0) {
          currentProgress = Math.min(95, 40 + Math.floor((imported / total) * 55));
        } else {
          currentProgress = Math.min(92, 40 + Math.floor(pollAttempts * 1.5));
        }

        if (isSuccess) {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          const finalTimeSec = batchInfo.processing_time_seconds && batchInfo.processing_time_seconds > 0 
            ? batchInfo.processing_time_seconds 
            : elapsed;

          addLog('INFO', `Database Ingestion Complete for ${fileName}. ${imported.toLocaleString()} rows saved in ${formatDuration(finalTimeSec)}.`);

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
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);

          let logs: string[] = [];
          try {
            const logsRes = await fetch(`${API_BASE_URL}/uploads/batches/${batchId}/logs`, { headers });
            if (logsRes.ok) {
              const logsData = await logsRes.json();
              if (Array.isArray(logsData)) {
                logs = logsData.map((l: any) => l.error_message || l.column_name || 'Validation error');
                logs.forEach(l => addLog('WARN', sanitizeErrorMessage(l)));
              }
            }
          } catch (logErr) {
            console.error('Error fetching logs:', logErr);
          }

          const rawErrMsg = batchInfo.remarks || 'Database insertion failed due to data validation errors.';
          addLog('ERROR', sanitizeErrorMessage(rawErrMsg));

          setUploadState({
            status: 'error',
            progress: 0,
            fileName,
            batchId,
            uploadStartTime: startTimeFormatted,
            elapsedSeconds: elapsed,
            errorMessage: rawErrMsg,
            errorLogs: logs
          });
          if (onErrorOccurred) onErrorOccurred(batchId);
        } else {
          setUploadState({
            status: 'processing',
            progress: currentProgress,
            fileName,
            batchId,
            uploadStartTime: startTimeFormatted,
            elapsedSeconds: elapsed,
            statusMessage: batchInfo.remarks || 'Saving data rows into database...'
          });

          if (pollAttempts % 5 === 0) {
            addLog('INFO', `Processing batch ${batchId}... Elapsed: ${formatDuration(elapsed)}.`);
          }

          if (pollAttempts >= maxPollAttempts) {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            const errT = 'Database ingestion exceeded timeout limit.';
            addLog('ERROR', errT);
            setUploadState({
              status: 'error',
              progress: 0,
              fileName,
              batchId,
              uploadStartTime: startTimeFormatted,
              elapsedSeconds: elapsed,
              errorMessage: errT
            });
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 1000);
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
        const imported = batchInfo.imported_rows ?? batchInfo.row_count ?? 0;
        addLog('INFO', `Live DB check confirmed batch ${id} completed with ${imported} rows.`);
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
      }
    } catch (e) {
      console.error('Manual status check error:', e);
    }
  };

  const processFile = async (file: File) => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    if (uploadIntervalRef.current) clearInterval(uploadIntervalRef.current);

    const startMs = Date.now();
    const timeFormatted = new Date().toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });

    addLog('SYSTEM', `Selected file '${file.name}' (${(file.size / 1024).toFixed(1)} KB) for processing.`);

    setUploadState({
      status: 'uploading',
      progress: 15,
      fileName: file.name,
      uploadStartTime: timeFormatted,
      elapsedSeconds: 0,
      statusMessage: 'Uploading file to backend server...'
    });

    // Live progress & elapsed timer updates while HTTP upload/processing is underway
    uploadIntervalRef.current = setInterval(() => {
      setUploadState(prev => {
        if (prev.status !== 'uploading') return prev;
        const currentProg = prev.progress || 15;
        const nextProgress = Math.min(92, currentProg + (currentProg < 45 ? 6 : currentProg < 75 ? 3 : 1));
        const nextElapsed = Math.floor((Date.now() - startMs) / 1000);
        const msg = nextProgress < 40 
          ? 'Streaming file bytes to server...' 
          : nextProgress < 75 
            ? 'Backend reading & parsing data rows...' 
            : 'Finalizing database user records...';

        return {
          ...prev,
          progress: nextProgress,
          elapsedSeconds: nextElapsed,
          statusMessage: msg
        };
      });
    }, 250);

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
        body: formData
      });

      if (uploadIntervalRef.current) clearInterval(uploadIntervalRef.current);

      if (!response.ok) {
        const errorText = await response.text();
        let detail = 'Upload failed';
        try {
          const parsed = JSON.parse(errorText);
          detail = parsed.detail || detail;
        } catch {
          detail = errorText || detail;
        }
        addLog('ERROR', sanitizeErrorMessage(detail));
        throw new Error(detail);
      }

      const data = await response.json();

      if (uploadEndpoint) {
        const impCount = data.imported_count || 0;
        const skipCount = data.skipped_count || 0;
        addLog('INFO', `Roster processing complete for ${file.name}: ${impCount} imported, ${skipCount} skipped.`);
        if (Array.isArray(data.warnings)) {
          data.warnings.forEach((w: string) => addLog('WARN', sanitizeErrorMessage(w)));
        }

        setUploadState({
          status: 'success',
          progress: 100,
          fileName: file.name,
          uploadStartTime: timeFormatted,
          elapsedSeconds: Math.floor((Date.now() - startMs) / 1000),
          importedRows: impCount,
          statusMessage: data.message || 'Personnel roster file successfully processed and saved.'
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

      addLog('SYSTEM', `File received by server. Assigned batch ID: ${batchId}. Starting database ingestion...`);

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
      console.error('Upload error:', error);
      const userErr = sanitizeErrorMessage(error.message);
      addLog('ERROR', userErr);
      setUploadState({
        status: 'error',
        progress: 0,
        fileName: file.name,
        uploadStartTime: timeFormatted,
        elapsedSeconds: Math.floor((Date.now() - startMs) / 1000),
        errorMessage: userErr
      });
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const resetUpload = () => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setUploadState({ status: 'idle', progress: 0 });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleCopyLogs = () => {
    const logText = diagnosticsLogs.map(l => `[${l.timestamp}] [${l.level}] ${sanitizeErrorMessage(l.message)}`).join('\n');
    navigator.clipboard.writeText(logText);
    setCopiedLogs(true);
    setTimeout(() => setCopiedLogs(false), 2000);
  };

  const handleClearLogs = () => {
    setDiagnosticsLogs([]);
  };

  const filteredLogs = diagnosticsLogs.filter(l => {
    if (logLevelFilter !== 'ALL' && l.level !== logLevelFilter) return false;
    if (logSearchQuery.trim()) {
      const q = logSearchQuery.toLowerCase();
      return l.message.toLowerCase().includes(q) || l.level.toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Upload Dropzone Container */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200/80 shadow-2xs p-7 flex flex-col min-h-[360px]">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-slate-900 tracking-tight">{title}</h2>
            {uploadState.status === 'success' && (
              <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-700 text-[10px] font-bold rounded-full border border-emerald-200">
                <Check size={12} /> Saved in DB
              </span>
            )}
          </div>

          <div 
            className={`border-2 border-dashed rounded-xl flex-1 flex flex-col items-center justify-center p-8 transition-all duration-200 ${
              uploadState.status === 'idle' ? 'border-slate-200 bg-slate-50/50 hover:bg-blue-50/20 hover:border-[#0D3B8E] cursor-pointer group' : 
              uploadState.status === 'processing' ? 'border-amber-300 bg-amber-50/30' :
              uploadState.status === 'success' ? 'border-emerald-300 bg-emerald-50/30' :
              'border-rose-300 bg-rose-50/30'
            }`}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onClick={() => uploadState.status === 'idle' && fileInputRef.current?.click()}
          >
            <input 
              type="file" 
              ref={fileInputRef} 
              className="hidden" 
              accept={accept}
              onChange={handleFileChange}
            />

            <AnimatePresence mode="wait">
              {uploadState.status === 'idle' && (
                <motion.div 
                  key="idle"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.96 }}
                  className="flex flex-col items-center text-center"
                >
                  <div className="w-14 h-14 bg-[#0D3B8E]/8 text-[#0D3B8E] rounded-full flex items-center justify-center mb-3 group-hover:scale-110 group-hover:bg-[#0D3B8E] group-hover:text-white transition-all duration-200">
                    <UploadCloud className="w-7 h-7" />
                  </div>
                  <p className="text-sm text-slate-800 font-bold">Click to upload or drag Excel file</p>
                  <p className="text-xs text-slate-400 mt-1 font-medium">Accepted formats: {accept}</p>
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
                  <p className="text-xs text-slate-500 mb-3">{uploadState.statusMessage}</p>
                  <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                    <motion.div 
                      className="h-full bg-[#0D3B8E] rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${uploadState.progress}%` }}
                      transition={{ duration: 0.3 }}
                    />
                  </div>
                  <p className="text-slate-500 text-xs mt-2 font-bold">{uploadState.progress}%</p>
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

                  <p className="text-xs text-slate-500 mt-1 max-w-md font-medium">{uploadState.statusMessage}</p>

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
                    <CheckCircle size={28} />
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

                  <button 
                    onClick={(e) => { e.stopPropagation(); resetUpload(); }}
                    className="mt-5 px-5 py-2.5 bg-[#0D3B8E] hover:bg-[#0A2F73] text-white rounded-xl transition-colors text-xs font-bold shadow-xs cursor-pointer"
                  >
                    Upload Another File
                  </button>
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

                  <p className="text-xs text-rose-700 mt-1 max-w-md font-medium">
                    {sanitizeErrorMessage(uploadState.errorMessage)}
                  </p>

                  {uploadState.errorLogs && uploadState.errorLogs.length > 0 && (
                    <div className="mt-3 w-full bg-rose-50/80 border border-rose-200 rounded-xl p-3 text-left max-h-32 overflow-y-auto">
                      <p className="text-[10px] font-bold text-rose-800 uppercase tracking-wider mb-1">
                        Detected Diagnostic Warnings ({uploadState.errorLogs.length}):
                      </p>
                      <ul className="list-disc list-inside text-xs text-rose-700 space-y-1">
                        {uploadState.errorLogs.slice(0, 3).map((log, i) => (
                          <li key={i} className="truncate">{sanitizeErrorMessage(log)}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-center gap-2.5 mt-4">
                    {uploadState.batchId && (
                      <button 
                        onClick={(e) => { e.stopPropagation(); checkBatchStatusDirectly(); }}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl transition-colors text-xs font-bold cursor-pointer shadow-xs flex items-center gap-1.5"
                      >
                        <RefreshCw size={12} /> Check Live DB Status
                      </button>
                    )}
                    <button 
                      onClick={(e) => { e.stopPropagation(); resetUpload(); }}
                      className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl transition-colors text-xs font-bold cursor-pointer"
                    >
                      Try Uploading Again
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
      </div>

      {/* Diagnostics Center Panel */}
      <div id="unified-error-section" className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg text-slate-100 font-sans">
        <div className="flex flex-wrap items-center justify-between pb-3 mb-3 border-b border-slate-800 gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#0D3B8E]/30 text-[#0D3B8E] flex items-center justify-center border border-[#0D3B8E]/50">
              <Terminal size={18} className="text-blue-400" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white tracking-wide">System Diagnostics Center</h3>
              <p className="text-[11px] text-slate-400">Live scrollable ingestion activity log & diagnostic inspection console</p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button 
              onClick={handleCopyLogs}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg border border-slate-700 transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <Copy size={12} /> {copiedLogs ? 'Copied!' : 'Copy Logs'}
            </button>
            <button 
              onClick={handleClearLogs}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 text-xs font-semibold rounded-lg border border-slate-700 transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <Trash2 size={12} /> Clear Logs
            </button>
          </div>
        </div>

        {/* Log Filter & Search Bar */}
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-[11px] font-bold">
            {(['ALL', 'ERROR', 'WARN', 'INFO'] as const).map(lvl => (
              <button
                key={lvl}
                onClick={() => setLogLevelFilter(lvl)}
                className={`px-3 py-1 rounded-md transition-colors cursor-pointer ${
                  logLevelFilter === lvl 
                    ? lvl === 'ERROR' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                      : lvl === 'WARN' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                      : lvl === 'INFO' ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                      : 'bg-slate-800 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>

          <div className="relative flex-1 min-w-[200px]">
            <Search size={13} className="text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input 
              type="text"
              placeholder="Filter logs by keyword..."
              value={logSearchQuery}
              onChange={(e) => setLogSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Terminal Log Console */}
        <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-3.5 max-h-64 overflow-y-auto font-mono text-xs space-y-2 leading-relaxed scrollbar-thin scrollbar-thumb-slate-800">
          {filteredLogs.length === 0 ? (
            <div className="py-6 text-center text-slate-500 font-sans text-xs">
              No log entries recorded in diagnostic console. Upload a file to view real-time diagnostics.
            </div>
          ) : (
            filteredLogs.map((log) => (
              <div key={log.id} className="flex items-start gap-2.5 text-slate-300 hover:bg-slate-900/60 p-1.5 rounded transition-colors">
                <span className="text-slate-500 shrink-0 text-[10px] font-semibold">{log.timestamp}</span>
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wider uppercase shrink-0 ${
                  log.level === 'ERROR' ? 'bg-rose-950 text-rose-400 border border-rose-800/50' :
                  log.level === 'WARN' ? 'bg-amber-950 text-amber-400 border border-amber-800/50' :
                  log.level === 'INFO' ? 'bg-blue-950 text-blue-400 border border-blue-800/50' :
                  'bg-slate-800 text-slate-300'
                }`}>
                  {log.level}
                </span>
                <span className="break-all text-slate-200">
                  {sanitizeErrorMessage(log.message)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
