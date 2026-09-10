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
  RefreshIcon,
} from '../../components/Icons';

import { useTenant } from '../../context/TenantContext';

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
  onRefresh?: () => Promise<void> | void;
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
  onRefresh,
}: CompanyCascadingViewProps) {
  const { config } = useTenant();
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

  // Derive current selectedCompany from parent companies list so it is ALWAYS 100% in sync with the latest date/period/HQ metrics!
  const activeSelectedCompany = useMemo(() => {
    if (!selectedCompany) return null;
    const normKey = getNormalizedCompanyKey(selectedCompany);
    return companies.find((c) => getNormalizedCompanyKey(c) === normKey) || selectedCompany;
  }, [selectedCompany, companies, getNormalizedCompanyKey]);

  // Sync details on date/period/HQ changes
  useEffect(() => {
    companyBrandsCacheRef.current.clear();
    brandLicenseesCacheRef.current.clear();
    if (level === 2 && activeSelectedCompany) {
      loadCompanyBrands(activeSelectedCompany, true);
    } else if (level === 3 && selectedBrand) {
      loadBrandLicensees(selectedBrand.brand_id, true);
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
    loadBrandLicensees(brand.brand_id, true);
  };

  const handleGoBack = useCallback(() => {
    if (level === 3) {
      setSelectedBrand(null);
      setLevel(2);
      resetFilters();

      if (activeSelectedCompany) {
        const normKey = getNormalizedCompanyKey(activeSelectedCompany);
        const key = `${normKey}_${cacheKey}`;
        if (companyBrandsCacheRef.current.has(key)) {
          setCompanyBrands(companyBrandsCacheRef.current.get(key) || []);
        } else {
          loadCompanyBrands(activeSelectedCompany);
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
  }, [level, activeSelectedCompany, cacheKey, onClearParentSelectedCompany, getNormalizedCompanyKey]);

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
      if (onRefresh) {
        await onRefresh();
      }
      if (level === 2 && activeSelectedCompany) {
        await loadCompanyBrands(activeSelectedCompany, true);
      } else if (level === 3 && selectedBrand?.brand_id) {
        await loadBrandLicensees(selectedBrand.brand_id, true);
      }
    } catch (err) {
      console.error('Error refreshing CompanyCascadingView:', err);
    } finally {
      setRefreshing(false);
    }
  }, [level, activeSelectedCompany, selectedBrand, onRefresh]);

  // Helper to extract cases and bottles respecting period
  const getScaledCases = (item: any): number => {
    const rawCases = Number(
      item.data?.[period]?.cases ??
      item.cases ??
      item.total_cases ??
      item.mtd_cases ??
      0
    );
    return Number((rawCases * scaleFactor).toFixed(2));
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

  // Pinned Rank helper for Companies (Dynamic tenant pinning or purely alphabetical)
  const getPinnedRank = (item: any): number => {
    const id = String(item.id || '').toLowerCase().trim();
    const name = String(item.name || item.company_name || '').toLowerCase().trim();
    const pinnedTarget = (config?.pinnedCompanyName || '').toLowerCase().trim();

    if (pinnedTarget && (name === pinnedTarget || name.includes(pinnedTarget) || id === pinnedTarget)) {
      return 1;
    }
    if (item.isPinned) return 2;
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
    if (level === 2 && activeSelectedCompany) {
      const cases = getScaledCases(activeSelectedCompany);
      const bottles = getScaledBottles(activeSelectedCompany);
      return { cases, bottles, title: activeSelectedCompany.name };
    }
    if (level === 3 && selectedBrand) {
      const cases = getScaledCases(selectedBrand);
      const bottles = getScaledBottles(selectedBrand);
      return { cases, bottles, title: selectedBrand.brand_name };
    }
    return null;
  }, [level, activeSelectedCompany, selectedBrand, period, scaleFactor]);

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
      {/* Level 2 or Level 3 Header Banner - Single Compact Row Layout */}
      {level > 1 && headerMetrics && (
        <View style={styles.headerCard}>
          <TouchableOpacity
            style={styles.headerLeftTitleBlock}
            onPress={handleGoBack}
            activeOpacity={0.7}
          >
            <ChevronLeftIcon size={18} color="#0F172A" style={styles.headerBackIcon} />
            <Text style={styles.headerTitle} numberOfLines={2}>
              {headerMetrics.title}
            </Text>
          </TouchableOpacity>

          <View style={styles.headerRightMetricsBlock}>
            <View style={styles.metricBadgePrimary}>
              <Text style={styles.metricValuePrimary}>{formatNumber(headerMetrics.cases)}</Text>
              <Text style={styles.metricLabelPrimary}>CASES</Text>
            </View>
            <View style={styles.metricBadgeSecondary}>
              <Text style={styles.metricValueSecondary}>{formatNumber(headerMetrics.bottles)}</Text>
              <Text style={styles.metricLabelSecondary}>BTL</Text>
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
          style={styles.refreshButton}
          onPress={handleRefresh}
          activeOpacity={0.7}
        >
          <RefreshIcon size={15} color="#0F172A" />
        </TouchableOpacity>

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
                  key={`company-${item.id || item.name || 'comp'}-${index}`}
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
                  key={`brand-${item.brand_id || item.id || item.brand_name || 'brand'}-${index}`}
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
                key={`licensee-${item.licensee_id || item.id || item.licensee_name || 'lic'}-${index}`}
                title={item.licensee_name || 'Licensee'}
                subtitle={`Trade: ${item.trade || item.Trade || 'Off'}`}
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
  headerCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  headerLeftTitleBlock: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginRight: 8,
  },
  headerBackIcon: {
    marginRight: 4,
    marginTop: 1,
  },
  headerTitle: {
    flex: 1,
    fontSize: 11.5,
    fontWeight: '700',
    color: '#0F172A',
    lineHeight: 15.5,
    flexWrap: 'wrap',
  },
  headerRightMetricsBlock: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  metricBadgePrimary: {
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    alignItems: 'center',
    minWidth: 54,
  },
  metricValuePrimary: {
    fontSize: 11.5,
    fontWeight: '800',
    color: '#1D4ED8',
  },
  metricLabelPrimary: {
    fontSize: 8,
    fontWeight: '700',
    color: '#3B82F6',
  },
  metricBadgeSecondary: {
    backgroundColor: '#F8FAFC',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    alignItems: 'center',
    minWidth: 46,
  },
  metricValueSecondary: {
    fontSize: 11.5,
    fontWeight: '800',
    color: '#0F172A',
  },
  metricLabelSecondary: {
    fontSize: 8,
    fontWeight: '700',
    color: '#64748B',
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
  refreshButton: {
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    paddingHorizontal: 10,
    height: 38,
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
