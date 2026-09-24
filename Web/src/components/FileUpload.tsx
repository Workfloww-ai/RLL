import React, { useState, useRef, useEffect } from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle, Database, RefreshCw, Server, X, Check, Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { FileUploadState } from '../types';
import { API_BASE_URL } from '../config';

interface FileUploadProps {
  title: string;
  instructions: string[];
  accept?: string;
  uploadEndpoint?: string;
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

  let cleanMsg = msg.replace(/^Upload validation failed for \d+ issue\(s\):\s*/i, '').strip?.() || msg;
  cleanMsg = cleanMsg.replace(/\[Row\s*#?\d+\]\s*/i, '');
  return rowNum ? `${rowNum}: ${cleanMsg}` : cleanMsg;
}

export default function FileUpload({ title, instructions, accept = ".xlsx, .xls, .xlsb, .csv, .numbers", uploadEndpoint, onUploadComplete, onErrorOccurred }: FileUploadProps) {
  const [uploadState, setUploadState] = useState<FileUploadState>({ status: 'idle', progress: 0 });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
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
    const maxPollAttempts = 1200; // Allow up to 20 minutes polling for 500k+ row files

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

    const startMs = Date.now();
    const timeFormatted = new Date().toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });

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
        body: formData
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
      console.error('Upload error:', error);
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
    setUploadState({ status: 'idle', progress: 0 });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
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

                <div className="flex flex-wrap items-center justify-center gap-2.5 mt-4">
                  {/* {uploadState.batchId && (
                    <button 
                      onClick={(e) => { e.stopPropagation(); checkBatchStatusDirectly(); }}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl transition-colors text-xs font-bold cursor-pointer shadow-xs flex items-center gap-1.5"
                    >
                      <RefreshCw size={12} /> Check Live DB Status
                    </button>
                  )} */}
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
  );
}
