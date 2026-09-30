/**
 * Web Chatbot API Client.
 * Connects Web application chatbot UI components to backend chatbot endpoints.
 */

import { API_BASE_URL } from '../../config';

export async function sendChatMessage(message: string, period?: string, selectedHq?: string) {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API_BASE_URL}/chatbot/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, period, selected_hq: selectedHq }),
  });
  return res.json();
}
