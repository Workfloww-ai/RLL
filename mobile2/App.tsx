import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  StatusBar,
  StyleSheet,
  View,
  Text,
  ScrollView,
  FlatList,
  TextInput,
  TouchableOpacity,
  Platform,
  useWindowDimensions,
  BackHandler,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { logger } from './src/lib/logger';

import { Company, Depot, TSM, Period, ViewMode } from './src/types';
import { formatNumber } from './src/lib/utils';
import { getDynamicCardDimensions } from './src/lib/responsive';
import {
  fetchMobileSales,
  fetchUserProfile,
  fetchMobileHeadquarters,
  clearAuthSession,
} from './src/lib/api';

import { Header } from './src/features/dashboard/Header';
import { FooterNav } from './src/features/dashboard/FooterNav';
import { CompanyCard } from './src/features/dashboard/CompanyCard';
import { CompanyListSkeletonList } from './src/features/dashboard/CompanyCardSkeleton';
import { DepotsView } from './src/features/dashboard/DepotsView';
import { GroupsCascadingView } from './src/features/dashboard/GroupsCascadingView';
import { TsmView } from './src/features/dashboard/TsmView';
import { BrandModal } from './src/features/dashboard/BrandModal';
import { LoginScreen } from './src/features/auth/LoginScreen';
import { ProfileScreen } from './src/features/profile/ProfileScreen';
import { XIcon, SearchIcon } from './src/components/Icons';

