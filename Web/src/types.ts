export type ViewState = 'stock' | 'territory' | 'headcount' | 'roles' | 'settings';

export interface FileUploadState {
  status: 'idle' | 'uploading' | 'processing' | 'success' | 'error';
  progress: number;
  fileName?: string;
  batchId?: number | string;
  statusMessage?: string;
  errorMessage?: string;
  importedRows?: number;
  failedRows?: number;
  duplicateRows?: number;
  processingTimeSeconds?: number;
  uploadStartTime?: string;
  elapsedSeconds?: number;
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
  email?: string;
  role: 'ASE' | 'TSM' | 'Regional Supervisor' | string;
  depotName: string;
  circleName: string;
  headquarters: string;
  reportingManager: string;
  isActive?: boolean;
  phoneNumber?: string;
}
