import React, { useState, useEffect, useMemo } from 'react';
import { 
  AlertTriangle, 
  AlertCircle, 
  CheckCircle, 
  RefreshCw, 
  Download, 
  Copy, 
  Search, 
  Layers, 
  ListFilter, 
  ChevronDown, 
  ChevronUp, 
  ShieldAlert, 
  Check, 
  Lightbulb,
  Database,
  WifiOff,
  FileSpreadsheet,
  HelpCircle,
  Clock
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { API_BASE_URL } from '../config';

export interface UploadErrorItem {
  error_id: string;
  batch_id: string;
  column_name: string;
  raw_message: string;
  friendly_title: string;
  friendly_explanation: string;
  suggested_action: string;
  category: string;
  category_key: string;
  severity: 'critical' | 'warning' | 'info';
  entity: string;
  created_at: string;
}

export interface GroupedIssue {
  group_key: string;
  category: string;
  category_key: string;
  severity: 'critical' | 'warning' | 'info';
  friendly_title: string;
  friendly_explanation: string;
  suggested_action: string;
  entity: string;
  affected_count: number;
  latest_seen?: string;
  sample_raw?: string;
  batch_id?: string;
}

export interface BatchOption {
  batch_id: string;
  label: string;
  status: string;
  created_at?: string;
}

interface UploadErrorViewerProps {
  initialBatchId?: string;
  refreshTrigger?: number;
  onRefreshRequested?: () => void;
}

export default function UploadErrorViewer({ initialBatchId, refreshTrigger = 0, onRefreshRequested }: UploadErrorViewerProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [fetchFailed, setFetchFailed] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<'grouped' | 'detailed'>('grouped');
  const [selectedBatch, setSelectedBatch] = useState<string>(initialBatchId || 'all');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedIssue, setExpandedIssue] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const [errors, setErrors] = useState<UploadErrorItem[]>([]);
  const [topIssues, setTopIssues] = useState<GroupedIssue[]>([]);
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({});
  const [availableBatches, setAvailableBatches] = useState<BatchOption[]>([]);
  const [totalErrors, setTotalErrors] = useState<number>(0);

  // Sync initialBatchId if passed from parent
  useEffect(() => {
    if (initialBatchId && initialBatchId !== selectedBatch) {
      setSelectedBatch(initialBatchId);
      setSelectedCategory('all');
      setSearchQuery('');
    }
  }, [initialBatchId]);

  const fetchErrors = async () => {
    setLoading(true);
    setFetchFailed(false);
    try {
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      let url = `${API_BASE_URL}/uploads/errors?limit=500`;
      if (selectedBatch && selectedBatch !== 'all') {
        url += `&batch_id=${encodeURIComponent(selectedBatch)}`;
      }
      if (selectedCategory && selectedCategory !== 'all') {
        url += `&category=${encodeURIComponent(selectedCategory)}`;
      }

      const res = await fetch(url, { headers });
      if (res.ok) {
        const data = await res.json();
        setErrors(data.errors || []);
        setTopIssues(data.top_issues || []);
        setCategoryCounts(data.category_counts || {});
        setAvailableBatches(data.available_batches || []);
        setTotalErrors(data.total_errors || 0);
      } else {
        console.warn('Failed to fetch upload errors, status:', res.status);
        setFetchFailed(true);
      }
    } catch (err) {
      console.error('Error loading upload errors:', err);
      setFetchFailed(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchErrors();
  }, [selectedBatch, selectedCategory, refreshTrigger]);

  // Filtered lists based on search query
  const filteredIssues = useMemo(() => {
    if (!searchQuery.trim()) return topIssues;
    const q = searchQuery.toLowerCase();
    return topIssues.filter(issue => 
      issue.friendly_title.toLowerCase().includes(q) ||
      issue.friendly_explanation.toLowerCase().includes(q) ||
      issue.suggested_action.toLowerCase().includes(q) ||
      issue.entity.toLowerCase().includes(q) ||
      (issue.sample_raw && issue.sample_raw.toLowerCase().includes(q))
    );
  }, [topIssues, searchQuery]);

  const filteredErrors = useMemo(() => {
    if (!searchQuery.trim()) return errors;
    const q = searchQuery.toLowerCase();
    return errors.filter(err => 
      err.friendly_title.toLowerCase().includes(q) ||
      err.friendly_explanation.toLowerCase().includes(q) ||
      err.column_name.toLowerCase().includes(q) ||
      err.raw_message.toLowerCase().includes(q) ||
      err.entity.toLowerCase().includes(q)
    );
  }, [errors, searchQuery]);

  const handleExportCSV = () => {
    if (errors.length === 0) return;
    const headers = ['Error ID', 'Batch ID', 'Category', 'Entity / Column', 'Friendly Title', 'Explanation', 'Suggested Action', 'Raw Error Message', 'Date'];
    const rows = errors.map(e => [
      `"${e.error_id}"`,
      `"${e.batch_id}"`,
      `"${e.category}"`,
      `"${e.column_name || e.entity}"`,
      `"${e.friendly_title.replace(/"/g, '""')}"`,
      `"${e.friendly_explanation.replace(/"/g, '""')}"`,
      `"${e.suggested_action.replace(/"/g, '""')}"`,
      `"${e.raw_message.replace(/"/g, '""')}"`,
      `"${e.created_at || ''}"`
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `rll_upload_errors_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleCopySummary = () => {
    if (topIssues.length === 0) return;
    const lines = [
      `RLL Ingestion Diagnostics Summary (${new Date().toLocaleString()})`,
      `Total Errors: ${totalErrors}`,
      '----------------------------------------',
      ...topIssues.map((iss, i) => `${i + 1}. [${iss.category}] ${iss.friendly_title}\n   - Affected Rows: ${iss.affected_count}\n   - Impact: ${iss.friendly_explanation}\n   - Action: ${iss.suggested_action}`)
    ];
    navigator.clipboard.writeText(lines.join('\n\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const getCategoryBadgeClass = (category: string) => {
    switch (category) {
      case 'Master Data Mapping':
        return 'bg-amber-50 text-amber-800 border-amber-200';
      case 'System & Network':
        return 'bg-blue-50 text-blue-800 border-blue-200';
      case 'Database Insertion':
        return 'bg-rose-50 text-rose-800 border-rose-200';
      case 'File Validation':
        return 'bg-purple-50 text-purple-800 border-purple-200';
      default:
        return 'bg-slate-50 text-slate-700 border-slate-200';
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'Master Data Mapping':
        return <HelpCircle className="w-4 h-4 text-amber-600 shrink-0" />;
      case 'System & Network':
        return <WifiOff className="w-4 h-4 text-blue-600 shrink-0" />;
      case 'Database Insertion':
        return <Database className="w-4 h-4 text-rose-600 shrink-0" />;
      case 'File Validation':
        return <FileSpreadsheet className="w-4 h-4 text-purple-600 shrink-0" />;
      default:
        return <AlertTriangle className="w-4 h-4 text-slate-600 shrink-0" />;
    }
  };

  return (
    <div id="unified-error-section" className="w-full bg-white rounded-2xl border border-slate-200/80 shadow-2xs p-6 transition-all duration-200">
      {/* Header Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-6 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-200 text-amber-700 flex items-center justify-center shadow-2xs">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 tracking-tight flex items-center gap-2">
                Ingestion Diagnostics & Error Center
                {totalErrors > 0 && (
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-extrabold bg-amber-100 text-amber-800 border border-amber-300">
                    {totalErrors.toLocaleString()} Issues Detected
                  </span>
                )}
              </h2>
              <p className="text-xs text-slate-500 mt-0.5 font-medium">
                Unified, user-friendly diagnostics and automated recommendations for file ingestion issues.
              </p>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Batch Selector Dropdown */}
          {availableBatches.length > 0 && (
            <div className="relative">
              <select
                value={selectedBatch}
                onChange={(e) => {
                  setSelectedBatch(e.target.value);
                  setSelectedCategory('all');
                  setSearchQuery('');
                }}
                className="text-xs font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-[#0D3B8E]/20 transition-all cursor-pointer appearance-none"
              >
                <option value="all">All Recent Ingestions</option>
                {availableBatches.map(b => (
                  <option key={b.batch_id} value={b.batch_id}>
                    {b.label}
                  </option>
                ))}
              </select>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          )}

          {/* Copy Summary */}
          <button
            onClick={handleCopySummary}
            disabled={totalErrors === 0}
            className="flex items-center gap-1.5 px-3 py-2 bg-slate-50 hover:bg-slate-100 text-slate-700 disabled:opacity-40 disabled:cursor-not-allowed border border-slate-200 rounded-xl text-xs font-bold transition-all cursor-pointer shadow-2xs"
            title="Copy human-readable summary to clipboard"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-slate-500" />}
            <span>{copied ? 'Copied!' : 'Copy Summary'}</span>
          </button>

          {/* Export CSV */}
          <button
            onClick={handleExportCSV}
            disabled={totalErrors === 0}
            className="flex items-center gap-1.5 px-3 py-2 bg-[#0D3B8E] hover:bg-[#0A2F73] text-white disabled:opacity-40 disabled:cursor-not-allowed rounded-xl text-xs font-bold transition-all cursor-pointer shadow-2xs shadow-[#0D3B8E]/10"
            title="Export error log to CSV"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV</span>
          </button>

          {/* Refresh */}
          <button
            onClick={() => {
              fetchErrors();
              if (onRefreshRequested) onRefreshRequested();
            }}
            disabled={loading}
            className="p-2 bg-slate-50 hover:bg-slate-100 text-slate-600 border border-slate-200 rounded-xl transition-all cursor-pointer"
            title="Refresh diagnostics"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#0D3B8E]' : ''}`} />
          </button>
        </div>
      </div>

      {/* Category Pills & View Switcher */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mt-5">
        {/* Category Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setSelectedCategory('all')}
            className={`px-3 py-1 rounded-full text-xs font-bold transition-all cursor-pointer ${
              selectedCategory === 'all'
                ? 'bg-slate-900 text-white shadow-2xs'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            All Issues ({totalErrors})
          </button>

          {Object.entries(categoryCounts).map(([cat, count]) => {
            if (count === 0 && selectedCategory !== cat) return null;
            const isSelected = selectedCategory === cat;
            return (
              <button
                key={cat}
                onClick={() => setSelectedCategory(isSelected ? 'all' : cat)}
                className={`px-3 py-1 rounded-full text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                  isSelected
                    ? 'bg-[#0D3B8E] text-white shadow-2xs'
                    : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border border-slate-200/80'
                }`}
              >
                <span>{cat}</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-extrabold ${
                  isSelected ? 'bg-white/20 text-white' : 'bg-slate-200/70 text-slate-600'
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* View Toggle: Grouped Summary vs Detailed Log */}
        <div className="flex items-center bg-slate-100 p-1 rounded-xl shrink-0 self-start md:self-auto">
          <button
            onClick={() => setViewMode('grouped')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              viewMode === 'grouped'
                ? 'bg-white text-[#0D3B8E] shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Grouped Summary</span>
          </button>
          <button
            onClick={() => setViewMode('detailed')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              viewMode === 'detailed'
                ? 'bg-white text-[#0D3B8E] shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <ListFilter className="w-3.5 h-3.5" />
            <span>Detailed Log</span>
          </button>
        </div>
      </div>

      {/* Search Bar */}
      <div className="relative mt-4">
        <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search issues by keyword, unmapped entity, column name, or description..."
          className="w-full text-xs font-medium text-slate-800 bg-slate-50/70 border border-slate-200/80 rounded-xl pl-9 pr-4 py-2.5 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0D3B8E]/20 transition-all placeholder:text-slate-400"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-600 font-bold px-1"
          >
            Clear
          </button>
        )}
      </div>

      {/* Content Area */}
      <div className="mt-5">
        {loading ? (
          <div className="py-14 flex flex-col items-center justify-center text-center">
            <RefreshCw className="w-7 h-7 text-[#0D3B8E] animate-spin mb-3" />
            <p className="text-xs font-bold text-slate-700">Analyzing Ingestion Diagnostics...</p>
            <p className="text-[11px] text-slate-400 mt-0.5">Fetching and categorizing validation records from backend</p>
          </div>
        ) : fetchFailed ? (
          <div className="py-12 px-6 rounded-2xl bg-amber-50/70 border border-amber-200 flex flex-col items-center justify-center text-center">
            <AlertTriangle className="w-6 h-6 text-amber-600 mb-2" />
            <h3 className="text-sm font-bold text-amber-950">Diagnostics Server Notice</h3>
            <p className="text-xs text-amber-800 mt-1 max-w-md font-medium">
              Could not fetch diagnostic logs from backend server. Please verify your connection or click refresh.
            </p>
            <button 
              onClick={fetchErrors}
              className="mt-3 px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-xs font-bold transition-all cursor-pointer"
            >
              Retry Loading Diagnostics
            </button>
          </div>
        ) : totalErrors === 0 ? (
          /* Healthy / Zero Error State or Interrupted Batch State */
          (() => {
            const currentBatchObj = availableBatches.find(b => String(b.batch_id) === String(selectedBatch));
            const isSelectedBatchFailed = currentBatchObj && ['failed', 'interrupted', 'error'].includes((currentBatchObj.status || '').toLowerCase());
            
            if (isSelectedBatchFailed) {
              return (
                <div className="py-12 px-6 rounded-2xl bg-rose-50/70 border border-rose-200 flex flex-col items-center justify-center text-center">
                  <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mb-3 shadow-2xs">
                    <AlertCircle className="w-6 h-6" />
                  </div>
                  <h3 className="text-sm font-bold text-rose-950">Ingestion Execution Interrupted / Failed</h3>
                  <p className="text-xs text-rose-800 mt-1 max-w-md font-medium">
                    The selected upload batch encountered an error or was interrupted during execution. All partial records were safely rolled back to 0.
                  </p>
                  <button 
                    onClick={fetchErrors}
                    className="mt-3 px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition-all cursor-pointer"
                  >
                    Reload Diagnostic Log
                  </button>
                </div>
              );
            }

            return (
              <div className="py-12 px-6 rounded-2xl bg-emerald-50/50 border border-emerald-200/80 flex flex-col items-center justify-center text-center">
                <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mb-3 shadow-2xs">
                  <CheckCircle className="w-6 h-6" />
                </div>
                <h3 className="text-sm font-bold text-emerald-950">Zero Ingestion Errors</h3>
                <p className="text-xs text-emerald-700 mt-1 max-w-md font-medium">
                  All records for the selected batch have been validated and inserted with 100% data integrity.
                </p>
              </div>
            );
          })()
        ) : viewMode === 'grouped' ? (
          /* Grouped Summary View */
          <div className="space-y-3.5">
            {filteredIssues.length === 0 ? (
              <div className="py-10 px-6 rounded-2xl bg-slate-50 border border-slate-200/80 text-center">
                <p className="text-xs font-bold text-slate-700">No issues match the active category/search filter</p>
                {selectedCategory !== 'all' && (
                  <button
                    onClick={() => setSelectedCategory('all')}
                    className="mt-2 text-xs font-bold text-[#0D3B8E] hover:underline cursor-pointer"
                  >
                    View All {totalErrors} Issues Across Batch →
                  </button>
                )}
              </div>
            ) : (
              filteredIssues.map((issue) => {
                const isExpanded = expandedIssue === issue.group_key;
                return (
                  <div
                    key={issue.group_key}
                    className="border border-slate-200/80 rounded-xl bg-white hover:border-slate-300 transition-all overflow-hidden shadow-2xs"
                  >
                    {/* Header Item */}
                    <div 
                      onClick={() => setExpandedIssue(isExpanded ? null : issue.group_key)}
                      className="p-4 flex items-start justify-between gap-4 cursor-pointer select-none bg-slate-50/30 hover:bg-slate-50/70 transition-colors"
                    >
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 p-1.5 rounded-lg bg-white border border-slate-200/80 shadow-2xs">
                          {getCategoryIcon(issue.category)}
                        </div>
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h4 className="text-xs font-bold text-slate-900">{issue.friendly_title}</h4>
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${getCategoryBadgeClass(issue.category)}`}>
                              {issue.category}
                            </span>
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-slate-100 text-slate-700">
                              {issue.affected_count.toLocaleString()} {issue.affected_count === 1 ? 'row' : 'rows'} affected
                            </span>
                          </div>
                          <p className="text-xs text-slate-600 mt-1 font-medium leading-relaxed">
                            {issue.friendly_explanation}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0 pt-1">
                        <span className="text-[11px] font-bold text-[#0D3B8E] hover:underline flex items-center gap-1">
                          {isExpanded ? 'Hide Details' : 'View Action'}
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </span>
                      </div>
                    </div>

                    {/* Actionable Solution & Raw Details (Expanded) */}
                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="border-t border-slate-100 p-4 bg-slate-50/40 space-y-3 text-xs"
                        >
                          {/* Recommended Action Box */}
                          <div className="p-3 bg-amber-50/80 border border-amber-200 rounded-xl flex items-start gap-2.5">
                            <Lightbulb className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                            <div>
                              <p className="text-[10px] font-extrabold text-amber-900 uppercase tracking-wider">
                                How to Resolve
                              </p>
                              <p className="text-xs text-amber-800 font-semibold mt-0.5 leading-relaxed">
                                {issue.suggested_action}
                              </p>
                            </div>
                          </div>

                          {/* Technical Breakdown */}
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5 pt-1">
                            <div className="p-2.5 bg-white border border-slate-200/80 rounded-xl">
                              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Impacted Entity</span>
                              <span className="font-semibold text-slate-800 mt-0.5 block">{issue.entity}</span>
                            </div>
                            <div className="p-2.5 bg-white border border-slate-200/80 rounded-xl">
                              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Affected Rows</span>
                              <span className="font-semibold text-slate-800 mt-0.5 block">{issue.affected_count.toLocaleString()} occurrences</span>
                            </div>
                            <div className="p-2.5 bg-white border border-slate-200/80 rounded-xl">
                              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Latest Occurrence</span>
                              <span className="font-semibold text-slate-800 mt-0.5 block flex items-center gap-1">
                                <Clock className="w-3 h-3 text-slate-400" />
                                {issue.latest_seen ? new Date(issue.latest_seen).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'Recent'}
                              </span>
                            </div>
                          </div>

                          {/* Sample Raw Technical Error Toggle */}
                          {issue.sample_raw && (
                            <div className="pt-1">
                              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                                Raw Technical Detail:
                              </span>
                              <div className="p-2.5 bg-slate-900 text-slate-200 font-mono text-[11px] rounded-lg overflow-x-auto select-all">
                                {issue.sample_raw}
                              </div>
                            </div>
                          )}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })
            )}
          </div>
        ) : (
          /* Detailed Row-by-Row Log View */
          <div className="border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-2xs">
            <div className="overflow-x-auto max-h-96">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold text-[10px] uppercase tracking-wider">
                    <th className="py-3 px-4">Row #</th>
                    <th className="py-3 px-4">Category</th>
                    <th className="py-3 px-4">Entity / Column</th>
                    <th className="py-3 px-4">Issue Description & Action Required</th>
                    <th className="py-3 px-4">Batch ID</th>
                    <th className="py-3 px-4 text-right">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredErrors.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-slate-400 font-medium">
                        No errors match the current filter.
                      </td>
                    </tr>
                  ) : (
                    filteredErrors.slice(0, 150).map((err) => {
                      const rowNum = err.excel_row_number || (err.raw_message && err.raw_message.match(/\[Row\s*#?(\d+)\]/i)?.[1]) || '—';
                      const actionText = err.suggested_action || err.resolution;
                      return (
                        <tr key={err.error_id} className="hover:bg-slate-50/60 transition-colors">
                          <td className="py-3 px-4 whitespace-nowrap">
                            <span className="px-2 py-0.5 rounded text-[11px] font-mono font-extrabold bg-amber-100 text-amber-900 border border-amber-300">
                              Row #{rowNum}
                            </span>
                          </td>
                          <td className="py-3 px-4 whitespace-nowrap">
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${getCategoryBadgeClass(err.category)}`}>
                              {getCategoryIcon(err.category)}
                              <span>{err.category}</span>
                            </span>
                          </td>
                          <td className="py-3 px-4 whitespace-nowrap">
                            <p className="font-bold text-slate-900">{err.entity || err.column_name}</p>
                            <p className="text-[10px] text-slate-400 font-mono">col: {err.column_name || 'raw'}</p>
                          </td>
                          <td className="py-3 px-4 max-w-lg">
                            <p className="font-bold text-slate-900 text-xs">{err.friendly_title}</p>
                            <p className="text-[11px] text-slate-600 mt-0.5">{err.friendly_explanation}</p>
                            
                            {actionText && (
                              <div className="mt-1.5 p-2 bg-amber-50/90 border border-amber-200 rounded-lg text-[11px] text-amber-900 font-medium flex items-start gap-1.5">
                                <Lightbulb className="w-3.5 h-3.5 text-amber-700 shrink-0 mt-0.5" />
                                <span><strong>Action Needed:</strong> {actionText}</span>
                              </div>
                            )}

                            {err.raw_message && (
                              <details className="mt-1 text-[10px] text-slate-400">
                                <summary className="cursor-pointer hover:text-slate-600 font-medium">Show raw message</summary>
                                <pre className="mt-1 p-1.5 bg-slate-100 text-slate-700 rounded text-[10px] whitespace-pre-wrap font-mono">
                                  {err.raw_message}
                                </pre>
                              </details>
                            )}
                          </td>
                          <td className="py-3 px-4 text-slate-500 font-mono text-[11px] whitespace-nowrap">
                            {err.batch_id ? `#${err.batch_id.slice(0, 8)}` : '—'}
                          </td>
                          <td className="py-3 px-4 text-right text-slate-400 whitespace-nowrap font-medium text-[11px]">
                            {err.created_at ? new Date(err.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : '—'}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
            {filteredErrors.length > 150 && (
              <div className="p-2.5 bg-slate-50 border-t border-slate-200 text-center text-[11px] font-semibold text-slate-500">
                Showing first 150 errors of {filteredErrors.length.toLocaleString()}. Use CSV export for full dataset.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
