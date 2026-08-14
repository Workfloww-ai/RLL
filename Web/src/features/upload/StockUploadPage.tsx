import React from 'react';
import FileUpload from '../../components/FileUpload';

export default function StockUploadPage() {
  return (
    <div className="max-w-7xl w-full space-y-6">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-800">Sales Data Upload</h1>
        <p className="text-slate-500 mt-1 text-sm font-medium">Upload the latest sales data for real-time outlet visibility.</p>
      </div>

      <FileUpload 
        title=""
        instructions={[
          "Ensure column headers match exactly with the provided template.",
          "Accepted formats: .xlsx, .xls, .xlsb, .csv, .numbers.",
          "Maximum file size: 30MB.",
          "System handles duplicate removal automatically based on Timestamp."
        ]}
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
          <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Last Upload</h3>
          <p className="text-lg font-bold text-slate-800">Today, 08:30 AM</p>
          <p className="text-[10px] text-slate-400 font-medium uppercase mt-1">By Admin User</p>
        </div>
        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
          <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Records Processed</h3>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-lg font-bold text-slate-800">12,450</p>
            <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 text-[9px] font-bold rounded uppercase tracking-wider">Success</span>
          </div>
          <p className="text-[10px] text-slate-400 font-medium uppercase mt-1">99.8% Data Accuracy • Clean</p>
        </div>
        <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-200 border-l-4 border-l-emerald-500">
          <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">System Status</h3>
          <div className="flex items-center gap-2 mt-1">
            <span className="w-2.5 h-2.5 bg-emerald-500 rounded-full animate-pulse"></span>
            <p className="text-lg font-bold text-slate-800">Sync Active</p>
          </div>
          <p className="text-[10px] text-slate-400 font-medium uppercase mt-1">Dashboards updated</p>
        </div>
      </div>
    </div>
  );
}
