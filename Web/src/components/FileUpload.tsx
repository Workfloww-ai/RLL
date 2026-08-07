import React, { useState, useRef, useEffect } from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle, Database, RefreshCw, Server, X, Check, Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { FileUploadState } from '../types';

interface FileUploadProps {
  title: string;
  instructions: string[];
  accept?: string;
  uploadEndpoint?: string;
  onUploadComplete?: (fileName: string) => void;
}

export default function FileUpload({ title, instructions, accept = ".xlsx, .xls, .xlsb, .csv, .numbers", uploadEndpoint, onUploadComplete }: FileUploadProps) {
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      e.target.value = '';
      processFile(selectedFile);
    }
  };

  const startPollingBatchStatus = (batchId: number, fileName: string) => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
    }

    let pollAttempts = 0;
    const maxPollAttempts = 360; // Allow up to 6 minutes polling for 500k+ row files

    pollTimerRef.current = setInterval(async () => {
      pollAttempts += 1;
      try {
        const token = localStorage.getItem('token');
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch(`http://localhost:8000/api/v1/uploads/batches/${batchId}`, { headers });
        if (!res.ok) {
          if (pollAttempts >= maxPollAttempts) {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            setUploadState({
              status: 'error',
              progress: 0,
              fileName,
              batchId,
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
          currentProgress = Math.min(90, 40 + pollAttempts * 2);
        }

        if (isSuccess) {
          // Backend has confirmed all data is completely saved in database!
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setUploadState({
            status: 'success',
            progress: 100,
            fileName,
            batchId,
            importedRows: imported,
            failedRows: batchInfo.failed_rows ?? 0,
            duplicateRows: batchInfo.duplicate_rows ?? 0,
            processingTimeSeconds: batchInfo.processing_time_seconds ?? 0,
            statusMessage: batchInfo.remarks || 'All records successfully verified and saved into database!'
          });
          if (onUploadComplete) onUploadComplete(fileName);
        } else if (isFailed) {
          // Background ingestion encountered errors
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);

          // Fetch error logs for detail if available
          let logs: string[] = [];
          try {
            const logsRes = await fetch(`http://localhost:8000/api/v1/uploads/batches/${batchId}/logs`, { headers });
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
            errorMessage: batchInfo.remarks || 'Database insertion failed due to data validation errors.',
            errorLogs: logs
          });
        } else {
          // Still processing/pending in database
          setUploadState({
            status: 'processing',
            progress: currentProgress,
            fileName,
            batchId,
            statusMessage: batchInfo.remarks || 'Saving data rows into database...'
          });

          if (pollAttempts >= maxPollAttempts) {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            setUploadState({
              status: 'error',
              progress: 0,
              fileName,
              batchId,
              errorMessage: 'Database ingestion took too long to respond.'
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
            errorMessage: 'Network error while checking database status.'
          });
        }
      }
    }, 1000);
  };

  const processFile = async (file: File) => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);

    setUploadState({
      status: 'uploading',
      progress: 15,
      fileName: file.name,
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

      const targetUrl = uploadEndpoint || 'http://localhost:8000/api/v1/uploads/';

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
        statusMessage: data.remarks || 'File received. Backend is parsing data and writing into database...'
      });

      startPollingBatchStatus(batchId, file.name);

    } catch (error: any) {
      console.error('Upload error:', error);
      setUploadState({
        status: 'error',
        progress: 0,
        fileName: file.name,
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
      <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col min-h-[340px]">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-800">{title}</h2>
          <div className="flex items-center gap-2">
            {uploadState.status === 'success' && (
              <span className="flex items-center gap-1 px-2.5 py-1 bg-emerald-50 border border-emerald-200 text-emerald-700 text-[10px] font-bold rounded-full uppercase tracking-wider">
                <Check size={11} /> Saved in DB
              </span>
            )}
          </div>
        </div>

        <div 
          className={`border-2 border-dashed rounded-xl flex-1 flex flex-col items-center justify-center p-6 transition-all duration-200 ${
            uploadState.status === 'idle' ? 'border-slate-300 bg-slate-50/50 hover:bg-slate-100/60 hover:border-slate-400 cursor-pointer group' : 
            uploadState.status === 'processing' ? 'border-amber-300 bg-amber-50/20' :
            uploadState.status === 'success' ? 'border-emerald-300 bg-emerald-50/30' :
            'border-rose-300 bg-rose-50/20'
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
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="flex flex-col items-center text-center"
              >
                <div className="w-14 h-14 bg-blue-50 text-[#004B87] rounded-full flex items-center justify-center mb-3 group-hover:scale-110 transition-transform shadow-xs">
                  <UploadCloud className="w-7 h-7" />
                </div>
                <p className="text-sm text-slate-700 font-bold">Click to upload or drag Excel file</p>
                <p className="text-xs text-slate-400 mt-1">Accepted formats: {accept}</p>
              </motion.div>
            )}

            {uploadState.status === 'uploading' && (
              <motion.div 
                key="uploading"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center w-full max-w-md mx-auto text-center"
              >
                <div className="w-12 h-12 bg-indigo-50 text-[#004B87] rounded-full flex items-center justify-center mb-3 animate-pulse">
                  <FileText size={24} />
                </div>
                <p className="text-sm text-slate-800 font-bold mb-1">Uploading {uploadState.fileName}...</p>
                <p className="text-xs text-slate-500 mb-3">{uploadState.statusMessage}</p>
                <div className="w-full h-2.5 bg-slate-200 rounded-full overflow-hidden">
                  <motion.div 
                    className="h-full bg-[#004B87] rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${uploadState.progress}%` }}
                    transition={{ duration: 0.3 }}
                  />
                </div>
                <p className="text-slate-500 text-xs mt-2 font-medium">{uploadState.progress}%</p>
              </motion.div>
            )}

            {uploadState.status === 'processing' && (
              <motion.div 
                key="processing"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center w-full max-w-md mx-auto text-center py-2"
              >
                <div className="relative mb-3">
                  <div className="w-14 h-14 bg-amber-50 border border-amber-200 text-amber-600 rounded-2xl flex items-center justify-center shadow-xs">
                    <Database size={28} className="animate-pulse" />
                  </div>
                  <div className="absolute -bottom-1 -right-1 bg-amber-500 text-white rounded-full p-1 shadow-xs">
                    <RefreshCw size={12} className="animate-spin" />
                  </div>
                </div>

                <h3 className="text-sm font-bold text-slate-800">Processing...</h3>

                <div className="w-full h-2.5 bg-slate-200 rounded-full overflow-hidden mt-4">
                  <motion.div 
                    className="h-full bg-amber-500 rounded-full bg-gradient-to-r from-amber-500 to-indigo-600"
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
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center w-full max-w-lg mx-auto"
              >
                <div className="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mb-3">
                  <CheckCircle size={28} />
                </div>
                <h3 className="text-base font-bold text-emerald-900">Database Confirmation Received!</h3>
                <p className="text-xs text-emerald-700 mt-0.5 font-medium">{uploadState.fileName} is fully saved in database.</p>

                <div className="mt-4 w-full grid grid-cols-3 gap-3 p-3 bg-white border border-emerald-200 rounded-xl shadow-xs text-center">
                  <div className="p-2 bg-emerald-50/50 rounded-lg">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Saved Rows</p>
                    <p className="text-base font-bold text-emerald-700 mt-0.5">
                      {uploadState.importedRows ? uploadState.importedRows.toLocaleString() : '—'}
                    </p>
                  </div>
                  <div className="p-2 bg-emerald-50/50 rounded-lg">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Time Taken</p>
                    <p className="text-base font-bold text-slate-700 mt-0.5 flex items-center justify-center gap-1">
                      <Clock size={12} className="text-slate-400" />
                      {uploadState.processingTimeSeconds ? `${uploadState.processingTimeSeconds}s` : '<1s'}
                    </p>
                  </div>
                  <div className="p-2 bg-emerald-50/50 rounded-lg">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Batch ID</p>
                    <p className="text-base font-bold text-slate-700 mt-0.5">#{uploadState.batchId || 1}</p>
                  </div>
                </div>

                <button 
                  onClick={(e) => { e.stopPropagation(); resetUpload(); }}
                  className="mt-5 px-5 py-2 bg-slate-800 text-white rounded-lg hover:bg-slate-700 transition-colors text-xs font-bold shadow-xs cursor-pointer"
                >
                  Upload Another File
                </button>
              </motion.div>
            )}

            {uploadState.status === 'error' && (
              <motion.div 
                key="error"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center w-full max-w-lg mx-auto text-center"
              >
                <div className="w-12 h-12 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center mb-2">
                  <AlertCircle size={28} />
                </div>
                <h3 className="text-sm font-bold text-rose-900">Database Ingestion Failed</h3>
                <p className="text-xs text-rose-700 mt-1 max-w-md font-medium">{uploadState.errorMessage}</p>

                {uploadState.errorLogs && uploadState.errorLogs.length > 0 && (
                  <div className="mt-3 w-full bg-rose-50 border border-rose-200 rounded-lg p-3 text-left max-h-32 overflow-y-auto">
                    <p className="text-[10px] font-bold text-rose-800 uppercase tracking-wider mb-1">Validation Errors:</p>
                    <ul className="list-disc list-inside text-xs text-rose-700 space-y-1">
                      {uploadState.errorLogs.slice(0, 5).map((log, i) => (
                        <li key={i}>{log}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <button 
                  onClick={(e) => { e.stopPropagation(); resetUpload(); }}
                  className="mt-4 px-4 py-2 bg-rose-600 text-white rounded-lg hover:bg-rose-700 transition-colors text-xs font-bold cursor-pointer"
                >
                  Try Uploading Again
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
        <h2 className="text-lg font-bold text-slate-800 mb-4">Upload Instructions</h2>
        <ul className="space-y-3">
          {instructions.map((inst, idx) => (
            <li key={idx} className="flex items-start gap-3">
              <span className="w-5 h-5 bg-slate-100 rounded text-slate-600 flex-shrink-0 flex items-center justify-center text-[10px] font-bold">
                {String(idx + 1).padStart(2, '0')}
              </span>
              <p className="text-xs text-slate-600 leading-relaxed pt-0.5">{inst}</p>
            </li>
          ))}
        </ul>
        <button className="mt-6 w-full py-2.5 bg-slate-800 text-white rounded-lg text-sm font-bold flex items-center justify-center gap-2 hover:bg-slate-700 transition-colors cursor-pointer">
          Download Template
        </button>
      </div>
    </div>
  );
}
