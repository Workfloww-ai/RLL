export type ViewState = 'stock' | 'territory' | 'headcount';

export interface FileUploadState {
  status: 'idle' | 'uploading' | 'processing' | 'success' | 'error';
  progress: number;
  fileName?: string;
  batchId?: number;
  statusMessage?: string;
  errorMessage?: string;
  importedRows?: number;
  failedRows?: number;
  duplicateRows?: number;
  processingTimeSeconds?: number;
  errorLogs?: string[];
}

export interface Territory {
  id: string;
  name: string;
  level: 'District' | 'District Office' | 'Depot';
  capacity: number; // max assignments
  assignedUsers: User[];
}

export interface User {
  id: string;
  name: string;
  role: 'Area Sales Manager' | 'Territory Executive' | 'Regional Supervisor';
  depotName: string;
  circleName: string;
  headquarters: string;
  reportingManager: string;
  isActive?: boolean;
  phoneNumber?: string;
}
