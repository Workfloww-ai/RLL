import React, { useState, useMemo, useEffect } from 'react';
import {
  StatusBar,
  StyleSheet,
  View,
  Text,
  ScrollView,
  TextInput,
  TouchableOpacity,
  RefreshControl,
  Platform,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { logger } from './src/lib/logger';

import { Company, Depot, TSM, Period, ViewMode } from './src/types';
import { formatNumber } from './src/lib/utils';
import {
  fetchMobileSales,
  fetchUserProfile,
  fetchMobileHeadquarters,
  clearAuthSession,
} from './src/lib/api';

import { Header } from './src/features/dashboard/Header';
import { FooterNav } from './src/features/dashboard/FooterNav';
import { CompanyCard } from './src/features/dashboard/CompanyCard';
import { DepotsView } from './src/features/dashboard/DepotsView';
import { TsmView } from './src/features/dashboard/TsmView';
import { BrandModal } from './src/features/dashboard/BrandModal';
import { LoginScreen } from './src/features/auth/LoginScreen';
import { ProfileScreen } from './src/features/profile/ProfileScreen';
import { XIcon } from './src/components/Icons';

export default function App() {
  const [user, setUser] = useState<any>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [period, setPeriod] = useState<Period>('Daily');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [viewMode, setViewMode] = useState<ViewMode>('companies');
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedHq, setSelectedHq] = useState<string>('All Headquarters');
  const [headquartersList, setHeadquartersList] = useState<string[]>(['All Headquarters']);
  const [apiData, setApiData] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

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

  // 4. Discover latest_sale_date on initial load (with empty dates)
  useEffect(() => {
    if (!user) return;
    if (dateFrom || dateTo) return; // already initialized

    fetchMobileSales('', '', period, selectedHq).then((res) => {
      if (res) {
        setApiData(res);
        if (res.latest_sale_date) {
          setDateFrom(res.latest_sale_date);
          setDateTo(res.latest_sale_date);
        }
      }
    });
  }, [user]);

  // 5. Fetch sales data when filters or dates change (after initialization)
  const loadSalesData = async (showRefreshIndicator = false) => {
    if (!user) return;
    if (!dateFrom || !dateTo) return; // wait for initialization

    if (showRefreshIndicator) setRefreshing(true);
    logger.info(`App: Loading sales data. Period=${period}, HQ=${selectedHq}, DateRange=${dateFrom} to ${dateTo}`);

    try {
      const res = await fetchMobileSales(dateFrom, dateTo, period, selectedHq);
      if (res) {
        setApiData(res);
      } else {
        // Token might have expired
        logger.warn('App: Sales fetch returned null. Checking auth token...');
        const checkToken = await AsyncStorage.getItem('rll_mobile_token');
        if (!checkToken) {
          logger.warn('App: Token missing. Redirecting to LoginScreen.');
          setUser(null);
        }
      }
    } catch (e) {
      logger.error('App: Error fetching sales:', e);
    } finally {
      if (showRefreshIndicator) setRefreshing(false);
    }
  };

  useEffect(() => {
    loadSalesData();
  }, [dateFrom, dateTo, period, selectedHq, Boolean(user)]);

  const onRefresh = () => {
    loadSalesData(true);
  };

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
              />
            )}

            {/* Quick Metrics aggregate banner */}
            {viewMode !== 'profile' && (
              <View style={styles.metricsBanner}>
                <View style={styles.indicatorRow}>
                  <View style={styles.indicatorDot} />
                  <Text style={styles.indicatorLabel}>{period} Total</Text>
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
                <ScrollView
                  style={styles.scrollList}
                  contentContainerStyle={styles.scrollContent}
                  refreshControl={
                    <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={['#0F2042']} />
                  }
                >
                  {/* Search box for companies list */}
                  <View style={styles.searchWrapper}>
                    <Text style={styles.searchIcon}>🔍</Text>
                    <TextInput
                      style={styles.searchInput}
                      placeholder="Search company or brand name..."
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

                  {/* List Cards */}
                  {sortedCompanies.length === 0 ? (
                    <View style={styles.emptyCard}>
                      <Text style={styles.emptyText}>
                        {apiData ? 'No companies match your filters' : 'Loading sales data...'}
                      </Text>
                    </View>
                  ) : (
                    sortedCompanies.map((c) => (
                      <CompanyCard
                        key={c.id}
                        company={c}
                        period={period}
                        scaleFactor={scaleFactor}
                        onClick={() => setSelectedCompany(c)}
                      />
                    ))
                  )}
                </ScrollView>
              )}

              {/* View Mode: DEPOTS */}
              {viewMode === 'depots' && (
                <View style={styles.tabViewWrapper}>
                  <DepotsView
                    depots={(apiData && apiData.depots) ? apiData.depots : []}
                    period={period}
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
                  />
                </View>
              )}

              {/* View Mode: PROFILE */}
              {viewMode === 'profile' && (
                <ProfileScreen user={user} onLogout={handleLogout} />
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
            <FooterNav viewMode={viewMode} setViewMode={setViewMode} />
          </SafeAreaView>
        )}
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  appContainer: {
    flex: 1,
    backgroundColor: '#0F2042',
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
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.02,
    shadowRadius: 2,
    elevation: 1,
  },
  indicatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  indicatorDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#2563EB',
    marginRight: 6,
  },
  indicatorLabel: {
    fontSize: 9,
    fontWeight: 'bold',
    color: '#64748B',
    textTransform: 'uppercase',
  },
  metricsSummaryText: {
    fontSize: 12,
  },
  boldText: {
    fontWeight: '900',
    color: '#0F2042',
  },
  lightText: {
    color: '#94A3B8',
    fontSize: 9,
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
    padding: 16,
    paddingTop: 12,
    paddingBottom: 30,
  },
  searchWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    paddingHorizontal: 12,
    marginBottom: 12,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  searchIcon: {
    fontSize: 14,
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 12,
    color: '#334155',
    paddingVertical: 10,
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
