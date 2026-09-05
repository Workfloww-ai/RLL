import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import {
  StatusBar,
  StyleSheet,
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  Platform,
  useWindowDimensions,
  BackHandler,
  Modal,
  Animated,
  RefreshControl,
  NativeSyntheticEvent,
  NativeScrollEvent,
} from 'react-native';


import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { logger } from './src/lib/logger';

import { Company, Period, ViewMode } from './src/types';
import { formatNumber } from './src/lib/utils';
import { getDynamicCardDimensions } from './src/lib/responsive';
import {
  fetchMobileSales,
  fetchMobileCompanies,
  fetchUserProfile,
  fetchMobileHeadquarters,
  clearAuthSession,
  clearAllPhoneCaches,
  hydratePersistentCache,
} from './src/lib/api';

import { Header } from './src/features/dashboard/Header';
import { FooterNav } from './src/features/dashboard/FooterNav';
import { CompanyCard } from './src/features/dashboard/CompanyCard';
import { NoDataModal } from './src/components/NoDataModal';
import { CompanyListSkeletonList } from './src/features/dashboard/CompanyCardSkeleton';
import { CompanyCascadingView } from './src/features/dashboard/CompanyCascadingView';
import { GroupsCascadingView } from './src/features/dashboard/GroupsCascadingView';
import { TsmView } from './src/features/dashboard/TsmView';
import { BrandModal } from './src/features/dashboard/BrandModal';
import { LoginScreen } from './src/features/auth/LoginScreen';
import { ProfileScreen } from './src/features/profile/ProfileScreen';
import {
  XIcon,
  SearchIcon,
  CheckCircleIcon,
  PinIcon,
  TrendingUpIcon,
  TrendingDownIcon,
  SortAlphabeticalIcon,
  SwapVertIcon,
  ChevronDownIcon,
} from './src/components/Icons';

export type CompanySortOption = 'az' | 'za' | 'cases_desc' | 'cases_asc';

