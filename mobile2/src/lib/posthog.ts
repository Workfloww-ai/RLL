import { Platform } from 'react-native';
import { apiFetch } from './api';

const POSTHOG_API_KEY =
  (process.env as any)?.EXPO_PUBLIC_POSTHOG_API_KEY ||
  'phc_tbxfduLcYNJFSPGMfmkQeHVVrK38ioq2UyMkZ8s86dxJ';
const POSTHOG_HOST =
  (process.env as any)?.EXPO_PUBLIC_POSTHOG_HOST ||
  'https://us.i.posthog.com';

let _userContext: Record<string, any> = {};

export function setMobileUserContext(user: any) {
  if (!user) return;
  _userContext = {
    user_id: user.user_id ? String(user.user_id) : undefined,
    email: user.email,
    name: `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.email,
    role: user.role_name || user.role,
    company_name: user.company_name,
    depot_name: user.depot_name,
    tenant_id: user.tenant_id,
  };
}

export function clearMobileUserContext() {
  _userContext = {};
}

/**
 * Capture mobile user activity fire-and-forget (never blocks UI).
 * Sends directly to PostHog HTTP endpoint for instant delivery + backend fallback.
 */
export function trackMobileActivity(event: string, properties: Record<string, any> = {}) {
  try {
    const distinctId = _userContext.email || _userContext.user_id || 'anonymous_mobile_user';
    const mergedProps = {
      ...properties,
      ..._userContext,
      $lib: 'posthog-react-native',
      $os: Platform.OS,
      $os_version: String(Platform.Version),
      client_type: 'mobile',
      timestamp: new Date().toISOString(),
    };

    if (__DEV__) {
      console.log('📡 [PostHog Mobile Event]', event, JSON.stringify(properties));
    }

    // 1. Direct PostHog HTTP capture (instant, zero backend latency)
    fetch(`${POSTHOG_HOST.replace(/\/+$/, '')}/capture/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: POSTHOG_API_KEY,
        event,
        distinct_id: distinctId,
        properties: mergedProps,
      }),
    }).catch(() => {});

    // 2. Also forward to backend /system/track-activity
    apiFetch('/system/track-activity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event,
        client_type: 'mobile',
        distinct_id: distinctId,
        properties: mergedProps,
      }),
    }).catch(() => {});
  } catch {
    // Fail silent
  }
}

export function trackScreenView(screenName: string, properties: Record<string, any> = {}) {
  trackMobileActivity('mobile_screen_view', {
    screen_name: screenName,
    ...properties,
  });
}

export function trackFilterChange(filterType: string, value: any, extraProps: Record<string, any> = {}) {
  trackMobileActivity('mobile_filter_changed', {
    filter_type: filterType,
    value,
    ...extraProps,
  });
}

export function trackCardClick(cardType: string, cardName: string, extraProps: Record<string, any> = {}) {
  trackMobileActivity('mobile_card_clicked', {
    card_type: cardType,
    card_name: cardName,
    ...extraProps,
  });
}
