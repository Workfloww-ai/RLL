/**
 * Mobile Chatbot API Client.
 * Connects frontend chatbot UI components to backend chatbot endpoints.
 */

import { apiFetch } from '../../lib/api';

export async function sendChatMessage(
  message: string,
  period: string = 'Daily',
  selectedHq: string = 'All Headquarters',
  dateFrom?: string,
  dateTo?: string
) {
  const res = await apiFetch('/chatbot/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      period,
      selected_hq: selectedHq,
      date_from: dateFrom,
      date_to: dateTo,
    }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Server returned error ${res.status}`);
  }
  return res.json();
}

export async function fetchSuggestedPrompts(): Promise<string[]> {
  try {
    const res = await apiFetch('/chatbot/suggested-prompts');
    if (res.ok) {
      const data = await res.json();
      return data.prompts || [];
    }
  } catch (e) {
    // Fallback prompt pills
  }
  return [
    'Summarise total sales for Daily',
    'What are the top 5 selling brands?',
    'Show company market share breakdown',
    'Compare MTD sales vs last month',
    'Which brands are growing the fastest?',
  ];
}
