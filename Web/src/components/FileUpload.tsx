import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle, X } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { FileUploadState } from '../types';

interface FileUploadProps {
  title: string;
  instructions: string[];
  accept?: string;
  onUploadComplete?: (fileName: string) => void;
}

export default function FileUpload({ title, instructions, accept = ".xlsx, .xls, .csv", onUploadComplete }: FileUploadProps) {
  const [uploadState, setUploadState] = useState<FileUploadState>({ status: 'idle', progress: 0 });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFile(e.target.files[0]);
    }
  };

  const processFile = (file: File) => {
    setUploadState({ status: 'uploading', progress: 0, fileName: file.name });
    
    // Simulate upload progress
    let progress = 0;
    const interval = setInterval(() => {
      progress += 10;
      setUploadState(prev => ({ ...prev, progress }));
      
      if (progress >= 100) {
        clearInterval(interval);
        setUploadState({ status: 'success', progress: 100, fileName: file.name });
        if (onUploadComplete) onUploadComplete(file.name);
      }
    }, 200);
  };

  const resetUpload = () => {
    setUploadState({ status: 'idle', progress: 0 });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
      <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col h-[320px]">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-800">{title}</h2>
          <span className="px-2 py-1 bg-green-50 text-green-700 text-[10px] font-bold rounded uppercase tracking-wider">Active</span>
        </div>

        <div 
          className={`border-2 border-dashed rounded-lg flex-1 flex flex-col items-center justify-center p-4 transition-colors cursor-pointer group ${
            uploadState.status === 'idle' ? 'border-slate-200 bg-slate-50 hover:bg-slate-100' : 
            uploadState.status === 'success' ? 'border-emerald-200 bg-emerald-50/50' :
            'border-slate-200 bg-slate-50'
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
                className="flex flex-col items-center"
              >
                <UploadCloud className="w-12 h-12 text-[#004B87]/40 group-hover:text-[#004B87] mb-3 transition-colors" />
                <p className="text-sm text-slate-600 font-semibold">Click to upload or drag Excel file</p>
                <p className="text-xs text-slate-400 mt-1">Accepted formats: {accept}</p>
              </motion.div>
            )}

            {uploadState.status === 'uploading' && (
              <motion.div 
                key="uploading"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center w-full max-w-md mx-auto"
              >
                <FileText size={32} className="text-[#004B87] mb-4 animate-pulse" />
                <p className="text-sm text-slate-700 font-bold mb-2">Uploading {uploadState.fileName}...</p>
                <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                  <motion.div 
                    className="h-full bg-[#004B87] rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${uploadState.progress}%` }}
                  />
                </div>
                <p className="text-slate-500 text-xs mt-2 font-medium">{uploadState.progress}%</p>
              </motion.div>
            )}

            {uploadState.status === 'success' && (
              <motion.div 
                key="success"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center w-full"
              >
                <div className="mt-4 w-full max-w-md flex items-center gap-3 p-3 bg-emerald-50 border border-emerald-100 rounded-lg">
                  <div className="w-6 h-6 bg-emerald-500 rounded-full flex items-center justify-center shrink-0">
                    <CheckCircle className="w-4 h-4 text-white" />
                  </div>
                  <div className="flex-1 text-left">
                    <p className="text-xs font-bold text-emerald-800">Sheet Successfully Uploaded</p>
                    <p className="text-[10px] text-emerald-600">{uploadState.fileName} processed.</p>
                  </div>
                </div>
                <button 
                  onClick={(e) => { e.stopPropagation(); resetUpload(); }}
                  className="mt-4 px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors text-xs font-bold"
                >
                  Upload Another File
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
        <button className="mt-6 w-full py-2.5 bg-slate-800 text-white rounded-lg text-sm font-bold flex items-center justify-center gap-2 hover:bg-slate-700 transition-colors">
          Download Template
        </button>
      </div>
    </div>
  );
}