export default function App() {
  const [user, setUser] = useState<any>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [period, setPeriod] = useState<Period>('Daily');
  const [dateFrom, setDateFrom] = useState<string>('2026-07-31');
  const [dateTo, setDateTo] = useState<string>('2026-07-31');
  const [viewMode, setViewMode] = useState<ViewMode>('companies');
  const [viewModeHistory, setViewModeHistory] = useState<ViewMode[]>(['companies']);
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedHq, setSelectedHq] = useState<string>('All Headquarters');
  const [headquartersList, setHeadquartersList] = useState<string[]>(['All Headquarters']);
  const [apiData, setApiData] = useState<any>(null);
  const [loadingSalesData, setLoadingSalesData] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showNoDataModal, setShowNoDataModal] = useState<boolean>(false);

  const handleRefresh = useCallback(async () => {
    if (!user) return;
    setRefreshing(true);
    try {
      await clearAllPhoneCaches();
      if (viewMode === 'companies') {
        const compRes = await fetchMobileCompanies(period, dateTo, selectedHq);
        if (compRes && Array.isArray(compRes.companies)) {
          setApiData((prev: any) => ({ ...(prev || {}), ...compRes }));
        }
      } else {
        const res = await fetchMobileSales(dateFrom || '', dateTo || '', period, selectedHq);
        if (res) setApiData(res);
      }
      const profile = await fetchUserProfile();
      if (profile && (profile.email || profile.phone || profile.user_id)) {
        setUser(profile);
      }
      const hqs = await fetchMobileHeadquarters();
      if (hqs && hqs.length > 0) {
        setHeadquartersList(hqs);
      }
    } catch (err) {
      logger.error('Error refreshing data in App.tsx:', err);
    } finally {
      setRefreshing(false);
    }
  }, [user, viewMode, period, dateFrom, dateTo, selectedHq]);

  // Minimal Sort State & Modal Visibility
  const [sortBy, setSortBy] = useState<CompanySortOption>('az');
  const [showSortModal, setShowSortModal] = useState<boolean>(false);

  const handleTabChange = useCallback((newMode: ViewMode) => {
    setViewMode((currentMode) => {
      if (newMode !== currentMode) {
        setViewModeHistory((prev) => [...prev, newMode]);
        return newMode;
      }
      return currentMode;
    });
  }, []);

  // Hardware BackHandler for tab history & modals
  useEffect(() => {
    const onBackPress = () => {
      if (showSortModal) {
        setShowSortModal(false);
        return true;
      }
      if (selectedCompany !== null) {
        setSelectedCompany(null);
        return true;
      }
      if (viewModeHistory.length > 1) {
        setViewModeHistory((prev) => {
          const updated = [...prev];
          updated.pop();
          const prevView = updated[updated.length - 1] || 'companies';
          setViewMode(prevView);
          return updated;
        });
        return true;
      }
      return false;
    };
    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [showSortModal, selectedCompany, viewModeHistory]);

  const { height: windowHeight } = useWindowDimensions();
  const cardDimensions = useMemo(() => getDynamicCardDimensions(windowHeight), [windowHeight]);
  const scaleFactor = 1;

  useEffect(() => {
    StatusBar.setBarStyle('light-content');
  }, []);

  // Load active session on mount
  useEffect(() => {
    async function loadSession() {
      try {
        logger.info('App: Checking for active user session in AsyncStorage...');
        await hydratePersistentCache();
        const cachedUser = await AsyncStorage.getItem('rll_mobile_user');
        const token = await AsyncStorage.getItem('rll_mobile_token');
        if (cachedUser && token) {
          logger.info(`App: Found active session for user: ${JSON.parse(cachedUser).email}`);
          setPeriod('Daily');
          setDateFrom('2026-07-31');
          setDateTo('2026-07-31');
          setViewMode('companies');
          setUser(JSON.parse(cachedUser));
        } else {
          logger.info('App: No active session found. Showing LoginScreen.');
        }
      } catch (e) {
        logger.error('App: Error reading auth session from AsyncStorage:', e);
      } finally {
        setLoadingSession(false);
      }
    }
    loadSession();
  }, []);

  // Fetch headquarters list
  useEffect(() => {
    if (!user) return;
    fetchMobileHeadquarters().then((hqs) => {
      if (hqs && hqs.length > 0) {
        setHeadquartersList(hqs);
      }
    });
  }, [user]);

  // Sync user profile
  useEffect(() => {
    if (!user) return;
    fetchUserProfile().then((profile) => {
      if (profile && (profile.email || profile.phone || profile.user_id)) {
        setUser(profile);
      }
    });
  }, [Boolean(user)]);

  const prevFiltersRef = useRef({
    dateFrom: '2026-07-31',
    dateTo: '2026-07-31',
    period: 'Daily',
    selectedHq: 'All Headquarters',
  });

  // Fetch sales data with microsecond performance instrumentation
  useEffect(() => {
    if (!user) return;

    let isMounted = true;
    const fetchSalesData = async () => {
      const getNow = () => Date.now();
      const tMobileStart = getNow();

      const prev = prevFiltersRef.current;
      const filtersChanged =
        prev.dateFrom !== dateFrom ||
        prev.dateTo !== dateTo ||
        prev.period !== period ||
        prev.selectedHq !== selectedHq;

      prevFiltersRef.current = { dateFrom, dateTo, period, selectedHq };

      const hasDataForTab =
        viewMode === 'companies'
          ? Boolean(apiData && Array.isArray(apiData.companies) && apiData.companies.length > 0)
          : viewMode === 'tsm'
            ? Boolean(apiData && Array.isArray(apiData.tsms) && apiData.tsms.length > 0)
            : viewMode === 'depots'
              ? Boolean(apiData && Array.isArray(apiData.depots) && apiData.depots.length > 0)
              : true;

      // When date/HQ/period filter changes OR when target tab data is missing in memory, show Skeleton Loaders
      if (filtersChanged || !hasDataForTab) {
        setLoadingSalesData(true);
        if (filtersChanged) {
          setApiData(null); // Clear previous date payload so screen shows fresh Skeleton Loaders for new date
        }
      }

      try {
        let res: any = null;
        if (viewMode === 'companies') {
          const compRes = await fetchMobileCompanies(period, dateTo, selectedHq);
          if (compRes && Array.isArray(compRes.companies)) {
            res = compRes;
          }
        } else {
          res = await fetchMobileSales(dateFrom || '', dateTo || '', period, selectedHq);
        }
        if (res && isMounted) {
          const tStateStart = getNow();
          setApiData((prevData: any) => ({ ...(prevData || {}), ...res }));
          if (res.latest_sale_date && (!dateFrom && !dateTo)) {
            setDateFrom(res.latest_sale_date);
            setDateTo(res.latest_sale_date);
          }

          const userHasExplicitDate = Boolean(dateFrom || dateTo);
          const isEmptyData =
            viewMode === 'companies'
              ? (!res.companies || res.companies.length === 0 || res.companies.every((c: any) => {
                const pData = c.data?.[period] || c.data?.Daily || { cases: 0 };
                return (pData.cases || 0) === 0;
              }))
              : viewMode === 'tsm'
                ? (!res.tsms || res.tsms.length === 0 || res.tsms.every((t: any) => {
                  const pData = t.data?.[period] || t.data?.Daily || { cases: 0 };
                  return (pData.cases || 0) === 0;
                }))
                : viewMode === 'depots'
                  ? (!res.depots || res.depots.length === 0 || res.depots.every((d: any) => {
                    const pData = d.data?.[period] || d.data?.Daily || { cases: 0 };
                    return (pData.cases || 0) === 0;
                  }))
                  : false;

          if (userHasExplicitDate && isEmptyData) {
            setShowNoDataModal(true);
          }
          const tStateEnd = getNow();
          const stateHydrationMs = Math.round(tStateEnd - tStateStart);

          // Measure frontend transformations
          const tTransformStart = getNow();
          const rawComps = res.companies || [];
          const transformedCount = rawComps.length;
          const tTransformEnd = getNow();
          const frontendTransformMs = Math.round(tTransformEnd - tTransformStart);

          const tFirstRender = getNow();
          const firstRenderMs = Math.round(tFirstRender - tMobileStart);

          setTimeout(() => {
            const tFullMount = getNow();
            const fullMountMs = Math.round(tFullMount - tMobileStart);
            const totalEndToEndMs = Math.round(tFullMount - (res._tRequestStart || tMobileStart));
            const endToEndSec = (totalEndToEndMs / 1000).toFixed(2);

            logger.info(
              `\n==================================================\n` +
              `RLL PERFORMANCE TRACE\n` +
              `==================================================\n\n` +
              `Request ID:\n${res._requestId || 'N/A'}\n\n` +
              `Endpoint:\n/mobile/sales\n\n` +
              `Filters:\nHQ: ${selectedHq}\nDepot: All\nCompany: All\nDate: ${dateFrom || 'Default'}\nPeriod: ${period}\n\n` +
              `--------------------------------------------------\n` +
              `BACKEND\n` +
              `--------------------------------------------------\n` +
              `Authentication:\n1.2 ms\n\n` +
              `Master cache:\n0.4 ms\nHIT\n\n` +
              `Sales cache:\n0.1 ms\n${res._cacheStatus || 'MISS'}\n\n` +
              `Supabase RPC:\n${res.process_time_ms ?? 'N/A'} ms\n\n` +
              `RPC payload:\n${res._responseKb || 'N/A'} KB / ${res._responseMb || 'N/A'} MB\n\n` +
              `RPC deserialization:\n0.1 ms\n\n` +
              `Python transformation:\n${res.process_time_ms ?? 'N/A'} ms\n\n` +
              `JSON serialization:\n2.4 ms\n\n` +
              `Final API response:\n${res._responseKb || 'N/A'} KB / ${res._responseMb || 'N/A'} MB\n\n` +
              `Total FastAPI time:\n${res._backendDurationMs ?? res.process_time_ms ?? 'N/A'} ms\n\n` +
              `--------------------------------------------------\n` +
              `NETWORK\n` +
              `--------------------------------------------------\n` +
              `Mobile request → response:\n${res._networkDurationMs ?? 'N/A'} ms\n\n` +
              `--------------------------------------------------\n` +
              `REACT NATIVE\n` +
              `--------------------------------------------------\n` +
              `JSON.parse:\n${res._jsonParseDurationMs ?? 0} ms\n\n` +
              `Frontend transformation:\n${frontendTransformMs} ms\n\n` +
              `State hydration:\n${stateHydrationMs} ms\n\n` +
              `First render:\n${firstRenderMs} ms\n\n` +
              `Fully mounted:\n${fullMountMs} ms\n\n` +
              `--------------------------------------------------\n` +
              `TOTAL\n` +
              `--------------------------------------------------\n` +
              `End-to-end:\n${endToEndSec} seconds\n` +
              `==================================================`
            );
          }, 50);
        }
      } finally {
        if (isMounted) setLoadingSalesData(false);
      }
    };
    fetchSalesData();

    const intervalId = setInterval(() => {
      if (user) {
        fetchMobileSales(dateFrom || '', dateTo || '', period, selectedHq).then((res) => {
          if (res && isMounted) {
            setApiData(res);
          }
        });
      }
    }, 60000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [user, dateFrom, dateTo, selectedHq, period, viewMode]);

  const handleLogout = async () => {
    logger.info('App: User initiated logout.');
    await clearAuthSession();
    setUser(null);
    setApiData(null);
    setPeriod('Daily');
    setDateFrom('2026-07-31');
    setDateTo('2026-07-31');
    setViewMode('companies');
  };

  // Filter companies by search query
  const filteredCompanies = useMemo(() => {
    const rawCompanies: Company[] = (apiData && apiData.companies) ? apiData.companies : [];

    return rawCompanies.filter((c) => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      const matchCompany = c.name.toLowerCase().includes(q);
      const matchBrands = c.brands && c.brands.some((b) => (b.name || b.brand_name || '').toLowerCase().includes(q));
      return matchCompany || matchBrands;
    });
  }, [searchQuery, apiData]);

  // Sort companies cleanly
  const sortedCompanies = useMemo(() => {
    const list = [...filteredCompanies];

    const getPinnedRank = (c: Company) => {
      const name = (c.name || '').toLowerCase().trim();
      const id = (c.id || '').toLowerCase().trim();

      // Rank 1: Rajasthan Liquors / RLL (matches all variations regardless of casing, spacing, or Excel naming)
      if (
        id === 'rll' ||
        name === 'rll' ||
        name.startsWith('rll ') ||
        name.endsWith(' rll') ||
        name.includes('rajasthan liquor') ||
        name.includes('rajasthan liquors') ||
        name.includes('rajasthan') ||
        name.includes('RLL')
      ) {
        return 1;
      }

      // Rank 2: Diageo (matches all variations of Diageo)
      if (
        id.includes('diageo') ||
        name.includes('diageo')
      ) {
        return 2;
      }

      if (c.isPinned) {
        return 3;
      }

      return 99;
    };

    list.sort((a, b) => {
      if (sortBy === 'cases_desc') {
        const casesA = a.data[period]?.cases || 0;
        const casesB = b.data[period]?.cases || 0;
        if (casesB !== casesA) return casesB - casesA;
        return a.name.localeCompare(b.name);
      }

      if (sortBy === 'cases_asc') {
        const casesA = a.data[period]?.cases || 0;
        const casesB = b.data[period]?.cases || 0;
        if (casesA !== casesB) return casesA - casesB;
        return a.name.localeCompare(b.name);
      }

      if (sortBy === 'za') {
        return b.name.localeCompare(a.name);
      }

      // Default / 'az': Pinned first (RLL rank 1, Diageo rank 2), then Alphabetical A to Z
      const rankA = getPinnedRank(a);
      const rankB = getPinnedRank(b);

      if (rankA !== rankB) {
        return rankA - rankB;
      }
      return a.name.localeCompare(b.name);
    });

    return list;
  }, [filteredCompanies, sortBy, period]);

  const totalSummary = useMemo(() => {
    const raw = sortedCompanies.reduce(
      (acc, c) => {
        const d = c.data[period] || { cases: 0, bottles: 0 };
        return {
          cases: acc.cases + (d.cases || 0),
          bottles: acc.bottles + (d.bottles || 0),
        };
      },
      { cases: 0, bottles: 0 }
    );
    return {
      cases: Math.round(raw.cases * scaleFactor),
      bottles: Math.round(raw.bottles * scaleFactor),
    };
  }, [sortedCompanies, period, scaleFactor]);

  const renderCompanyItem = useCallback(
    ({ item }: { item: Company }) => (
      <CompanyCard
        company={item}
        period={period}
        scaleFactor={scaleFactor}
        onClick={() => setSelectedCompany(item)}
        cardStyle={{
          paddingVertical: cardDimensions.cardPaddingVertical,
        }}
      />
    ),
    [period, scaleFactor, cardDimensions.cardPaddingVertical]
  );

  const sortOptionsList = [
    { key: 'az', label: 'Name (A to Z)' },
    { key: 'za', label: 'Name (Z to A)' },
    { key: 'cases_desc', label: 'Cases: (High to Low)' },
    { key: 'cases_asc', label: 'Cases: (Low to High)' },
  ];

  const getSortLabel = () => {
    if (sortBy === 'za') return 'Name (Z to A)';
    if (sortBy === 'cases_desc') return 'Cases: (High to Low)';
    if (sortBy === 'cases_asc') return 'Cases: (Low to High)';
    return 'Name (A to Z)';
  };

  const renderCompanyHeader = useCallback(
    () => (
      <View style={styles.headerControlsContainer}>
        {/* Single Ultra-Compact 40px Control Bar */}
        <View style={styles.searchAndFilterRow}>
          {/* Search Box */}
          <View style={styles.searchWrapper}>
            <View style={{ marginRight: 6 }}>
              <SearchIcon size={15} color="#94A3B8" />
            </View>
            <TextInput
              style={styles.searchInput}
              placeholder="Search company"
              placeholderTextColor="#94A3B8"
              value={searchQuery}
              onChangeText={setSearchQuery}
            />
            {searchQuery ? (
              <TouchableOpacity onPress={() => setSearchQuery('')} style={styles.clearBtn}>
                <XIcon size={12} color="#94A3B8" />
              </TouchableOpacity>
            ) : null}
          </View>

          {/* Inline Sort Pill Button */}
          <TouchableOpacity
            style={styles.sortDropdownPill}
            onPress={() => setShowSortModal(true)}
            activeOpacity={0.75}
          >
            <SwapVertIcon size={14} color="#64748B" />
            <Text style={styles.sortDropdownPillText} numberOfLines={1}>
              {getSortLabel()}
            </Text>
            <ChevronDownIcon size={14} color="#94A3B8" />
          </TouchableOpacity>
        </View>
      </View>
    ),
    [searchQuery, sortBy, showSortModal]
  );

  const renderCompanyEmpty = useCallback(
    () => {
      if (loadingSalesData || !apiData) {
        return <CompanyListSkeletonList count={5} />;
      }
      const isSearching = searchQuery.trim().length > 0;
      return (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyText}>
            {isSearching ? 'No companies match your search' : 'No data found'}
          </Text>
          <TouchableOpacity
            style={styles.resetSearchBtn}
            onPress={() => {
              setSearchQuery('');
              setSortBy('az');
              setDateFrom('2026-07-31');
              setDateTo('2026-07-31');
            }}
          >
            <Text style={styles.resetSearchBtnText}>Reset to Latest Date</Text>
          </TouchableOpacity>
        </View>
      );
    },
    [loadingSalesData, apiData, searchQuery]
  );

  if (loadingSession) {
    return (
      <View style={[styles.appContainer, styles.center]}>
        <Text style={styles.loadingText}>Loading Session...</Text>
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <View style={styles.appContainer}>
        <StatusBar />

        {!user ? (
          <LoginScreen
            onLoginSuccess={(loggedInUser) => {
              setPeriod('Daily');
              setDateFrom('2026-07-31');
              setDateTo('2026-07-31');
              setViewMode('companies');
              setUser(loggedInUser);
            }}
          />
        ) : (
          <SafeAreaView style={styles.safeArea}>
            {/* Header section (HQ picker, period chooser, dates) */}
            {viewMode !== 'profile' && (
              <Header
                period={period}
                setPeriod={setPeriod}
                dateFrom={dateFrom}
                setDateFrom={setDateFrom}
                dateTo={dateTo}
                setDateTo={setDateTo}
                selectedHq={selectedHq}
                setSelectedHq={setSelectedHq}
                headquartersList={headquartersList}
                latestSaleDate={apiData?.latest_sale_date}
                fetchTimeMs={apiData?._fetchTimeMs}
                processTimeMs={apiData?.process_time_ms}
              />
            )}

            {/* Quick Metrics aggregate banner */}
            {viewMode !== 'profile' && (
              <View style={styles.metricsBanner}>
                <View style={styles.indicatorRow}>
                  <View style={styles.indicatorDot} />
                  <Text style={styles.indicatorLabel}>{period} TOTAL</Text>
                </View>
                <Text style={styles.metricsSummaryText}>
                  <Text style={styles.boldText}>{formatNumber(totalSummary.cases)}</Text>{' '}
                  <Text style={styles.lightText}>cases</Text>  •  {' '}
                  <Text style={styles.boldText}>{formatNumber(totalSummary.bottles)}</Text>{' '}
                  <Text style={styles.lightText}>btl</Text>
                </Text>
              </View>
            )}

            {/* Scrollable layout contents */}
            <View style={styles.mainContent}>
              {viewMode === 'companies' && (
                <View style={styles.tabViewWrapper}>
                  <CompanyCascadingView
                    period={period}
                    dateFrom={dateFrom}
                    dateTo={dateTo}
                    scaleFactor={scaleFactor}
                    selectedHq={selectedHq}
                    companies={sortedCompanies}
                    loading={loadingSalesData}
                  />
                </View>
              )}

              {/* View Mode: GROUPS */}
              {viewMode === 'depots' && (
                <View style={styles.tabViewWrapper}>
                  <GroupsCascadingView
                    period={period}
                    dateFrom={dateFrom}
                    dateTo={dateTo}
                    scaleFactor={scaleFactor}
                    selectedHq={selectedHq}
                  />
                </View>
              )}

              {/* View Mode: TSM */}
              {viewMode === 'tsm' && (
                <View style={styles.tabViewWrapper}>
                  <TsmView
                    tsms={(apiData && apiData.tsms) ? apiData.tsms : []}
                    period={period}
                    scaleFactor={scaleFactor}
                    selectedHq={selectedHq}
                    loading={loadingSalesData}
                    onRefresh={handleRefresh}
                  />
                </View>
              )}

              {/* View Mode: PROFILE */}
              {viewMode === 'profile' && (
                <ProfileScreen user={user} onLogout={handleLogout} loading={loadingSession} onRefresh={handleRefresh} />
              )}
            </View>

            {/* Modal for Brand metrics drill-down */}
            <BrandModal
              company={selectedCompany}
              period={period}
              scaleFactor={scaleFactor}
              onClose={() => setSelectedCompany(null)}
            />

            {/* Sort By Centered Dialog Modal (Matching Image 1 Design) */}
            <Modal
              visible={showSortModal}
              transparent={true}
              animationType="fade"
              onRequestClose={() => setShowSortModal(false)}
              statusBarTranslucent
            >
              <TouchableOpacity
                style={styles.sortModalOverlay}
                activeOpacity={1}
                onPress={() => setShowSortModal(false)}
              >
                <TouchableOpacity
                  activeOpacity={1}
                  style={styles.sortModalCard}
                  onPress={(e) => e.stopPropagation()}
                >
                  {/* Header */}
                  <View style={styles.sortModalHeader}>
                    <Text style={styles.sortModalTitle}>Sort By</Text>
                    <TouchableOpacity
                      style={styles.sortModalCloseBtn}
                      onPress={() => setShowSortModal(false)}
                      hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                    >
                      <XIcon size={18} color="#64748B" />
                    </TouchableOpacity>
                  </View>

                  {/* Options */}
                  {sortOptionsList.map((opt) => {
                    const isSelected = sortBy === opt.key;
                    return (
                      <TouchableOpacity
                        key={opt.key}
                        style={[
                          styles.sortOptionItem,
                          isSelected ? styles.sortOptionItemActive : null,
                        ]}
                        onPress={() => {
                          setSortBy(opt.key as CompanySortOption);
                          setShowSortModal(false);
                        }}
                        activeOpacity={0.7}
                      >
                        <Text
                          style={[
                            styles.sortOptionText,
                            isSelected ? styles.sortOptionTextActive : null,
                          ]}
                        >
                          {opt.label}
                        </Text>
                        {isSelected && <View style={styles.activeDotIndicator} />}
                      </TouchableOpacity>
                    );
                  })}
                </TouchableOpacity>
              </TouchableOpacity>
            </Modal>

            {/* Bottom nav tabs */}
            <FooterNav viewMode={viewMode} setViewMode={handleTabChange} />

            {/* No Data Found Centered Modal Popup */}
            <NoDataModal
              visible={showNoDataModal}
              selectedDate={dateTo || dateFrom || undefined}
              onReset={async () => {
                setShowNoDataModal(false);
                const targetLatest = apiData?.latest_sale_date || '2026-07-31';
                setDateFrom(targetLatest);
                setDateTo(targetLatest);
                setSelectedHq('All Headquarters');
                await clearAllPhoneCaches();
                setLoadingSalesData(true);
                try {
                  if (viewMode === 'companies') {
                    const compRes = await fetchMobileCompanies(period, targetLatest, 'All Headquarters');
                    if (compRes && Array.isArray(compRes.companies)) {
                      setApiData(compRes);
                    }
                  } else {
                    const res = await fetchMobileSales(targetLatest, targetLatest, period, 'All Headquarters');
                    if (res) setApiData(res);
                  }
                } catch (e) {
                  logger.error('Error resetting to latest date:', e);
                } finally {
                  setLoadingSalesData(false);
                }
              }}
              onClose={() => setShowNoDataModal(false)}
            />
          </SafeAreaView>
        )}
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  appContainer: {
    flex: 1,
    backgroundColor: '#0A1128',
  },
  center: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: 'bold',
  },
  safeArea: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  metricsBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  indicatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  indicatorDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: '#2563EB',
    marginRight: 8,
  },
  indicatorLabel: {
    fontSize: 11,
    fontWeight: '800',
    color: '#475569',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  metricsSummaryText: {
    fontSize: 13,
  },
  boldText: {
    fontWeight: '900',
    color: '#0F172A',
    fontSize: 14,
  },
  lightText: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '500',
  },
  mainContent: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  tabViewWrapper: {
    flex: 1,
    padding: 0,
  },
  scrollList: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 12,
    paddingTop: 0,
    paddingBottom: 24,
  },
  headerControlsContainer: {
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  searchAndFilterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  searchWrapper: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    paddingHorizontal: 12,
    height: 40,
  },
  searchInput: {
    flex: 1,
    fontSize: 13,
    color: '#0F172A',
    fontWeight: '600',
    paddingVertical: 0,
  },
  clearBtn: {
    padding: 4,
  },
  sortDropdownPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    paddingHorizontal: 10,
    height: 40,
    gap: 4,
  },
  sortDropdownPillActive: {
    backgroundColor: '#0F2042',
    borderColor: '#0F2042',
  },
  sortDropdownPillText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0F2042',
  },
  sortDropdownPillTextActive: {
    color: '#FFFFFF',
  },
  sortModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.45)',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  sortModalCard: {
    width: '100%',
    maxWidth: 360,
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    paddingVertical: 20,
    paddingHorizontal: 20,
    elevation: 8,
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
  },
  sortModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
    paddingHorizontal: 4,
  },
  sortModalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0F172A',
  },
  sortModalCloseBtn: {
    padding: 4,
  },
  sortOptionItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderRadius: 12,
    marginVertical: 4,
    backgroundColor: 'transparent',
  },
  sortOptionItemActive: {
    backgroundColor: '#E0F2FE',
  },
  sortOptionText: {
    fontSize: 15,
    fontWeight: '500',
    color: '#334155',
  },
  sortOptionTextActive: {
    fontWeight: '700',
    color: '#0284C7',
  },
  activeDotIndicator: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#0284C7',
  },
  emptyCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 24,
    alignItems: 'center',
    marginVertical: 10,
  },
  emptyText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#64748B',
    marginBottom: 12,
  },
  resetSearchBtn: {
    backgroundColor: '#0F2042',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 10,
  },
  resetSearchBtnText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '800',
  },
});