export default function App() {
  const [user, setUser] = useState<any>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [period, setPeriod] = useState<Period>('Daily');
  const [dateFrom, setDateFrom] = useState<string>('2026-05-31');
  const [dateTo, setDateTo] = useState<string>('2026-05-31');
  const [viewMode, setViewMode] = useState<ViewMode>('companies');
  const [viewModeHistory, setViewModeHistory] = useState<ViewMode[]>(['companies']);
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedHq, setSelectedHq] = useState<string>('All Headquarters');
  const [headquartersList, setHeadquartersList] = useState<string[]>(['All Headquarters']);
  const [apiData, setApiData] = useState<any>(null);
  const [loadingSalesData, setLoadingSalesData] = useState(true);

  const handleTabChange = useCallback((newMode: ViewMode) => {
    setViewMode((currentMode) => {
      if (newMode !== currentMode) {
        setViewModeHistory((prev) => [...prev, newMode]);
        return newMode;
      }
      return currentMode;
    });
  }, []);

  // Hardware BackHandler for tab history
  useEffect(() => {
    const onBackPress = () => {
      // 1. If BrandModal is open in App.tsx, close it
      if (selectedCompany !== null) {
        setSelectedCompany(null);
        return true;
      }
      // 2. If we have tab history, navigate back to previous tab
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
      return false; // Exit app on root screen
    };
    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [selectedCompany, viewModeHistory]);

  const { height: windowHeight } = useWindowDimensions();
  const cardDimensions = useMemo(() => getDynamicCardDimensions(windowHeight), [windowHeight]);

  const scaleFactor = 1;

  // Initialize status bar colors
  useEffect(() => {
    StatusBar.setBarStyle('light-content');
  }, []);

  // 1. Load active session on mount
  useEffect(() => {
    async function loadSession() {
      try {
        logger.info('App: Checking for active user session in AsyncStorage...');
        const cachedUser = await AsyncStorage.getItem('rll_mobile_user');
        const token = await AsyncStorage.getItem('rll_mobile_token');
        if (cachedUser && token) {
          logger.info(`App: Found active session for user: ${JSON.parse(cachedUser).email}`);
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

  // 2. Fetch headquarters list once when user session is active
  useEffect(() => {
    if (!user) return;
    fetchMobileHeadquarters().then((hqs) => {
      if (hqs && hqs.length > 0) {
        setHeadquartersList(hqs);
      }
    });
  }, [user]);

  // 3. Sync user profile on mount / token load
  useEffect(() => {
    if (!user) return;
    fetchUserProfile().then((profile) => {
      if (profile && (profile.email || profile.phone || profile.user_id)) {
        setUser(profile);
      }
    });
  }, [Boolean(user)]);

  // 4. Initial sales data load, period/filter changes, and auto-date discovery
  useEffect(() => {
    if (!user) return;

    let isMounted = true;
    const fetchSalesData = async () => {
      setLoadingSalesData(true);
      try {
        const res = await fetchMobileSales(dateFrom || '', dateTo || '', period, selectedHq);
        if (res && isMounted) {
          setApiData(res);
          if (res.latest_sale_date && !dateFrom && !dateTo) {
            setDateFrom(res.latest_sale_date);
            setDateTo(res.latest_sale_date);
          }
        }
      } finally {
        if (isMounted) setLoadingSalesData(false);
      }
    };
    fetchSalesData();

    // Live real-time background sync every 60 seconds
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
  }, [user, dateFrom, dateTo, selectedHq]);

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

  const renderCompanyHeader = useCallback(
    () => (
      <>
        {/* Search box for companies list */}
        <View style={styles.searchWrapper}>
          <View style={{ marginRight: 8 }}>
            <SearchIcon size={18} color="#94A3B8" />
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

        {/* Active filters display */}
        {(selectedHq !== 'All Headquarters' || searchQuery) && (
          <View style={styles.activeFiltersPillRow}>
            {selectedHq !== 'All Headquarters' && (
              <View style={styles.filterPill}>
                <Text style={styles.filterPillText}>HQ: {selectedHq}</Text>
                <TouchableOpacity onPress={() => setSelectedHq('All Headquarters')}>
                  <Text style={styles.filterPillClose}>✕</Text>
                </TouchableOpacity>
              </View>
            )}
            {searchQuery && (
              <View style={styles.filterPill}>
                <Text style={styles.filterPillText}>"{searchQuery}"</Text>
                <TouchableOpacity onPress={() => setSearchQuery('')}>
                  <Text style={styles.filterPillClose}>✕</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}
      </>
    ),
    [searchQuery, selectedHq]
  );

  const renderCompanyEmpty = useCallback(
    () => {
      if (loadingSalesData || !apiData) {
        return <CompanyListSkeletonList count={5} />;
      }
      return (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyText}>No companies match your filters</Text>
        </View>
      );
    },
    [loadingSalesData, apiData]
  );



  const handleLogout = async () => {
    logger.info('App: User initiated logout.');
    await clearAuthSession();
    setUser(null);
    setApiData(null);
    setDateFrom('');
    setDateTo('');
    setViewMode('companies');
  };

  // Filter and sort companies
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

  const sortedCompanies = useMemo(() => {
    const list = [...filteredCompanies];
    list.sort((a, b) => {
      const getPinnedRank = (c: Company) => {
        const id = c.id.toLowerCase();
        const name = c.name.toLowerCase();
        if (id === 'rll' || name === 'rll') return 1;
        if (id === 'diageo-inbrew' || name.includes('diageo')) return 2;
        if (c.isPinned) return 3;
        return 99;
      };

      const rankA = getPinnedRank(a);
      const rankB = getPinnedRank(b);

      if (rankA !== rankB) {
        return rankA - rankB;
      }
      return a.name.localeCompare(b.name);
    });
    return list;
  }, [filteredCompanies]);


  const totalSummary = useMemo(() => {
    return sortedCompanies.reduce(
      (acc, c) => {
        const d = c.data[period];
        return {
          cases: acc.cases + Math.round(d.cases * scaleFactor),
          bottles: acc.bottles + Math.round(d.bottles * scaleFactor),
        };
      },
      { cases: 0, bottles: 0 }
    );
  }, [sortedCompanies, period]);

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
          <LoginScreen onLoginSuccess={setUser} />
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
                <FlatList
                  data={loadingSalesData ? [] : sortedCompanies}
                  renderItem={renderCompanyItem}
                  keyExtractor={(item) => item.id}
                  ListHeaderComponent={renderCompanyHeader}
                  ListEmptyComponent={renderCompanyEmpty}
                  style={styles.scrollList}
                  contentContainerStyle={styles.scrollContent}
                  initialNumToRender={10}
                  maxToRenderPerBatch={10}
                  windowSize={5}
                  removeClippedSubviews={Platform.OS === 'android'}
                />
              )}

              {/* View Mode: GROUPS */}
              {viewMode === 'depots' && (
                <View style={styles.tabViewWrapper}>
                  <GroupsCascadingView
                    period={period}
                    dateFrom={dateFrom}
                    dateTo={dateTo}
                    scaleFactor={scaleFactor}
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
                  />
                </View>
              )}

              {/* View Mode: PROFILE */}
              {viewMode === 'profile' && (
                <ProfileScreen user={user} onLogout={handleLogout} loading={loadingSession} />
              )}
            </View>

            {/* Modal for Brand metrics drill-down */}
            <BrandModal
              company={selectedCompany}
              period={period}
              scaleFactor={scaleFactor}
              onClose={() => setSelectedCompany(null)}
            />

            {/* Bottom nav tabs */}
            <FooterNav viewMode={viewMode} setViewMode={handleTabChange} />
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
    padding: 16,
  },
  scrollList: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 24,
  },
  searchWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 16,
    paddingHorizontal: 14,
    marginBottom: 14,
    height: 44,
  },
  searchIcon: {
    fontSize: 15,
    marginRight: 10,
    color: '#94A3B8',
  },
  searchInput: {
    flex: 1,
    fontSize: 14,
    color: '#0F172A',
    fontWeight: '500',
    paddingVertical: 0,
  },
  clearBtn: {
    padding: 6,
  },
  activeFiltersPillRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 10,
  },
  filterPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#EEF2F6',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 20,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginRight: 8,
    marginBottom: 6,
  },
  filterPillText: {
    fontSize: 10,
    fontWeight: 'bold',
    color: '#0F2042',
    marginRight: 6,
  },
  filterPillClose: {
    fontSize: 9,
    fontWeight: '900',
    color: '#94A3B8',
  },
  emptyCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 30,
    alignItems: 'center',
    marginVertical: 10,
  },
  emptyText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#94A3B8',
  },
});

