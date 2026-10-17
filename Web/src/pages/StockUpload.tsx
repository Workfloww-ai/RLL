import React, { useEffect, useState } from 'react';
import FileUpload, { formatFriendlyStatusMessage } from '../components/FileUpload';
import UploadErrorViewer from '../components/UploadErrorViewer';
import { API_BASE_URL } from '../config';
import { useSystemLock } from '../contexts/SystemLockContext';
import { Clock, RefreshCw } from 'lucide-react';

interface LatestUpload {
  lastUploadFormatted: string;
  uploaderInfo: string;
  recordsCountFormatted: string;
  status: 'SUCCESS' | 'FAILED' | 'PROCESSING' | 'NONE';
  remarksText: string;
}

export default function StockUpload() {
  const { isCooldownActive, formattedCooldown, formattedCooldownLong, cooldownTotalSeconds, cooldownMessage } = useSystemLock();
  const [activeErrorBatchId, setActiveErrorBatchId] = useState<string>('all');
  const [errorRefreshTrigger, setErrorRefreshTrigger] = useState<number>(0);
  const [latestUpload, setLatestUpload] = useState<LatestUpload>({
    lastUploadFormatted: 'No uploads yet',
    uploaderInfo: 'No sales data uploaded for this company',
    recordsCountFormatted: '0 Records',
    status: 'NONE',
    remarksText: 'Upload sales data to begin tracking analytics.'
  });

  const handleUploadStart = (fileName: string) => {
    const createdAt = new Date();
    const formattedDate = createdAt.toLocaleString('en-US', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
    const uploaderName = localStorage.getItem('user_name') || 'Admin User';
    setLatestUpload({
      lastUploadFormatted: formattedDate,
      uploaderInfo: `${fileName} (${uploaderName})`,
      recordsCountFormatted: 'Processing...',
      status: 'PROCESSING',
      remarksText: 'Processing started: Uploading sheet...'
    });
  };

  const fetchLatestBatch = async () => {
    try {
      const token = localStorage.getItem('token');
      let tenantId = localStorage.getItem('rll_tenant_id');
      if (!tenantId) {
        try {
          const raw = localStorage.getItem('user');
          if (raw) {
            const u = JSON.parse(raw);
            if (u && u.tenant_id) tenantId = u.tenant_id;
          }
        } catch {}
      }
      const headers: Record<string, string> = {
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...(tenantId ? { 'X-Tenant-ID': tenantId } : {})
      };
      const endpoint = tenantId
        ? `${API_BASE_URL}/uploads/latest?tenant_id=${encodeURIComponent(tenantId)}`
        : `${API_BASE_URL}/uploads/latest`;
      const res = await fetch(endpoint, { headers });
      if (res.ok) {
        const data = await res.json();
        if (data && data.batch_id && data.status !== 'none') {
          const createdAt = data.created_at ? new Date(data.created_at) : null;
          const formattedDate = createdAt ? createdAt.toLocaleString('en-US', {
            day: '2-digit',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
          }) : 'Just now';

          const statusLower = (data.upload_status || data.status || '').toLowerCase();
          const isProcessing = ['processing', 'queued', 'running', 'validating', 'aggregating', 'uploading'].includes(statusLower);
          const isFailed = !isProcessing && (statusLower === 'failed' || statusLower === 'interrupted' || statusLower === 'error');
          const isSuccess = !isProcessing && !isFailed && (['success', 'loaded', 'completed'].includes(statusLower) || (data.imported_rows > 0 && !isFailed));
          const imported = isSuccess ? (data.imported_rows || data.total_rows || 0) : 0;

          const fileName = data.source_file || data.file_name || 'Upload File';
          const uploaderName = data.uploader_name || data.uploaded_by_name || localStorage.getItem('user_name') || 'Admin User';
          const uploaderInfo = `${fileName} (${uploaderName})`;

          setLatestUpload({
            lastUploadFormatted: formattedDate,
            uploaderInfo: uploaderInfo,
            recordsCountFormatted: isSuccess ? `${imported.toLocaleString()} Records` : (isProcessing ? 'Processing...' : '0 Records'),
            status: isProcessing ? 'PROCESSING' : (isSuccess ? 'SUCCESS' : 'FAILED'),
            remarksText: isProcessing 
              ? formatFriendlyStatusMessage(data.remarks || 'Processing: Validating and saving records...')
              : (isSuccess ? `${imported.toLocaleString()} Records Verified & Saved` : formatFriendlyStatusMessage(data.remarks || 'Upload halted due to validation issues.'))
          });
        } else {
          setLatestUpload({
            lastUploadFormatted: 'No uploads yet',
            uploaderInfo: 'No sales data uploaded for this company',
            recordsCountFormatted: '0 Records',
            status: 'NONE',
            remarksText: 'Upload sales data to begin tracking analytics.'
          });
        }
      }
    } catch (err) {
      console.warn('Failed to fetch live upload batch details:', err);
    }
  };

  useEffect(() => {
    fetchLatestBatch();
  }, []);

  return (
    <div className="w-full space-y-6 pb-16">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Sales Data Upload</h1>
        <p className="text-slate-500 mt-1 text-xs font-medium">Upload the latest sales data for real-time outlet visibility.</p>
      </div>

      {isCooldownActive && (
        <div className="bg-amber-500/10 border border-amber-300 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-2xs">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-amber-500 text-white flex items-center justify-center shrink-0 shadow-xs">
              <Clock className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-bold text-slate-900">
                  {cooldownTotalSeconds <= 600 ? '10-Minute Rollback Buffer Active' : '30-Minute Cooldown Active • System in Read-Only Mode'}
                </h4>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-amber-200/90 text-amber-950 border border-amber-300">
                  READ-ONLY
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1 font-medium leading-relaxed">
                {cooldownMessage || (
                  cooldownTotalSeconds <= 600
                    ? 'A 10-minute rollback & purge buffer is active following a file validation issue. Next upload will be enabled once the timer completes.'
                    : 'A 30-minute buffer is active after the last upload to ensure complete background database indexing and accuracy. Next upload and system updates will be enabled once the timer completes.'
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 self-start sm:self-auto bg-white border border-amber-300/80 rounded-xl px-4 py-2.5 shadow-2xs shrink-0">
            <Clock size={16} className="text-amber-600 animate-spin" style={{ animationDuration: '6s' }} />
            <div className="flex flex-col text-right">
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Unlocks in</span>
              <span className="text-base font-black text-amber-600 font-mono tracking-wider">{formattedCooldown}</span>
            </div>
          </div>
        </div>
      )}

      <FileUpload 
        title=""
        instructions={[
          "Ensure column headers match exactly with the provided template.",
          "Accepted formats: .xlsx, .xls, .xlsb, .csv, .numbers.",
          "Maximum file size: 30MB.",
          "System handles duplicate removal automatically based on Timestamp."
        ]}
        onUploadStart={handleUploadStart}
        onUploadComplete={() => {
          fetchLatestBatch();
          setErrorRefreshTrigger(prev => prev + 1);
        }}
        onErrorOccurred={(batchId) => {
          if (batchId) setActiveErrorBatchId(String(batchId));
          fetchLatestBatch();
          setErrorRefreshTrigger(prev => prev + 1);
        }}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
        <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-2xs hover:shadow-xs transition-shadow">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-[10px] font-bold text-[#0D3B8E] uppercase tracking-wider">
              {latestUpload.status === 'PROCESSING' ? 'Current Upload' : 'Last Upload'}
            </h3>
            {latestUpload.status === 'PROCESSING' && (
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-blue-100 text-[#0D3B8E] animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-[#0D3B8E] animate-ping" />
                IN PROGRESS
              </span>
            )}
          </div>
          <p className="text-xl font-bold text-slate-900">{latestUpload.lastUploadFormatted}</p>
          <p className="text-xs text-slate-400 font-medium mt-1 truncate" title={latestUpload.uploaderInfo}>
            {latestUpload.uploaderInfo}
          </p>
        </div>

        <div className={`rounded-2xl border p-6 shadow-2xs hover:shadow-xs transition-all ${
          latestUpload.status === 'FAILED' 
            ? 'bg-rose-50/40 border-rose-200' 
            : latestUpload.status === 'PROCESSING'
              ? 'bg-blue-50/40 border-blue-200'
              : 'bg-white border-slate-200/80'
        }`}>
          <div className="flex items-center justify-between mb-2">
            <h3 className={`text-[10px] font-bold uppercase tracking-wider ${
              latestUpload.status === 'FAILED' ? 'text-rose-700' : 'text-[#0D3B8E]'
            }`}>
              Records Processed
            </h3>
            {latestUpload.status === 'PROCESSING' && (
              <RefreshCw className="w-3.5 h-3.5 text-[#0D3B8E] animate-spin" />
            )}
          </div>
          <p className={`text-xl font-bold ${
            latestUpload.status === 'FAILED' 
              ? 'text-rose-950' 
              : latestUpload.status === 'PROCESSING'
                ? 'text-[#0D3B8E]'
                : 'text-slate-900'
          }`}>
            {latestUpload.status === 'SUCCESS' && `${latestUpload.recordsCountFormatted} Records`}
            {latestUpload.status === 'PROCESSING' && 'Processing Data...'}
            {latestUpload.status === 'FAILED' && 'Processing Failed (Errors Found)'}
            {latestUpload.status === 'NONE' && 'No Upload Data'}
          </p>
          <p className={`text-xs font-medium mt-1 truncate ${
            latestUpload.status === 'FAILED' 
              ? 'text-rose-800' 
              : latestUpload.status === 'PROCESSING'
                ? 'text-[#0D3B8E] font-semibold'
                : 'text-slate-400'
          }`}>
            {latestUpload.status === 'SUCCESS' 
              ? '100% Data Accuracy • All Records Verified & Saved' 
              : (latestUpload.status === 'PROCESSING'
                  ? formatFriendlyStatusMessage(latestUpload.remarksText || 'Processing: Validating and saving records...')
                  : formatFriendlyStatusMessage(latestUpload.remarksText))}
          </p>
        </div>
      </div>

      {/* Unified Ingestion Diagnostics & Error Center */}
      <UploadErrorViewer 
        initialBatchId={activeErrorBatchId} 
        refreshTrigger={errorRefreshTrigger}
        onRefreshRequested={fetchLatestBatch}
      />
    </div>
  );
}
