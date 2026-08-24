/// <reference types="vite/client" />

export const API_BASE_URL: string =
  ((import.meta as any).env?.VITE_API_URL as string) ||
  'https://rll-backend-414899512001.asia-south2.run.app/api/v1';
