import { API_BASE_URL } from '../config';

export interface LogErrorParams {
  source: 'frontend';
  error_message: string;
  stack_trace?: string;
  context?: Record<string, any>;
}

export const logErrorToBackend = async (params: LogErrorParams): Promise<void> => {
  try {
    const token = localStorage.getItem('token');
    
    // We intentionally don't await this to block the UI, it fires and forgets.
    fetch(`${API_BASE_URL}/system/log-error`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
      },
      body: JSON.stringify(params),
    }).catch(err => {
      // Suppress network errors from the logging endpoint itself to avoid infinite loops
      console.warn('Failed to send error log to backend:', err);
    });
  } catch (e) {
    console.warn('Error logger encountered an error:', e);
  }
};
