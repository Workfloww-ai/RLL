import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  BackHandler,
  RefreshControl,
} from 'react-native';
import { Company, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { GroupListSkeletonList, CompanyListSkeletonList } from '../../components/SkeletonLoaders';
import { fetchCompanyBrands, fetchBrandLicensees } from '../../lib/api';
import { MetricsCard } from '../../components/MetricsCard';
import { PaginationBar } from '../../components/PaginationBar';
import { SortModal, SortOptionValue } from '../../components/SortModal';
import { CompanyCard } from './CompanyCard';
import {
  SwapVertIcon,
  XIcon,
  SearchIcon,
  ChevronLeftIcon,
  WineIcon,
  UsersIcon,
} from '../../components/Icons';

interface CompanyCascadingViewProps {
  period: Period;
  dateFrom: string;
  dateTo: string;
  scaleFactor: number;
  selectedHq?: string;
  companies: Company[];
  loading?: boolean;
  selectedCompanyFromParent?: Company | null;
  onClearParentSelectedCompany?: () => void;
}

export function CompanyCascadingView({
  period,
  dateFrom,
  dateTo,
  scaleFactor,
  selectedHq,
  companies,
  loading: parentLoading = false,
  selectedCompanyFromParent,
  onClearParentSelectedCompany,
}: CompanyCascadingViewProps) {
  // Navigation level:
  // Level 1 = Companies List
  // Level 2 = Company Detail (Brands List)
  // Level 3 = Brand Detail (Licensees List)
  const [level, setLevel] = useState<1 | 2 | 3>(1);

  // Selected items
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [selectedBrand, setSelectedBrand] = useState<any | null>(null);

  // Data lists
  const [companyBrands, setCompanyBrands] = useState<any[]>([]);
  const [brandLicensees, setBrandLicensees] = useState<any[]>([]);

  // Filtering & controls
  const [loading, setLoading] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortOption, setSortOption] = useState<SortOptionValue>('az');
  const [showSortModal, setShowSortModal] = useState<boolean>(false);
  const [perPage, setPerPage] = useState<number>(15);
  const [showPerPageModal, setShowPerPageModal] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Caching refs
  const cacheKey = `${dateFrom}_${dateTo}_${period}_${selectedHq || 'All'}`;
  const companyBrandsCacheRef = useRef<Map<string, any[]>>(new Map());
  const brandLicenseesCacheRef = useRef<Map<string, any[]>>(new Map());

  // Reset cache on date/period/HQ changes
  useEffect(() => {
    companyBrandsCacheRef.current.clear();
    brandLicenseesCacheRef.current.clear();
    setCompanyBrands([]);
    setBrandLicensees([]);
  }, [dateFrom, dateTo, period, selectedHq]);

  // Handle drilldown trigger from parent
  useEffect(() => {
    if (selectedCompanyFromParent) {
      setSelectedCompany(selectedCompanyFromParent);
      setSelectedBrand(null);
      setLevel(2);
      setSearchQuery('');
      setCurrentPage(1);
      const compId = (selectedCompanyFromParent as any).company_id || selectedCompanyFromParent.id || selectedCompanyFromParent.name;
      loadCompanyBrands(compId);
    }
  }, [selectedCompanyFromParent]);

  // Reset filters & pagination
  const resetFilters = () => {
    setSearchQuery('');
    setSortOption('az');
    setCurrentPage(1);
  };

  // Helper for consistent company cache key resolution
  const getNormalizedCompanyKey = useCallback((companyObjOrId: any): string => {
    if (!companyObjOrId) return '';
    const id = typeof companyObjOrId === 'string'
      ? companyObjOrId
      : (companyObjOrId.company_id || companyObjOrId.id || companyObjOrId.name || '');
    return String(id).trim().toLowerCase();
  }, []);

  // 1. Fetch Brands for Selected Company (Level 2)
  const loadCompanyBrands = async (companyObjOrId: any, forceRefresh = false) => {
    const targetId = typeof companyObjOrId === 'string'
      ? companyObjOrId
      : (companyObjOrId?.company_id || companyObjOrId?.id || companyObjOrId?.name || '');

    if (!targetId) return;

    const normKey = getNormalizedCompanyKey(companyObjOrId);
    const key = `${normKey}_${cacheKey}`;

    if (!forceRefresh && companyBrandsCacheRef.current.has(key)) {
      const cached = companyBrandsCacheRef.current.get(key) || [];
      setCompanyBrands(cached);
      return;
    }

    setLoading(true);
    try {
      const data = await fetchCompanyBrands(targetId, dateFrom, dateTo, selectedHq);
      const result = data || [];
      companyBrandsCacheRef.current.set(key, result);
      setCompanyBrands(result);
    } catch (e) {
      console.error(`Error loading brands for company ${targetId}:`, e);
      if (!companyBrandsCacheRef.current.has(key)) {
        setCompanyBrands([]);
      }
    } finally {
      setLoading(false);
    }
  };

  // 2. Fetch Licensees for Selected Brand (Level 3)
  const loadBrandLicensees = async (brandId: string, forceRefresh = false) => {
    const key = `${brandId}_${cacheKey}`;
    if (!forceRefresh && brandLicenseesCacheRef.current.has(key)) {
      setBrandLicensees(brandLicenseesCacheRef.current.get(key) || []);
      return;
    }

    setLoading(true);
    try {
      const data = await fetchBrandLicensees(brandId, dateFrom, dateTo, selectedHq);
      const result = data || [];
      brandLicenseesCacheRef.current.set(key, result);
      setBrandLicensees(result);
    } catch (e) {
      console.error(`Error loading licensees for brand ${brandId}:`, e);
      setBrandLicensees([]);
    } finally {
      setLoading(false);
    }
  };

  // Sync details on date/period/HQ changes
  useEffect(() => {
    if (level === 2 && selectedCompany) {
      loadCompanyBrands(selectedCompany);
    } else if (level === 3 && selectedBrand) {
      loadBrandLicensees(selectedBrand.brand_id);
    }
  }, [dateFrom, dateTo, period, selectedHq]);

  // Selection handlers
  const handleSelectCompany = (c: Company) => {
    setSelectedCompany(c);
    setSelectedBrand(null);
    setLevel(2);
    resetFilters();
    loadCompanyBrands(c);
  };

  const handleSelectBrand = (brand: any) => {
    setSelectedBrand(brand);
    setLevel(3);
    resetFilters();
    loadBrandLicensees(brand.brand_id);
  };

  const handleGoBack = useCallback(() => {
    if (level === 3) {
      setSelectedBrand(null);
      setLevel(2);
      resetFilters();

      if (selectedCompany) {
        const normKey = getNormalizedCompanyKey(selectedCompany);
        const key = `${normKey}_${cacheKey}`;
        if (companyBrandsCacheRef.current.has(key)) {
          setCompanyBrands(companyBrandsCacheRef.current.get(key) || []);
        } else {
          loadCompanyBrands(selectedCompany);
        }
      }
    } else if (level === 2) {
      setSelectedCompany(null);
      setSelectedBrand(null);
      setLevel(1);
      resetFilters();
      if (onClearParentSelectedCompany) {
        onClearParentSelectedCompany();
      }
    }
  }, [level, selectedCompany, cacheKey, onClearParentSelectedCompany, getNormalizedCompanyKey]);

  // Hardware BackHandler
  useEffect(() => {
    if (level === 1 && !showSortModal && !showPerPageModal) return;
    const onBackPress = () => {
      if (showSortModal) {
        setShowSortModal(false);
        return true;
      }
      if (showPerPageModal) {
        setShowPerPageModal(false);
        return true;
      }
      if (level > 1) {
        handleGoBack();
        return true;
      }
      return false;
    };
    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [level, handleGoBack, showSortModal, showPerPageModal]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    companyBrandsCacheRef.current.clear();
    brandLicenseesCacheRef.current.clear();
    try {
      if (level === 2 && selectedCompany) {
        await loadCompanyBrands(selectedCompany, true);
      } else if (level === 3 && selectedBrand?.brand_id) {
        await loadBrandLicensees(selectedBrand.brand_id, true);
      }
    } catch (err) {
      console.error('Error refreshing CompanyCascadingView:', err);
    } finally {
      setRefreshing(false);
    }
  }, [level, selectedCompany, selectedBrand]);

  // Helper to extract cases and bottles respecting period
  const getScaledCases = (item: any): number => {
    const rawCases = Number(
      item.data?.[period]?.cases ??
      item.cases ??
      item.total_cases ??
      item.mtd_cases ??
      0
    );
    return Math.round(rawCases * scaleFactor);
  };

  const getScaledBottles = (item: any): number => {
    const rawBottles = Number(
      item.data?.[period]?.bottles ??
      item.bottles ??
      item.total_bottles ??
      item.mtd_bottles ??
      0
    );
    return Math.round(rawBottles * scaleFactor);
  };

  // Determine active raw dataset for current level
  const activeRawList = useMemo(() => {
    if (level === 1) return companies;
    if (level === 2) return companyBrands;
    return brandLicensees;
  }, [level, companies, companyBrands, brandLicensees]);

  // Pinned Rank helper for Companies (BUSINESS_LOGIC_SPEC.md Section 5)
  const getPinnedRank = (item: any): number => {
    const id = String(item.id || '').toLowerCase();
    const name = String(item.name || item.company_name || '').toLowerCase();

    if (
      id === 'rll' ||
      name === 'rll' ||
      name.startsWith('rll ') ||
      name.includes('rajasthan liquor') ||
      name.includes('rajasthan liquors') ||
      name.includes('rajasthan')
    ) {
      return 1;
    }
    if (id.includes('diageo') || name.includes('diageo')) {
      return 2;
    }
    if (item.isPinned) return 3;
    return 99;
  };

  // Filter & Sort active list
  const filteredAndSortedList = useMemo(() => {
    let result = [...activeRawList];

    // Filter out "Others" company (AGENTS.md Rule 7 & BUSINESS_LOGIC_SPEC.md Section 4)
    if (level === 1) {
      result = result.filter(c => {
        const name = (c.name || '').trim().toLowerCase();
        return name !== 'others' && name !== 'others company' && !name.startsWith('others ');
      });
    }

    // Search query filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter(item => {
        const name = String(item.name || item.brand_name || item.licensee_name || item.group_name || '').toLowerCase();
        const code = String(item.code || item.licensee_id || item.brand_id || '').toLowerCase();
        return name.includes(q) || code.includes(q);
      });
    }

    // Sort options
    result.sort((a, b) => {
      if (sortOption === 'cases_desc') {
        const casesA = getScaledCases(a);
        const casesB = getScaledCases(b);
        if (casesB !== casesA) return casesB - casesA;
        const nameA = a.name || a.brand_name || a.licensee_name || '';
        const nameB = b.name || b.brand_name || b.licensee_name || '';
        return nameA.localeCompare(nameB);
      }

      if (sortOption === 'cases_asc') {
        const casesA = getScaledCases(a);
        const casesB = getScaledCases(b);
        if (casesA !== casesB) return casesA - casesB;
        const nameA = a.name || a.brand_name || a.licensee_name || '';
        const nameB = b.name || b.brand_name || b.licensee_name || '';
        return nameA.localeCompare(nameB);
      }

      if (sortOption === 'za') {
        const nameA = a.name || a.brand_name || a.licensee_name || '';
        const nameB = b.name || b.brand_name || b.licensee_name || '';
        return nameB.localeCompare(nameA);
      }

      // Default A to Z (with Pinned corporate hierarchy for Level 1)
      if (level === 1) {
        const rankA = getPinnedRank(a);
        const rankB = getPinnedRank(b);
        if (rankA !== rankB) return rankA - rankB;
      }

      const nameA = a.name || a.brand_name || a.licensee_name || '';
      const nameB = b.name || b.brand_name || b.licensee_name || '';
      return nameA.localeCompare(nameB);
    });

    return result;
  }, [activeRawList, level, searchQuery, sortOption, period, scaleFactor]);

  // Paginated dataset
  const totalItems = filteredAndSortedList.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / perPage));
  const paginatedList = useMemo(() => {
    const start = (currentPage - 1) * perPage;
    return filteredAndSortedList.slice(start, start + perPage);
  }, [filteredAndSortedList, currentPage, perPage]);

  // Header breadcrumb summary metrics
  const headerMetrics = useMemo(() => {
    if (level === 2 && selectedCompany) {
      const cases = getScaledCases(selectedCompany);
      const bottles = getScaledBottles(selectedCompany);
      return { cases, bottles, title: selectedCompany.name };
    }
    if (level === 3 && selectedBrand) {
      const cases = getScaledCases(selectedBrand);
      const bottles = getScaledBottles(selectedBrand);
      return { cases, bottles, title: selectedBrand.brand_name };
    }
    return null;
  }, [level, selectedCompany, selectedBrand, period, scaleFactor]);

  const getSortOptionLabel = (option: SortOptionValue): string => {
    switch (option) {
      case 'az': return 'A to Z';
      case 'za': return 'Z to A';
      case 'cases_desc': return 'High to Low';
      case 'cases_asc': return 'Low to High';
      default: return 'A to Z';
    }
  };

  return (
    <View style={styles.container}>
      {/* Top Header Bar for Level 2 & Level 3: Back Button */}
      {level > 1 && (
        <View style={styles.topHeaderBar}>
          <TouchableOpacity
            style={styles.backBtn}
            onPress={handleGoBack}
            activeOpacity={0.75}
          >
            <ChevronLeftIcon size={16} color="#0F172A" />
            <Text style={styles.backBtnText}>
              {level === 2 ? 'Brands' : 'Licensees'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Level 2 or Level 3 Header Banner */}
      {level > 1 && headerMetrics && (
        <View style={styles.headerCard}>
          <View style={styles.headerTitleRow}>
            <View style={styles.headerTitleWrapper}>
              <Text style={styles.headerTitle} numberOfLines={1}>
                {headerMetrics.title}
              </Text>
              <Text style={styles.headerSubtitle}>
                {level === 2 ? 'Company Brands' : 'Brand Licensees'}
              </Text>
            </View>

            <View style={styles.headerMetricsRow}>
              <View style={styles.headerMetricCell}>
                <Text style={styles.headerMetricValue}>
                  {formatNumber(headerMetrics.cases)}
                </Text>
                <Text style={styles.headerMetricLabel}>CASES</Text>
              </View>

              <View style={styles.headerMetricCell}>
                <Text style={styles.headerMetricValue}>
                  {formatNumber(headerMetrics.bottles)}
                </Text>
                <Text style={styles.headerMetricLabel}>BOTTLES</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {/* Search Bar & Sort Bar */}
      <View style={styles.searchControlsRow}>
        <View style={styles.searchInputContainer}>
          <SearchIcon size={16} color="#64748B" />
          <TextInput
            style={styles.searchInput}
            placeholder={
              level === 1
                ? 'Search company...'
                : level === 2
                ? 'Search brand...'
                : 'Search licensee...'
            }
            placeholderTextColor="#94A3B8"
            value={searchQuery}
            onChangeText={t => {
              setSearchQuery(t);
              setCurrentPage(1);
            }}
          />
          {searchQuery ? (
            <TouchableOpacity onPress={() => setSearchQuery('')}>
              <XIcon size={16} color="#64748B" />
            </TouchableOpacity>
          ) : null}
        </View>

        <TouchableOpacity
          style={styles.sortButton}
          onPress={() => setShowSortModal(true)}
          activeOpacity={0.7}
        >
          <SwapVertIcon size={15} color="#0F172A" />
          <Text style={styles.sortButtonText}>
            {getSortOptionLabel(sortOption)}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Main Content List */}
      <ScrollView
        style={styles.scrollContainer}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={['#0F172A']}
            tintColor="#0F172A"
          />
        }
      >
        {(loading || (level === 1 && (parentLoading || (companies.length === 0 && !searchQuery)))) ? (
          level === 1 ? <CompanyListSkeletonList count={6} /> : <GroupListSkeletonList count={6} />
        ) : paginatedList.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>
              {searchQuery
                ? 'No matching records found'
                : level === 2
                ? 'No brands recorded for this company'
                : level === 3
                ? 'No licensees found for this brand'
                : 'No companies available'}
            </Text>
          </View>
        ) : (
          paginatedList.map((item, index) => {
            if (level === 1) {
              return (
                <CompanyCard
                  key={item.id || index}
                  company={item}
                  period={period}
                  scaleFactor={scaleFactor}
                  onClick={() => handleSelectCompany(item)}
                />
              );
            }

            if (level === 2) {
              const bCases = getScaledCases(item);
              const bBottles = getScaledBottles(item);
              const licCount = Number(item.selling_licensees_count || 0);
              const licLabel = `${formatNumber(licCount)} ${licCount === 1 ? 'Licensee' : 'Licensees'}`;
              const subtext = item.pack_size ? `${licLabel}  •  ${item.pack_size}` : licLabel;

              return (
                <MetricsCard
                  key={item.brand_id || index}
                  title={item.brand_name || 'Brand'}
                  subtitle={subtext}
                  metrics={[
                    { label: 'CASES', value: formatNumber(bCases) },
                    { label: 'BOTTLES', value: formatNumber(bBottles) },
                  ]}
                  titleIcon={<WineIcon size={16} color="#0F172A" />}
                  onPress={() => handleSelectBrand(item)}
                />
              );
            }

            // Level 3 (Licensee List)
            const lCases = getScaledCases(item);
            const lBottles = getScaledBottles(item);
            const depotLocationPill = item.depot_name
              ? (item.depot_name.startsWith('Depot:') ? item.depot_name : `Depot: ${item.depot_name}`)
              : (selectedHq && selectedHq !== 'All Headquarters' ? `Headquarter: ${selectedHq}` : undefined);

            return (
              <MetricsCard
                key={item.licensee_id || index}
                title={item.licensee_name || 'Licensee'}
                // subtitle={item.group_name ? `Group: ${item.group_name}` : item.shop_name || 'Licensee Detail'}
                locationPill={depotLocationPill}
                pillTheme="blue"
                metrics={[
                  { label: 'CASES', value: formatNumber(lCases) },
                  { label: 'BOTTLES', value: formatNumber(lBottles) },
                ]}
                titleIcon={<UsersIcon size={16} color="#0F172A" />}
              />
            );
          })
        )}
      </ScrollView>

      {/* Pagination Bar */}
      {!loading && totalItems > 0 && (
        <PaginationBar
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={totalItems}
          perPage={perPage}
          onPageChange={setCurrentPage}
          onOpenPerPageModal={() => setShowPerPageModal(true)}
        />
      )}

      {/* Sort Modal */}
      <SortModal
        visible={showSortModal}
        selectedOption={sortOption}
        onSelectOption={(opt: SortOptionValue) => {
          setSortOption(opt);
          setCurrentPage(1);
        }}
        onClose={() => setShowSortModal(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  topHeaderBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    gap: 4,
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  backBtnText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0F172A',
  },
  headerCard: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
    gap: 4,
  },
  backButtonText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0F172A',
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerTitleWrapper: {
    flex: 1,
    marginRight: 10,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0F172A',
  },
  headerSubtitle: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
    marginTop: 2,
  },
  headerMetricsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  headerMetricCell: {
    alignItems: 'flex-end',
  },
  headerMetricValue: {
    fontSize: 14,
    fontWeight: '900',
    color: '#0F172A',
  },
  headerMetricLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: '#94A3B8',
  },
  searchControlsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  searchInputContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    paddingHorizontal: 10,
    height: 38,
    gap: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 13,
    color: '#0F172A',
    paddingVertical: 0,
  },
  sortButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    paddingHorizontal: 10,
    height: 38,
    gap: 6,
  },
  sortButtonText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0F172A',
  },
  scrollContainer: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 12,
    paddingTop: 0,
    paddingBottom: 20,
  },
  emptyContainer: {
    padding: 30,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    fontSize: 13,
    color: '#64748B',
    fontWeight: '600',
    textAlign: 'center',
  },
});
