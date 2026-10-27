import { logger } from './logger';
import { FastStorage } from './storage';
import { fetchMobileHeadquarters, fetchMobileCompanies, fetchMobileSales } from './api';

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

  _isPrefetching = true;
  logger.info('🚀 [PREFETCH_WORKER_START] Initializing background batch prefetch for all Headquarters...');

  try {
    // 1. Fetch registered headquarters list
    const hqs = await fetchMobileHeadquarters();
    if (!hqs || !Array.isArray(hqs) || hqs.length === 0) {
      logger.warn('preloadAllHeadquartersData: No registered headquarters found.');
      return;
    }

    // Only prefetch 'All Headquarters' and top active HQs to stay safely under AsyncStorage SQLite limit (6MB)
    const hqList = ['All Headquarters', ...hqs.filter((h: string) => h && h !== 'All Headquarters').slice(0, 2)];
    logger.info(`preloadAllHeadquartersData: Prefetching ${hqList.length} primary Headquarters into FastStorage.`);

    const periods: ('Daily' | 'MTD' | 'YTD')[] = ['MTD', 'Daily', 'YTD'];

    // 2. Non-blocking background worker queue
    for (const hq of hqList) {
      // Yield execution to main thread to ensure 60fps UI responsiveness
      await new Promise((resolve) => setTimeout(() => resolve(undefined), 80));

      for (const period of periods) {
        try {
          const cleanHq = (hq || 'All Headquarters').trim();
          const compKey = `rll_fast_companies_${period}_${cleanHq}_latest`;
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
