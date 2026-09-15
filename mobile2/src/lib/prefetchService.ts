import { logger } from './logger';
import { FastStorage } from './storage';
import {
  getAuthToken,
  fetchMobileHeadquarters,
  fetchMobileCompanies,
  fetchMobileSales,
  fetchGroupLicensees,
  fetchGroupBrands,
  fetchCompanyBrands,
} from './api';

let _isPrefetching = false;
let _prefetchedHqs = new Set<string>();

/**
 * Full Batch Background Prefetch Worker.
 * Concurrently prefetches analytics data for ALL registered Headquarters across active periods
 * without blocking UI threads or interrupting user experience.
 */
export async function preloadAllHeadquartersData(forceRefresh: boolean = false): Promise<void> {
  if (_isPrefetching && !forceRefresh) {
    logger.info('preloadAllHeadquartersData: Prefetch worker already running. Skipping.');
    return;
  }

  const token = await getAuthToken();
  if (!token) {
    logger.info('preloadAllHeadquartersData: No active auth session. Skipping prefetch.');
    return;
  }

  _isPrefetching = true;
  logger.info('🚀 [PREFETCH_WORKER_START] Initializing background batch prefetch for all Headquarters...');

  try {
    // 1. Fetch registered headquarters list
    const hqs = await fetchMobileHeadquarters();
    if (!hqs || !Array.isArray(hqs) || hqs.length === 0) {
      logger.warn('preloadAllHeadquartersData: No registered headquarters found.');
      return;
    }

    const hqList = hqs.filter((h: string) => h && h !== 'All Headquarters');
    logger.info(`preloadAllHeadquartersData: Found ${hqList.length} distinct Headquarters to prefetch.`);

    const periods: ('Daily' | 'MTD' | 'YTD')[] = ['MTD', 'Daily', 'YTD'];

    // 2. Non-blocking background worker queue
    for (const hq of hqList) {
      // Abort immediately if session was revoked, expired, or logged out
      const currentToken = await getAuthToken();
      if (!currentToken) {
        logger.info('preloadAllHeadquartersData: Auth session expired/cleared. Stopping prefetch worker.');
        break;
      }

      // Yield execution to main thread to ensure 60fps UI responsiveness
      await new Promise((resolve) => setTimeout(() => resolve(undefined), 80));

      for (const period of periods) {
        try {
          const compKey = `companies_${hq}_${period}_latest`;
          const existing = FastStorage.getObject(compKey);

          if (!existing || forceRefresh) {
            const compRes = await fetchMobileCompanies(period, '', hq, true);
            if (compRes && Array.isArray(compRes.companies) && compRes.companies.length > 0) {
              FastStorage.setObject(compKey, compRes);
            }
          }
        } catch (e_hq) {
          logger.warn(`preloadAllHeadquartersData: Error prefetching HQ '${hq}' (${period}): ${e_hq}`);
        }
      }
      _prefetchedHqs.add(hq.toLowerCase().trim());
    }

    logger.info(`✅ [PREFETCH_WORKER_COMPLETE] Successfully prefetched ${_prefetchedHqs.size} Headquarters silently into FastStorage.`);
  } catch (err) {
    logger.error('preloadAllHeadquartersData: Exception in prefetch worker:', err);
  } finally {
    _isPrefetching = false;
  }
}

/**
 * Checks if a specific HQ's data has been pre-fetched into FastStorage.
 */
export function isHqPrefetched(hqName: string): boolean {
  if (!hqName || hqName === 'All Headquarters') return true;
  return _prefetchedHqs.has(hqName.toLowerCase().trim());
}

/**
 * Predictive background prefetching for top Level 1 cards (Groups or Companies).
 * Silently pre-populates Level 2 child items in FastStorage during user idle time.
 */
export async function prefetchTopCascadingCards(
  items: any[],
  type: 'groups' | 'companies',
  period: string = 'Daily',
  dateFrom?: string,
  dateTo?: string,
  selectedHq?: string
): Promise<void> {
  if (!items || items.length === 0) return;
  const token = await getAuthToken();
  if (!token) return;

  const topItems = items.slice(0, 3);
  logger.info(`🚀 [PREFETCH_CASCADING] Starting idle prefetch for top ${topItems.length} ${type}...`);

  for (const item of topItems) {
    // Yield to main thread
    await new Promise((resolve) => setTimeout(() => resolve(undefined), 120));

    try {
      if (type === 'groups') {
        const groupId = item.group_id;
        if (!groupId) continue;

        // Prefetch Group Licensees & Brands
        await fetchGroupLicensees(groupId, dateFrom, dateTo, period, selectedHq, false, true);
        await fetchGroupBrands(groupId, dateFrom, dateTo, period, selectedHq, false, true);
      } else if (type === 'companies') {
        const companyId = item.company_id;
        if (!companyId) continue;

        // Prefetch Company Brands
        await fetchCompanyBrands(companyId, dateFrom, dateTo, selectedHq, false, true);
      }
    } catch (e) {
      logger.warn(`prefetchTopCascadingCards: Silent error prefetching ${type} item:`, e);
    }
  }
}

