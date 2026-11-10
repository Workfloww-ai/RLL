import posthog from 'posthog-js';

let isPosthogInitialized = false;

const DEFAULT_POSTHOG_KEY = 'phc_tbxfduLcYNJFSPGMfmkQeHVVrK38ioq2UyMkZ8s86dxJ';
const DEFAULT_POSTHOG_HOST = 'https://us.i.posthog.com';

export function initPosthog(token?: string, host?: string) {
  if (isPosthogInitialized) return;
  if (typeof window === 'undefined') return;

  const phToken = token || (import.meta as any).env?.VITE_POSTHOG_KEY || DEFAULT_POSTHOG_KEY;
  const phHost = host || (import.meta as any).env?.VITE_POSTHOG_HOST || DEFAULT_POSTHOG_HOST;

  if (!phToken || typeof phToken !== 'string' || phToken.trim() === '' || phToken.includes('your_project_api_key')) {
    return;
  }

  try {
    posthog.init(phToken.trim(), {
      api_host: phHost.trim(),
      person_profiles: 'identified_only', // Conserves free tier quota by only profiling identified users
      autocapture: true, // Automatically captures all user clicks, buttons, tabs, inputs, and links!
      capture_pageview: true, // Tracks URL and page navigation
      capture_pageleave: true,
      disable_session_recording: false, // Session Replay: video recordings of user clicks & actions (5,000/mo FREE)
      session_recording: {
        maskAllInputs: false,
        maskInputOptions: {
          password: true, // Masks sensitive password inputs
        },
      },
    });
    isPosthogInitialized = true;
    console.log('⚡ PostHog Web Client initialized with Autocapture & Session Replay');

    // Auto-identify if user is already saved in localStorage
    try {
      const storedUserStr = localStorage.getItem('user');
      if (storedUserStr) {
        const u = JSON.parse(storedUserStr);
        if (u && (u.user_id || u.email)) {
          identifyWebUser(u);
        }
      }
    } catch {}
  } catch (err) {
    console.warn('Failed to initialize PostHog on Web:', err);
  }
}

export function identifyWebUser(user: {
  user_id?: string | number;
  email?: string;
  first_name?: string;
  last_name?: string;
  role_name?: string;
  role?: string;
  tenant_id?: string;
}) {
  if (!isPosthogInitialized || !user) return;
  const uid = user.user_id ? String(user.user_id) : (user.email || '');
  if (!uid) return;

  try {
    const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.email || uid;
    posthog.identify(uid, {
      email: user.email,
      name: fullName,
      role: user.role || user.role_name,
      tenant_id: user.tenant_id,
      client_type: 'web',
    });
  } catch (err) {
    console.warn('PostHog user identification notice:', err);
  }
}

export function trackUserClick(actionName: string, properties?: Record<string, any>) {
  if (!isPosthogInitialized) return;
  try {
    posthog.capture(actionName, {
      ...properties,
      $current_url: window.location.href,
    });
  } catch {}
}

export function resetWebUser() {
  if (!isPosthogInitialized) return;
  try {
    posthog.reset();
  } catch {}
}

export { posthog };

