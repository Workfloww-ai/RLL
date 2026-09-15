import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  FlatList,
  Modal,
  TouchableOpacity,
  TouchableWithoutFeedback,
  BackHandler,
  RefreshControl,
} from 'react-native';
import { Period } from '../../types';
import { FastStorage } from '../../lib/storage';
import { prefetchTopCascadingCards } from '../../lib/prefetchService';
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
  RefreshIcon,
} from '../../components/Icons';

interface GroupsCascadingViewProps {
  period: Period;
  dateFrom: string;
  dateTo: string;
  scaleFactor: number;
  selectedHq?: string;
  onRefresh?: () => Promise<void> | void;
}

export function GroupsCascadingView({
  period,
  dateFrom,
  dateTo,
  scaleFactor,
  selectedHq,
  onRefresh,
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

  // Caching refs & keys
  const cleanHq = selectedHq && selectedHq !== 'All Headquarters' ? selectedHq.trim() : 'All';
  const groupsFastKey = `rll_v2::groups::${period || 'Daily'}::${cleanHq}::${dateTo || 'latest'}`;
  const cacheKey = `${dateFrom}_${dateTo}_${period}_${cleanHq}`;
  const groupsCacheRef = useRef<{ key: string; data: any[] } | null>(null);
  const groupLicenseesCacheRef = useRef<Map<string, any[]>>(new Map());
  const groupBrandsCacheRef = useRef<Map<string, any[]>>(new Map());
  const licenseeBrandsCacheRef = useRef<Map<string, any[]>>(new Map());

  // Data lists - Synchronous instant-paint from FastStorage (0ms on revisit / launch)
  const [groups, setGroups] = useState<any[]>(() => {
    const initHq = selectedHq && selectedHq !== 'All Headquarters' ? selectedHq.trim() : 'All';
    const initKey = `rll_v2::groups::${period || 'Daily'}::${initHq}::${dateTo || 'latest'}`;
    return FastStorage.getObject<any[]>(initKey) || [];
  });
  const [groupBrands, setGroupBrands] = useState<any[]>([]);
  const [licensees, setLicensees] = useState<any[]>([]);
  const [licenseeBrands, setLicenseeBrands] = useState<any[]>([]);

  // Filtering & controls - loading is false if cached data exists
  const [loading, setLoading] = useState<boolean>(groups.length === 0);
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

  // Sync Level 1 & Level 2 on date/period/selectedHq change
  useEffect(() => {
    groupsCacheRef.current = null;
    groupLicenseesCacheRef.current.clear();
    groupBrandsCacheRef.current.clear();
    licenseeBrandsCacheRef.current.clear();
    setLicensees([]);
    setGroupBrands([]);
    setLicenseeBrands([]);

    if (level === 1) {
      // Check FastStorage synchronously for the new filter parameters
      const cached = FastStorage.getObject<any[]>(groupsFastKey);
      if (cached && Array.isArray(cached) && cached.length > 0) {
        setGroups(cached);
        setLoading(false);
        // Silent background refresh
        loadGroups(false);
      } else {
        setGroups([]);
        setLoading(true);
        loadGroups(true);
      }
    } else if (level === 2 && selectedGroup) {
      loadGroupDetails(selectedGroup.group_id);
    } else if (level === 3 && selectedLicensee) {
      loadLicenseeBrands(selectedLicensee.licensee_id);
    }
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
      prefetchTopCascadingCards(groupsCacheRef.current.data, 'groups', period, dateFrom, dateTo, selectedHq).catch(() => {});
      return;
    }

    if (showIndicator) setLoading(true);

    try {
      const data = await fetchCascadingGroups(dateFrom, dateTo, period, selectedHq);
      const result = data || [];
      if (result.length > 0) {
        groupsCacheRef.current = { key: cacheKey, data: result };
        FastStorage.setObject(groupsFastKey, result);
        prefetchTopCascadingCards(result, 'groups', period, dateFrom, dateTo, selectedHq).catch(() => {});
      }
      setGroups(result);
    } catch (e) {
      console.error('Error loading groups:', e);
      if (!groups || groups.length === 0) {
        setGroups([]);
      }
    } finally {
      setLoading(false);
    }
  };

  // 2. Fetch Group Licensees and Group Brands
  const loadGroupDetails = async (groupId: string, forceRefresh = false) => {
    const key = `${groupId}_${cacheKey}`;
    const fastLicsKey = `rll_grp_lic_${key}`;
    const fastBrandsKey = `rll_grp_brands_${key}`;

    if (
      !forceRefresh &&
      groupLicenseesCacheRef.current.has(key) &&
      groupBrandsCacheRef.current.has(key)
    ) {
      setLicensees(groupLicenseesCacheRef.current.get(key) || []);
      setGroupBrands(groupBrandsCacheRef.current.get(key) || []);
      return;
    }

    // Check FastStorage for instant 0ms drill-down
    if (!forceRefresh) {
      const cachedLics = FastStorage.getObject<any[]>(fastLicsKey);
      const cachedBrands = FastStorage.getObject<any[]>(fastBrandsKey);
      if (cachedLics && cachedBrands) {
        groupLicenseesCacheRef.current.set(key, cachedLics);
        groupBrandsCacheRef.current.set(key, cachedBrands);
        setLicensees(cachedLics);
        setGroupBrands(cachedBrands);
        setLoading(false);
        // Silent background refresh
        Promise.all([
          fetchGroupLicensees(groupId, dateFrom, dateTo, period, selectedHq),
          fetchGroupBrands(groupId, dateFrom, dateTo, period, selectedHq),
        ]).then(([licsData, brandsData]) => {
          const lics = licsData || [];
          const gBrands = brandsData || [];
          groupLicenseesCacheRef.current.set(key, lics);
          groupBrandsCacheRef.current.set(key, gBrands);
          if (lics.length > 0) FastStorage.setObject(fastLicsKey, lics);
          if (gBrands.length > 0) FastStorage.setObject(fastBrandsKey, gBrands);
        }).catch(() => {});
        return;
      }
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
      if (lics.length > 0) FastStorage.setObject(fastLicsKey, lics);
      if (gBrands.length > 0) FastStorage.setObject(fastBrandsKey, gBrands);

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
    const fastKey = `rll_lic_brands_${key}`;

    if (!forceRefresh && licenseeBrandsCacheRef.current.has(key)) {
      setLicenseeBrands(licenseeBrandsCacheRef.current.get(key) || []);
      return;
    }

    // Check FastStorage for instant 0ms drill-down
    if (!forceRefresh) {
      const cached = FastStorage.getObject<any[]>(fastKey);
      if (cached && Array.isArray(cached) && cached.length > 0) {
        licenseeBrandsCacheRef.current.set(key, cached);
        setLicenseeBrands(cached);
        setLoading(false);
        // Silent background refresh
        fetchLicenseeBrandSales(licenseeId, dateFrom, dateTo, period, selectedHq)
          .then((data) => {
            const result = data || [];
            licenseeBrandsCacheRef.current.set(key, result);
            if (result.length > 0) FastStorage.setObject(fastKey, result);
          })
          .catch(() => {});
        return;
      }
    }

    setLoading(true);
    try {
      const data = await fetchLicenseeBrandSales(licenseeId, dateFrom, dateTo, period, selectedHq);
      const result = data || [];
      licenseeBrandsCacheRef.current.set(key, result);
      if (result.length > 0) FastStorage.setObject(fastKey, result);
      setLicenseeBrands(result);
    } catch (e) {
      console.error(`Error loading brand sales for licensee ${licenseeId}:`, e);
      setLicenseeBrands([]);
    } finally {
      setLoading(false);
    }
  };

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
      if (onRefresh) {
        await onRefresh();
      }
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
  }, [level, selectedGroup, selectedLicensee, loadGroups, loadGroupDetails, loadLicenseeBrands, onRefresh]);

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

  // Memoized keyExtractor for virtualized list
  const keyExtractor = useCallback(
    (item: any, index: number) => {
      if (level === 1) return `grp-${item.group_id || item.id || index}`;
      if (level === 2) {
        return activeGroupTab === 'brands'
          ? `grp-brand-${item.brand_id || item.id || index}`
          : `grp-lic-${item.licensee_id || item.id || index}`;
      }
      return `lic-brand-${item.brand_id || item.id || index}`;
    },
    [level, activeGroupTab]
  );

  // Memoized item renderer preserving 100% exact design and business logic
  const renderCascadingItem = useCallback(
    ({ item, index }: { item: any; index: number }) => {
      // Level 1: Root Group Card (Image 1)
      if (level === 1) {
        const cases = Number(
          Number(item.total_cases ?? item.cases ?? item.mtd_cases ?? 0).toFixed(2)
        );
        const bottles = Math.round(
          Number(item.total_bottles ?? item.bottles ?? item.mtd_bottles ?? 0)
        );

        return (
          <MetricsCard
            key={`grp-${item.group_id || item.id || 'grp'}-${index}`}
            title={item.group_name}
            subtitle={`${item.total_licensees || 0} Licensee(s)  •  ${item.total_brands || 0} Brand(s)`}
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
        const cases = Number(Number(item.total_cases ?? 0).toFixed(2));
        const bottles = Math.round(Number(item.total_bottles ?? 0));
        const depotPill =
          item.depot_name && item.depot_name !== 'Unassigned'
            ? item.depot_name
            : undefined;

        return (
          <MetricsCard
            key={`grp-brand-${item.brand_id || item.id || 'brand'}-${index}`}
            title={item.brand_name}
            companyBadge={item.company_name || 'Brand Product'}
            metrics={[
              { label: 'Cases', value: cases },
              { label: 'Bottles', value: bottles },
            ]}
            locationPill={depotPill}
            pillTheme="blue"
            scaleFactor={scaleFactor}
          />
        );
      }

      // Level 2: Group Licensees View (Image 3)
      if (level === 2 && activeGroupTab === 'licensees') {
        const cases = Number(Number(item.total_cases ?? 0).toFixed(2));
        const bottles = Math.round(Number(item.total_bottles ?? 0));
        const depotPill =
          item.depot_name && item.depot_name !== 'Unassigned'
            ? item.depot_name
            : item.licensee_depots && item.licensee_depots.length > 0
              ? item.licensee_depots[0]
              : undefined;

        return (
          <MetricsCard
            key={`grp-lic-${item.licensee_id || item.id || 'lic'}-${index}`}
            title={item.licensee_name}
            subtitle={`Trade: ${item.trade || 'Off'}  •  ${item.total_brands || 0} Brand(s)`}
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
        const cases = Number(Number(item.total_cases ?? 0).toFixed(2));
        const bottles = Math.round(Number(item.total_bottles ?? 0));
        const depotPill =
          item.depot_name && item.depot_name !== 'Unassigned'
            ? item.depot_name
            : item.sales_depots && item.sales_depots.length > 0
              ? item.sales_depots[0]
              : undefined;

        return (
          <MetricsCard
            key={`lic-brand-${item.brand_id || item.id || 'brand'}-${index}`}
            title={item.brand_name}
            companyBadge={item.company_name || 'Brand'}
            metrics={[
              { label: 'Cases', value: cases },
              { label: 'Bottles', value: bottles },
            ]}
            locationPill={depotPill}
            pillTheme="blue"
            scaleFactor={scaleFactor}
          />
        );
      }

      return null;
    },
    [level, activeGroupTab, scaleFactor, handleSelectGroup, handleSelectLicensee]
  );

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

        <TouchableOpacity
          style={styles.refreshPillBtn}
          onPress={handleRefresh}
          activeOpacity={0.75}
        >
          <RefreshIcon size={14} color="#0F172A" />
        </TouchableOpacity>

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

      {/* Main Virtualized List Container */}
      {loading && paginatedList.length === 0 ? (
        <View style={styles.scrollList}>
          <GroupListSkeletonList count={5} />
        </View>
      ) : (
        <FlatList
          style={styles.scrollList}
          contentContainerStyle={styles.scrollContent}
          data={paginatedList}
          keyExtractor={keyExtractor}
          renderItem={renderCascadingItem}
          initialNumToRender={10}
          maxToRenderPerBatch={10}
          windowSize={5}
          removeClippedSubviews={true}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={handleRefresh}
              colors={['#0284C7', '#0F172A']}
              tintColor="#0284C7"
            />
          }
          ListEmptyComponent={
            loading || (!searchQuery.trim() && (level === 1 ? groups.length === 0 : level === 2 ? (activeGroupTab === 'brands' ? groupBrands.length === 0 : licensees.length === 0) : licenseeBrands.length === 0)) ? (
              <GroupListSkeletonList count={5} />
            ) : (
              <View style={styles.emptyCard}>
                <Text style={styles.emptyText}>
                  {searchQuery.trim() ? 'No items match your search' : 'No data found'}
                </Text>
              </View>
            )
          }
        />
      )}

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
  refreshPillBtn: {
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    paddingHorizontal: 10,
    height: 40,
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
