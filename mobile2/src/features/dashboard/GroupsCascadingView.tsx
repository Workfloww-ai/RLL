import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  ScrollView,
  Modal,
  TouchableOpacity,
  TouchableWithoutFeedback,
  BackHandler,
  Animated,
  RefreshControl,
} from 'react-native';
import { Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { GroupListSkeletonList } from '../../components/SkeletonLoaders';
import {
  fetchCascadingGroups,
  fetchGroupBrands,
  fetchGroupLicensees,
  fetchLicenseeBrandSales,
} from '../../lib/api';
import { MetricsCard } from '../../components/MetricsCard';
import { SegmentedTabs, GroupTabType } from '../../components/SegmentedTabs';
import { PaginationBar } from '../../components/PaginationBar';
import { SortModal, SortOptionValue } from '../../components/SortModal';
import {
  SwapVertIcon,
  ChevronDownIcon,
  XIcon,
  SearchIcon,
  ChevronLeftIcon,
  WineIcon,
  UsersIcon,
} from '../../components/Icons';

interface GroupsCascadingViewProps {
  period: Period;
  dateFrom: string;
  dateTo: string;
  scaleFactor: number;
  selectedHq?: string;
}

export function GroupsCascadingView({
  period,
  dateFrom,
  dateTo,
  scaleFactor,
  selectedHq,
}: GroupsCascadingViewProps) {
  // Navigation level:
  // Level 1 = Groups List
  // Level 2 = Group Detail (Brands Tab & Licensees Tab)
  // Level 3 = Licensee Detail (Brands for selected licensee)
  const [level, setLevel] = useState<1 | 2 | 3>(1);
  const [activeGroupTab, setActiveGroupTab] = useState<GroupTabType>('brands');

  // Selected items
  const [selectedGroup, setSelectedGroup] = useState<any>(null);
  const [selectedLicensee, setSelectedLicensee] = useState<any>(null);

  // Data lists
  const [groups, setGroups] = useState<any[]>([]);
  const [groupBrands, setGroupBrands] = useState<any[]>([]);
  const [licensees, setLicensees] = useState<any[]>([]);
  const [licenseeBrands, setLicenseeBrands] = useState<any[]>([]);

  // Filtering & controls
  const [loading, setLoading] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortOption, setSortOption] = useState<SortOptionValue>('az');
  const [showSortModal, setShowSortModal] = useState<boolean>(false);
  const [perPage, setPerPage] = useState<number>(15);
  const [showPerPageModal, setShowPerPageModal] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);

  const scaledFontSize = useCallback(
    (base: number) => Math.round(base * scaleFactor),
    [scaleFactor]
  );

  // Caching refs
  const cacheKey = `${dateFrom}_${dateTo}_${period}_${selectedHq || 'All'}`;
  const groupsCacheRef = useRef<{ key: string; data: any[] } | null>(null);
  const groupLicenseesCacheRef = useRef<Map<string, any[]>>(new Map());
  const groupBrandsCacheRef = useRef<Map<string, any[]>>(new Map());
  const licenseeBrandsCacheRef = useRef<Map<string, any[]>>(new Map());

  // Reset cache and set loading state on date/period/selectedHq change
  useEffect(() => {
    groupsCacheRef.current = null;
    groupLicenseesCacheRef.current.clear();
    groupBrandsCacheRef.current.clear();
    licenseeBrandsCacheRef.current.clear();
    setLicensees([]);
    setGroupBrands([]);
    setLicenseeBrands([]);
    setLoading(true);
  }, [dateFrom, dateTo, period, selectedHq]);

  // Reset search and pagination
  const resetFilters = () => {
    setSearchQuery('');
    setSortOption('az');
    setCurrentPage(1);
  };

  // 1. Fetch Level 1: Groups List
  const loadGroups = async (showIndicator = true, forceRefresh = false) => {
    if (
      !forceRefresh &&
      groupsCacheRef.current &&
      groupsCacheRef.current.key === cacheKey &&
      groupsCacheRef.current.data.length > 0
    ) {
      setGroups(groupsCacheRef.current.data);
      setLoading(false);
      return;
    }

    setLoading(true);

    try {
      const data = await fetchCascadingGroups(dateFrom, dateTo, period, selectedHq);
      const result = data || [];
      if (result.length > 0) {
        groupsCacheRef.current = { key: cacheKey, data: result };
      }
      setGroups(result);
    } catch (e) {
      console.error('Error loading groups:', e);
      setGroups([]);
    } finally {
      setLoading(false);
    }
  };

  // 2. Fetch Group Licensees and Group Brands
  const loadGroupDetails = async (groupId: string, forceRefresh = false) => {
    const key = `${groupId}_${cacheKey}`;

    if (
      !forceRefresh &&
      groupLicenseesCacheRef.current.has(key) &&
      groupBrandsCacheRef.current.has(key)
    ) {
      setLicensees(groupLicenseesCacheRef.current.get(key) || []);
      setGroupBrands(groupBrandsCacheRef.current.get(key) || []);
      return;
    }

    setLoading(true);
    try {
      // Fetch licensees and brand sales for group concurrently
      const [licsData, brandsData] = await Promise.all([
        fetchGroupLicensees(groupId, dateFrom, dateTo, period, selectedHq),
        fetchGroupBrands(groupId, dateFrom, dateTo, period, selectedHq),
      ]);

      const lics = licsData || [];
      const gBrands = brandsData || [];

      groupLicenseesCacheRef.current.set(key, lics);
      groupBrandsCacheRef.current.set(key, gBrands);

      setLicensees(lics);
      setGroupBrands(gBrands);
    } catch (e) {
      console.error(`Error loading group details for ${groupId}:`, e);
      setLicensees([]);
      setGroupBrands([]);
    } finally {
      setLoading(false);
    }
  };

  // 3. Fetch Licensee Brands (Level 3)
  const loadLicenseeBrands = async (licenseeId: string, forceRefresh = false) => {
    const key = `${licenseeId}_${cacheKey}`;
    if (!forceRefresh && licenseeBrandsCacheRef.current.has(key)) {
      setLicenseeBrands(licenseeBrandsCacheRef.current.get(key) || []);
      return;
    }

    setLoading(true);
    try {
      const data = await fetchLicenseeBrandSales(licenseeId, dateFrom, dateTo, period, selectedHq);
      const result = data || [];
      licenseeBrandsCacheRef.current.set(key, result);
      setLicenseeBrands(result);
    } catch (e) {
      console.error(`Error loading brand sales for licensee ${licenseeId}:`, e);
      setLicenseeBrands([]);
    } finally {
      setLoading(false);
    }
  };

  // Sync Level 1 on mount or date/period/HQ changes
  useEffect(() => {
    if (level === 1) {
      loadGroups(true);
    } else if (level === 2 && selectedGroup) {
      loadGroupDetails(selectedGroup.group_id);
    } else if (level === 3 && selectedLicensee) {
      loadLicenseeBrands(selectedLicensee.licensee_id);
    }
  }, [dateFrom, dateTo, period, selectedHq]);

  // Selection handlers
  const handleSelectGroup = (g: any) => {
    setSelectedGroup(g);
    setSelectedLicensee(null);
    setActiveGroupTab('brands'); // Default to Brands tab as shown in Image 2!
    setLevel(2);
    resetFilters();
    loadGroupDetails(g.group_id);
  };

  const handleSelectLicensee = (l: any) => {
    setSelectedLicensee(l);
    setLevel(3);
    resetFilters();
    loadLicenseeBrands(l.licensee_id);
  };

  const handleGoBack = useCallback(() => {
    if (level === 3) {
      // Return from Licensee Brands view to Group Licensees view (Image 3)
      setSelectedLicensee(null);
      setLevel(2);
      setActiveGroupTab('licensees');
      resetFilters();
    } else if (level === 2) {
      // Return from Group Detail view to Root Groups view (Image 1)
      setSelectedGroup(null);
      setSelectedLicensee(null);
      setLevel(1);
      resetFilters();
    }
  }, [level]);

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
    groupsCacheRef.current = null;
    groupLicenseesCacheRef.current.clear();
    groupBrandsCacheRef.current.clear();
    licenseeBrandsCacheRef.current.clear();
    try {
      if (level === 1) {
        await loadGroups(true);
      } else if (level === 2 && selectedGroup?.group_id) {
        await loadGroupDetails(selectedGroup.group_id, true);
      } else if (level === 3 && selectedLicensee?.licensee_id) {
        await loadLicenseeBrands(selectedLicensee.licensee_id, true);
      }
    } catch (err) {
      console.error('Error refreshing GroupsCascadingView:', err);
    } finally {
      setRefreshing(false);
    }
  }, [level, selectedGroup, selectedLicensee, loadGroups, loadGroupDetails, loadLicenseeBrands]);

  // Determine active dataset for current view state
  const activeRawList = useMemo(() => {
    if (level === 1) return groups;
    if (level === 2) {
      return activeGroupTab === 'brands' ? groupBrands : licensees;
    }
    return licenseeBrands; // Level 3
  }, [level, activeGroupTab, groups, groupBrands, licensees, licenseeBrands]);

  // Filter & Sort active list
  const filteredAndSortedList = useMemo(() => {
    let result = [...activeRawList];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter((item) => {
        const name = (
          item.group_name ||
          item.licensee_name ||
          item.brand_name ||
          ''
        ).toLowerCase();
        const sub = (
          item.trade ||
          item.company_name ||
          ''
        ).toLowerCase();
        return name.includes(q) || sub.includes(q);
      });
    }

    result.sort((a, b) => {
      const nameA = (a.group_name || a.licensee_name || a.brand_name || '').toLowerCase();
      const nameB = (b.group_name || b.licensee_name || b.brand_name || '').toLowerCase();
      const casesA = Number(a.total_cases || 0);
      const casesB = Number(b.total_cases || 0);

      if (sortOption === 'az') return nameA.localeCompare(nameB);
      if (sortOption === 'za') return nameB.localeCompare(nameA);
      if (sortOption === 'cases_desc') return casesB - casesA;
      if (sortOption === 'cases_asc') return casesA - casesB;
      return 0;
    });

    return result;
  }, [activeRawList, searchQuery, sortOption]);

  // Pagination calculations
  const totalItems = filteredAndSortedList.length;
  const totalPages = Math.ceil(totalItems / perPage) || 1;
  const startIndex = (currentPage - 1) * perPage;
  const endIndex = Math.min(startIndex + perPage, totalItems);
  const paginatedList = filteredAndSortedList.slice(startIndex, endIndex);

  // Search input placeholder calculation
  const searchPlaceholder = useMemo(() => {
    if (level === 1) return 'Search group...';
    if (level === 2) {
      return activeGroupTab === 'brands' ? 'Search group brands...' : 'Search licensee...';
    }
    // Level 3
    const firstName = selectedLicensee?.licensee_name?.split(' ')[0] || 'licensee';
    return `Search brands in ${firstName}...`;
  }, [level, activeGroupTab, selectedLicensee]);

  return (
    <View style={styles.container}>
      {/* Top Header Bar for Level 2 & Level 3: [ Back Button ] + [ Segmented Tabs ] */}
      {level > 1 && (
        <View style={styles.topHeaderBar}>
          <TouchableOpacity
            style={styles.backBtn}
            onPress={handleGoBack}
            activeOpacity={0.75}
          >
            <ChevronLeftIcon size={scaledFontSize(16)} color="#0F172A" />
            <Text style={[styles.backBtnText, { fontSize: scaledFontSize(13) }]}>
              Back
            </Text>
          </TouchableOpacity>

          <SegmentedTabs
            tabs={[
              { key: 'brands', label: 'Brands', icon: <WineIcon /> },
              { key: 'licensees', label: 'Licensees', icon: <UsersIcon /> },
            ]}
            activeTabKey={activeGroupTab}
            onTabChange={(tabKey) => {
              setActiveGroupTab(tabKey as any);
              if (level === 3 && tabKey === 'brands') {
                setLevel(2);
                setSelectedLicensee(null);
              }
              resetFilters();
            }}
            scaleFactor={scaleFactor}
          />
        </View>
      )}

      {/* Filter Row: Search Bar & Sort Pill (Matching Company Screen Design) */}
      <View style={styles.searchControlsRow}>
        <View style={styles.searchWrapper}>
          <View style={{ marginRight: 6 }}>
            <SearchIcon size={15} color="#94A3B8" />
          </View>
          <TextInput
            style={styles.searchInput}
            placeholder={searchPlaceholder}
            placeholderTextColor="#94A3B8"
            value={searchQuery}
            onChangeText={(text) => {
              setSearchQuery(text);
              setCurrentPage(1);
            }}
          />
          {searchQuery ? (
            <TouchableOpacity
              onPress={() => {
                setSearchQuery('');
                setCurrentPage(1);
              }}
              style={styles.clearBtn}
            >
              <XIcon size={12} color="#94A3B8" />
            </TouchableOpacity>
          ) : null}
        </View>

        {/* Sort Pill Button */}
        <TouchableOpacity
          style={styles.sortPillBtn}
          onPress={() => setShowSortModal(true)}
          activeOpacity={0.75}
        >
          <SwapVertIcon size={14} color="#64748B" />
          <Text style={styles.sortText} numberOfLines={1}>
            {sortOption === 'az'
              ? 'Name (A to Z)'
              : sortOption === 'za'
                ? 'Name (Z to A)'
                : sortOption === 'cases_desc'
                  ? 'Cases: (High to Low)'
                  : 'Cases: (Low to High)'}
          </Text>
          <ChevronDownIcon size={14} color="#94A3B8" />
        </TouchableOpacity>
      </View>

      {/* Main List Container */}
      <ScrollView
        style={styles.scrollList}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={['#0284C7', '#0F172A']}
            tintColor="#0284C7"
          />
        }
      >
        {loading ? (
          <GroupListSkeletonList count={5} />
        ) : paginatedList.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyText}>
              {searchQuery.trim() ? 'No items match your search' : 'No data found'}
            </Text>
          </View>
        ) : (
          paginatedList.map((item, index) => {
            // Level 1: Root Group Card (Image 1)
            if (level === 1) {
              const cases = Math.round(
                Number(item.total_cases ?? item.cases ?? item.mtd_cases ?? 0)
              );
              const bottles = Math.round(
                Number(item.total_bottles ?? item.bottles ?? item.mtd_bottles ?? 0)
              );

              return (
                <MetricsCard
                  key={item.group_id || index}
                  title={item.group_name}
                  subtitle={
                    <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' }}>
                      <UsersIcon size={scaledFontSize(12)} color="#64748B" />
                      <Text style={{ fontSize: scaledFontSize(12), color: '#64748B', fontWeight: '500', marginLeft: 3 }}>
                        {`${item.total_licensees || 0} Licensee(s)`}
                      </Text>
                      <Text style={{ fontSize: scaledFontSize(12), color: '#64748B', fontWeight: '500' }}>
                        {'  •  '}
                      </Text>
                      <WineIcon size={scaledFontSize(12)} color="#64748B" />
                      <Text style={{ fontSize: scaledFontSize(12), color: '#64748B', fontWeight: '500', marginLeft: 3 }}>
                        {`${item.total_brands || 0} Brand(s)`}
                      </Text>
                    </View>
                  }
                  metrics={[
                    { label: 'Cases', value: cases },
                    { label: 'Bottles', value: bottles },
                  ]}
                  pillTheme="blue"
                  onPress={() => handleSelectGroup(item)}
                  scaleFactor={scaleFactor}
                />
              );
            }

            // Level 2: Group Brands View (Image 2)
            if (level === 2 && activeGroupTab === 'brands') {
              const cases = Math.round(Number(item.total_cases ?? 0));
              const bottles = Math.round(Number(item.total_bottles ?? 0));
              const depotPill =
                item.depot_name && item.depot_name !== 'Unassigned'
                  ? item.depot_name
                  : undefined;

              return (
                <MetricsCard
                  key={item.brand_id || index}
                  title={item.brand_name}
                  titleIcon={<WineIcon size={16} color="#0F172A" />}
                  companyBadge={item.company_name || 'Brand Product'}
                  metrics={[
                    { label: 'Cases', value: cases },
                    { label: 'Bottles', value: bottles },
                  ]}
                  locationPill={depotPill}
                  pillTheme="red"
                  scaleFactor={scaleFactor}
                />
              );
            }

            // Level 2: Group Licensees View (Image 3)
            if (level === 2 && activeGroupTab === 'licensees') {
              const cases = Math.round(Number(item.total_cases ?? 0));
              const bottles = Math.round(Number(item.total_bottles ?? 0));
              const depotPill =
                item.depot_name && item.depot_name !== 'Unassigned'
                  ? item.depot_name
                  : item.licensee_depots && item.licensee_depots.length > 0
                    ? item.licensee_depots[0]
                    : undefined;

              return (
                <MetricsCard
                  key={item.licensee_id || index}
                  title={item.licensee_name}
                  subtitle={
                    <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' }}>
                      <Text style={{ fontSize: scaledFontSize(12), color: '#64748B', fontWeight: '500' }}>
                        {`Trade: ${item.trade || 'Off'}`}
                      </Text>
                      <Text style={{ fontSize: scaledFontSize(12), color: '#64748B', fontWeight: '500' }}>
                        {'  •  '}
                      </Text>
                      <WineIcon size={scaledFontSize(12)} color="#64748B" />
                      <Text style={{ fontSize: scaledFontSize(12), color: '#64748B', fontWeight: '500', marginLeft: 3 }}>
                        {`${item.total_brands || 0} Brand(s)`}
                      </Text>
                    </View>
                  }
                  metrics={[
                    { label: 'Cases', value: cases },
                    { label: 'Bottles', value: bottles },
                  ]}
                  locationPill={depotPill}
                  pillTheme="blue"
                  onPress={() => handleSelectLicensee(item)}
                  scaleFactor={scaleFactor}
                />
              );
            }

            // Level 3: Licensee Brands View (Image 4)
            if (level === 3) {
              const cases = Math.round(Number(item.total_cases ?? 0));
              const bottles = Math.round(Number(item.total_bottles ?? 0));
              const depotPill =
                item.depot_name && item.depot_name !== 'Unassigned'
                  ? item.depot_name
                  : item.sales_depots && item.sales_depots.length > 0
                    ? item.sales_depots[0]
                    : undefined;

              return (
                <MetricsCard
                  key={item.brand_id || index}
                  title={item.brand_name}
                  titleIcon={<WineIcon size={16} color="#0F172A" />}
                  companyBadge={item.company_name || 'Brand'}
                  metrics={[
                    { label: 'Cases', value: cases },
                    { label: 'Bottles', value: bottles },
                  ]}
                  locationPill={depotPill}
                  pillTheme="red"
                  scaleFactor={scaleFactor}
                />
              );
            }

            return null;
          })
        )}
      </ScrollView>

      {/* Pagination Bar */}
      <PaginationBar
        currentPage={currentPage}
        totalPages={totalPages}
        totalItems={totalItems}
        perPage={perPage}
        onPageChange={(page) => setCurrentPage(page)}
        onOpenPerPageModal={() => setShowPerPageModal(true)}
        scaleFactor={scaleFactor}
      />

      {/* Reusable SortModal */}
      <SortModal
        visible={showSortModal}
        onClose={() => setShowSortModal(false)}
        selectedOption={sortOption}
        onSelectOption={(val) => {
          setSortOption(val);
          setCurrentPage(1);
        }}
        scaleFactor={scaleFactor}
      />

      {/* Per Page Modal */}
      <Modal
        visible={showPerPageModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowPerPageModal(false)}
      >
        <TouchableWithoutFeedback onPress={() => setShowPerPageModal(false)}>
          <View style={styles.modalOverlay}>
            <TouchableWithoutFeedback>
              <View style={styles.perPageModalCard}>
                <View style={styles.modalHeader}>
                  <Text style={styles.modalTitle}>Items Per Page</Text>
                  <TouchableOpacity onPress={() => setShowPerPageModal(false)}>
                    <XIcon size={18} color="#64748B" />
                  </TouchableOpacity>
                </View>
                {[15, 25, 50, 100].map((num) => (
                  <TouchableOpacity
                    key={num}
                    style={[
                      styles.perPageOptionRow,
                      perPage === num && styles.perPageOptionSelected,
                    ]}
                    onPress={() => {
                      setPerPage(num);
                      setCurrentPage(1);
                      setShowPerPageModal(false);
                    }}
                  >
                    <Text
                      style={[
                        styles.perPageOptionText,
                        perPage === num && styles.perPageOptionTextSelected,
                      ]}
                    >
                      {num} items
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </TouchableWithoutFeedback>
          </View>
        </TouchableWithoutFeedback>
      </Modal>
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
    gap: 10,
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
    fontWeight: '700',
    color: '#0F172A',
  },
  searchControlsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: 'transparent',
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
    fontWeight: '500',
    color: '#0F172A',
    paddingVertical: 0,
    margin: 0,
  },
  clearBtn: {
    padding: 4,
  },
  sortPillBtn: {
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
  sortText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0F2042',
  },
  showingInfoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  showingText: {
    color: '#64748B',
    fontWeight: '500',
  },
  perPageTrigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  perPageLabelText: {
    color: '#64748B',
    fontWeight: '500',
  },
  perPagePill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    gap: 4,
  },
  perPageValueText: {
    color: '#0F172A',
    fontWeight: '700',
  },
  scrollList: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 12,
    paddingBottom: 16,
  },
  emptyCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 24,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    marginTop: 20,
  },
  emptyText: {
    color: '#64748B',
    fontSize: 14,
    fontWeight: '500',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  perPageModalCard: {
    width: '100%',
    maxWidth: 320,
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  modalTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#0F172A',
  },
  perPageOptionRow: {
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 10,
    marginBottom: 4,
  },
  perPageOptionSelected: {
    backgroundColor: '#F0F9FF',
  },
  perPageOptionText: {
    color: '#334155',
    fontSize: 14,
    fontWeight: '500',
  },
  perPageOptionTextSelected: {
    color: '#0284C7',
    fontWeight: '700',
  },
});
