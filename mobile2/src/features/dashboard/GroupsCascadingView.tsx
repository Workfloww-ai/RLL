import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  FlatList,
  BackHandler,
} from 'react-native';
import { Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { GroupListSkeletonList } from '../../components/SkeletonLoaders';
import {
  fetchCascadingGroups,
  fetchGroupLicensees,
  fetchLicenseeBrandSales,
} from '../../lib/api';
import {
  SearchIcon,
  ChevronRightIcon,
  ChevronLeftIcon,
  LocationIcon,
  UsersIcon,
  XIcon,
  WineIcon,
  SwapVertIcon,
  ChevronDownIcon,
} from '../../components/Icons';

interface GroupsCascadingViewProps {
  period: Period;
  dateFrom: string;
  dateTo: string;
  scaleFactor: number;
}

export function GroupsCascadingView({
  period,
  dateFrom,
  dateTo,
  scaleFactor,
}: GroupsCascadingViewProps) {
  // Navigation level: 1 = Groups List, 2 = Group Licensees List, 3 = Licensee Brand Sales List
  const [level, setLevel] = useState<1 | 2 | 3>(1);

  // Selected items
  const [selectedGroup, setSelectedGroup] = useState<any>(null);
  const [selectedLicensee, setSelectedLicensee] = useState<any>(null);

  // Data lists
  const [groups, setGroups] = useState<any[]>([]);
  const [licensees, setLicensees] = useState<any[]>([]);
  const [brandSales, setBrandSales] = useState<any[]>([]);

  // Filtering & controls
  const [loading, setLoading] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortOption, setSortOption] = useState<'az' | 'za' | 'cases_desc' | 'cases_asc'>('az');
  const [showSortModal, setShowSortModal] = useState<boolean>(false);
  const [perPage, setPerPage] = useState<number>(15);
  const [showPerPageModal, setShowPerPageModal] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Client-side instant caching
  const cacheKey = `${dateFrom}_${dateTo}_${period}`;
  const groupsCacheRef = React.useRef<{ key: string; data: any[] } | null>(null);
  const licenseesCacheRef = React.useRef<Map<string, any[]>>(new Map());
  const brandSalesCacheRef = React.useRef<Map<string, any[]>>(new Map());

  // Reset cache on date/period change
  useEffect(() => {
    licenseesCacheRef.current.clear();
    brandSalesCacheRef.current.clear();
  }, [dateFrom, dateTo, period]);

  // Reset pagination & search when level changes
  const resetFiltersOnLevelChange = () => {
    setSearchQuery('');
    setSortOption('az');
    setCurrentPage(1);
  };

  // 1. Fetch Level 1: Groups List
  const loadGroups = async (showIndicator = false, forceRefresh = false) => {
    if (!forceRefresh && groupsCacheRef.current && groupsCacheRef.current.key === cacheKey) {
      setGroups(groupsCacheRef.current.data);
      return;
    }

    if (showIndicator && (!groupsCacheRef.current || groupsCacheRef.current.key !== cacheKey)) {
      setLoading(true);
    }

    try {
      const data = await fetchCascadingGroups(dateFrom, dateTo, period);
      const result = data || [];
      groupsCacheRef.current = { key: cacheKey, data: result };
      setGroups(result);
    } catch (e) {
      console.error('Error loading groups:', e);
      setGroups([]);
    } finally {
      if (showIndicator) setLoading(false);
    }
  };

  // 2. Fetch Level 2: Group Licensees List
  const loadGroupLicensees = async (groupId: string, forceRefresh = false) => {
    const key = `${groupId}_${cacheKey}`;
    if (!forceRefresh && licenseesCacheRef.current.has(key)) {
      const cached = licenseesCacheRef.current.get(key) || [];
      setLicensees(cached);
      // Update selected group totals from licensees if needed
      if (cached.length > 0 && selectedGroup) {
        const sumCases = cached.reduce((sum: number, item: any) => sum + (item.total_cases || 0), 0);
        const sumBottles = cached.reduce((sum: number, item: any) => sum + (item.total_bottles || 0), 0);
        setSelectedGroup((prev: any) => ({
          ...prev,
          total_licensees: cached.length,
          total_cases: prev?.total_cases ? prev.total_cases : sumCases,
          total_bottles: prev?.total_bottles ? prev.total_bottles : sumBottles,
        }));
      }
      return;
    }

    setLoading(true);
    try {
      const data = await fetchGroupLicensees(groupId, dateFrom, dateTo, period);
      const result = data || [];
      licenseesCacheRef.current.set(key, result);
      setLicensees(result);

      if (result.length > 0 && selectedGroup) {
        const sumCases = result.reduce((sum: number, item: any) => sum + (item.total_cases || 0), 0);
        const sumBottles = result.reduce((sum: number, item: any) => sum + (item.total_bottles || 0), 0);
        setSelectedGroup((prev: any) => ({
          ...prev,
          total_licensees: result.length,
          total_cases: prev?.total_cases ? prev.total_cases : sumCases,
          total_bottles: prev?.total_bottles ? prev.total_bottles : sumBottles,
        }));
      }
    } catch (e) {
      console.error(`Error loading licensees for group ${groupId}:`, e);
      setLicensees([]);
    } finally {
      setLoading(false);
    }
  };

  // 3. Fetch Level 3: Licensee Brand Sales List
  const loadLicenseeBrandSales = async (licenseeId: string, forceRefresh = false) => {
    const key = `${licenseeId}_${cacheKey}`;
    if (!forceRefresh && brandSalesCacheRef.current.has(key)) {
      const cached = brandSalesCacheRef.current.get(key) || [];
      setBrandSales(cached);
      if (cached.length > 0 && selectedLicensee) {
        const sumCases = cached.reduce((sum: number, item: any) => sum + (item.total_cases || 0), 0);
        const sumBottles = cached.reduce((sum: number, item: any) => sum + (item.total_bottles || 0), 0);
        setSelectedLicensee((prev: any) => ({
          ...prev,
          total_cases: prev?.total_cases ? prev.total_cases : sumCases,
          total_bottles: prev?.total_bottles ? prev.total_bottles : sumBottles,
        }));
      }
      return;
    }

    setLoading(true);
    try {
      const data = await fetchLicenseeBrandSales(licenseeId, dateFrom, dateTo, period);
      const result = data || [];
      brandSalesCacheRef.current.set(key, result);
      setBrandSales(result);

      if (result.length > 0 && selectedLicensee) {
        const sumCases = result.reduce((sum: number, item: any) => sum + (item.total_cases || 0), 0);
        const sumBottles = result.reduce((sum: number, item: any) => sum + (item.total_bottles || 0), 0);
        setSelectedLicensee((prev: any) => ({
          ...prev,
          total_cases: prev?.total_cases ? prev.total_cases : sumCases,
          total_bottles: prev?.total_bottles ? prev.total_bottles : sumBottles,
        }));
      }
    } catch (e) {
      console.error(`Error loading brand sales for licensee ${licenseeId}:`, e);
      setBrandSales([]);
    } finally {
      setLoading(false);
    }
  };

  // Sync Level 1 on mount or date/period changes
  // Debounce ref — avoids firing multiple rapid fetches when date/period changes quickly
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      if (level === 1) {
        loadGroups(true);
      } else if (level === 2 && selectedGroup) {
        loadGroupLicensees(selectedGroup.group_id);
      } else if (level === 3 && selectedLicensee) {
        loadLicenseeBrandSales(selectedLicensee.licensee_id);
      }
    }, 150);
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [dateFrom, dateTo, period]);

  const handleSelectGroup = useCallback((g: any) => {
    setSelectedGroup(g);
    setSelectedLicensee(null);
    setLevel(2);
    resetFiltersOnLevelChange();
    loadGroupLicensees(g.group_id);
  }, []);

  const handleSelectLicensee = useCallback((l: any) => {
    setSelectedLicensee(l);
    setLevel(3);
    resetFiltersOnLevelChange();
    loadLicenseeBrandSales(l.licensee_id);
  }, []);

  const handleGoBack = useCallback(() => {
    if (level === 3) {
      setSelectedLicensee(null);
      setLevel(2);
      resetFiltersOnLevelChange();
    } else if (level === 2) {
      setSelectedGroup(null);
      setLevel(1);
      resetFiltersOnLevelChange();
    }
  }, [level]);

  // Hardware BackHandler for drill-down levels (Level 3 -> Level 2 -> Level 1) and dropdown modals
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



  // Filter and sort active list
  const activeRawList = useMemo(() => {
    if (level === 1) return groups;
    if (level === 2) return licensees;
    return brandSales;
  }, [level, groups, licensees, brandSales]);

  const filteredAndSortedList = useMemo(() => {
    let result = [...activeRawList];

    // Filter search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter((item) => {
        if (level === 1) {
          return (item.group_name || '').toLowerCase().includes(q);
        } else if (level === 2) {
          return (
            (item.licensee_name || '').toLowerCase().includes(q) ||
            (item.trade || '').toLowerCase().includes(q)
          );
        } else {
          return (
            (item.brand_name || '').toLowerCase().includes(q) ||
            (item.company_name || '').toLowerCase().includes(q)
          );
        }
      });
    }

    // Sort
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
  }, [activeRawList, searchQuery, sortOption, level]);

  // Pagination bounds
  const totalItems = filteredAndSortedList.length;
  const totalPages = Math.ceil(totalItems / perPage) || 1;
  const startIndex = (currentPage - 1) * perPage;
  const endIndex = Math.min(startIndex + perPage, totalItems);
  const paginatedList = filteredAndSortedList.slice(startIndex, endIndex);

  return (
    <View style={styles.container}>
      {/* Breadcrumb Header Bar (Level 2 & 3) */}
      {level > 1 && (
        <View style={styles.breadcrumbBar}>
          <TouchableOpacity style={styles.backBtn} onPress={handleGoBack} activeOpacity={0.7}>
            <ChevronLeftIcon size={16} color="#0F172A" />
            <Text style={styles.backBtnText}>Back</Text>
          </TouchableOpacity>

          <View style={styles.breadcrumbPathContainer}>
            <Text style={styles.breadcrumbPathText} numberOfLines={1}>
              <Text style={styles.breadcrumbSeparator}> › </Text>
              <Text style={level === 2 ? styles.breadcrumbActive : styles.breadcrumbMuted}>
                {selectedGroup?.group_name}
              </Text>
              {level === 3 && (
                <>
                  <Text style={styles.breadcrumbSeparator}> › </Text>
                  <Text style={styles.breadcrumbActive} numberOfLines={1}>
                    {selectedLicensee?.licensee_name}
                  </Text>
                </>
              )}
            </Text>
          </View>
        </View>
      )}

      {/* Level 2 Banner: GROUP SELECTED */}
      {level === 2 && selectedGroup && (
        <View style={styles.selectionBanner}>
          <View style={styles.bannerInfo}>
            <Text style={styles.bannerSubtitle}>GROUP SELECTED</Text>
            <Text style={styles.bannerTitle} numberOfLines={1}>
              {selectedGroup.group_name}
            </Text>
          </View>
          <View style={styles.bannerPillRow}>
            <View style={styles.casesPill}>
              <Text style={styles.pillLabel}>CASES</Text>
              <Text style={styles.casesPillValue}>
                {formatNumber(Math.round(selectedGroup.total_cases * scaleFactor))}
              </Text>
            </View>
            <View style={styles.bottlesPill}>
              <Text style={styles.pillLabel}>BOTTLES</Text>
              <Text style={styles.bottlesPillValue}>
                {formatNumber(Math.round(selectedGroup.total_bottles * scaleFactor))}
              </Text>
            </View>
          </View>
        </View>
      )}

      {/* Level 3 Banner: LICENSEE SELECTED */}
      {level === 3 && selectedLicensee && (
        <View style={styles.selectionBanner}>
          <View style={styles.bannerInfo}>
            <Text style={styles.bannerSubtitle}>LICENSEE SELECTED</Text>
            <Text style={styles.bannerTitle} numberOfLines={1}>
              {selectedLicensee.licensee_name}
            </Text>
          </View>
          <View style={styles.bannerPillRow}>
            <View style={styles.casesPill}>
              <Text style={styles.pillLabel}>CASES</Text>
              <Text style={styles.casesPillValue}>
                {formatNumber(Math.round(selectedLicensee.total_cases * scaleFactor))}
              </Text>
            </View>
            <View style={styles.bottlesPill}>
              <Text style={styles.pillLabel}>BOTTLES</Text>
              <Text style={styles.bottlesPillValue}>
                {formatNumber(Math.round(selectedLicensee.total_bottles * scaleFactor))}
              </Text>
            </View>
          </View>
        </View>
      )}

      {/* Search Input Bar & Sort Controls */}
      <View style={styles.searchControlsRow}>
        <View style={styles.searchWrapper}>
          <SearchIcon size={18} color="#94A3B8" />
          <TextInput
            style={styles.searchInput}
            placeholder={
              level === 1
                ? 'Search group...'
                : level === 2
                ? 'Search licensee...'
                : 'Search brand...'
            }
            placeholderTextColor="#94A3B8"
            value={searchQuery}
            onChangeText={(text) => {
              setSearchQuery(text);
              setCurrentPage(1);
            }}
          />
          {searchQuery ? (
            <TouchableOpacity onPress={() => setSearchQuery('')} style={styles.clearBtn}>
              <XIcon size={14} color="#94A3B8" />
            </TouchableOpacity>
          ) : null}
        </View>

        {/* Sort Pill Dropdown */}
        <TouchableOpacity
          style={styles.sortPillBtn}
          onPress={() => setShowSortModal(true)}
          activeOpacity={0.7}
        >
          <View style={{ marginRight: 4 }}>
            <SwapVertIcon size={14} color="#64748B" />
          </View>
          <Text style={styles.sortText}>
            {sortOption === 'az'
              ? 'A-Z (Name)'
              : sortOption === 'za'
              ? 'Z-A (Name)'
              : sortOption === 'cases_desc'
              ? 'Cases (High-Low)'
              : 'Cases (Low-High)'}
          </Text>
          <ChevronDownIcon size={14} color="#94A3B8" />
        </TouchableOpacity>
      </View>

      {/* Items Count & Per-Page Controls Row */}
      <View style={styles.itemsCountRow}>
        <Text style={styles.showingText}>
          Showing {totalItems === 0 ? 0 : startIndex + 1}-{endIndex} of {totalItems} item(s)
        </Text>

        <TouchableOpacity
          style={styles.perPageBtn}
          onPress={() => setShowPerPageModal(true)}
          activeOpacity={0.7}
        >
          <Text style={styles.perPageLabel}>Per page: </Text>
          <Text style={styles.perPageValue}>{perPage}</Text>
          <ChevronDownIcon size={14} color="#94A3B8" />
        </TouchableOpacity>
      </View>

      {/* Main List Container */}
      <ScrollView
        style={styles.scrollList}
        contentContainerStyle={styles.scrollContent}
      >
        {loading ? (
          <GroupListSkeletonList count={5} />
        ) : paginatedList.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyText}>No items found matching criteria</Text>
          </View>
        ) : (
          paginatedList.map((item, index) => {
            // Level 1: Group Card
            if (level === 1) {
              const cases = Math.round((item.total_cases || 0) * scaleFactor);
              const bottles = Math.round((item.total_bottles || 0) * scaleFactor);
              return (
                <TouchableOpacity
                  key={item.group_id || index}
                  style={styles.card}
                  onPress={() => handleSelectGroup(item)}
                  activeOpacity={0.75}
                >
                  <View style={styles.cardHeader}>
                    <View style={styles.titleWrapper}>
                      <Text style={styles.companyName} numberOfLines={1}>
                        {item.group_name}
                      </Text>
                      <View style={styles.licenseeBadgeRow}>
                        <UsersIcon size={12} color="#94A3B8" />
                        <Text style={styles.brandCount}>
                          {item.total_licensees || 0} Licensee(s)
                        </Text>
                      </View>
                    </View>
                    <ChevronRightIcon size={20} color="#94A3B8" />
                  </View>

                  <View style={styles.metricsGrid}>
                    <View style={styles.metricCell}>
                      <Text style={styles.metricLabel}>CASES</Text>
                      <Text style={styles.metricValue}>{formatNumber(cases)}</Text>
                    </View>
                    <View style={styles.metricCell}>
                      <Text style={styles.metricLabel}>BOTTLES</Text>
                      <Text style={styles.metricValue}>{formatNumber(bottles)}</Text>
                    </View>
                  </View>
                </TouchableOpacity>
              );
            }

            // Level 2: Licensee Card
            if (level === 2) {
              const cases = Math.round((item.total_cases || 0) * scaleFactor);
              const bottles = Math.round((item.total_bottles || 0) * scaleFactor);
              const depotName = item.licensee_depots && item.licensee_depots.length > 0 ? item.licensee_depots[0] : null;

              return (
                <TouchableOpacity
                  key={item.licensee_id || index}
                  style={styles.card}
                  onPress={() => handleSelectLicensee(item)}
                  activeOpacity={0.75}
                >
                  <View style={styles.cardHeader}>
                    <View style={styles.titleWrapper}>
                      <Text style={styles.companyName} numberOfLines={1}>
                        {item.licensee_name}
                      </Text>
                      <View style={styles.tradeBadge}>
                        <Text style={styles.tradeBadgeText}>Trade: {item.trade || 'Off'}</Text>
                      </View>
                    </View>
                    <ChevronRightIcon size={20} color="#94A3B8" />
                  </View>

                  <View style={styles.metricsGrid}>
                    <View style={styles.metricCell}>
                      <Text style={styles.metricLabel}>CASES</Text>
                      <Text style={styles.metricValue}>{formatNumber(cases)}</Text>
                    </View>
                    <View style={styles.metricCell}>
                      <Text style={styles.metricLabel}>BOTTLES</Text>
                      <Text style={styles.metricValue}>{formatNumber(bottles)}</Text>
                    </View>
                  </View>

                  {depotName ? (
                    <View style={styles.depotLocationPill}>
                      <LocationIcon size={12} color="#94A3B8" />
                      <Text style={styles.depotLocationText} numberOfLines={1}>
                        {depotName}
                      </Text>
                    </View>
                  ) : null}
                </TouchableOpacity>
              );
            }

            // Level 3: Brand Sales Card
            if (level === 3) {
              const cases = Math.round((item.total_cases || 0) * scaleFactor);
              const bottles = Math.round((item.total_bottles || 0) * scaleFactor);
              const depotName = item.sales_depots && item.sales_depots.length > 0 ? item.sales_depots[0] : null;

              return (
                <View key={item.brand_id || index} style={styles.card}>
                  <View style={styles.cardHeader}>
                    <View style={styles.titleWrapper}>
                      <View style={styles.brandTitleRow}>
                        <View style={{ marginRight: 6 }}>
                          <WineIcon size={14} color="#94A3B8" />
                        </View>
                        <Text style={styles.companyName} numberOfLines={1}>
                          {item.brand_name}
                        </Text>
                      </View>
                      {item.company_name ? (
                        <View style={styles.tradeBadge}>
                          <Text style={styles.tradeBadgeText}>{item.company_name}</Text>
                        </View>
                      ) : null}
                    </View>
                  </View>

                  <View style={styles.metricsGrid}>
                    <View style={styles.metricCell}>
                      <Text style={styles.metricLabel}>CASES</Text>
                      <Text style={styles.metricValue}>{formatNumber(cases)}</Text>
                    </View>
                    <View style={styles.metricCell}>
                      <Text style={styles.metricLabel}>BOTTLES</Text>
                      <Text style={styles.metricValue}>{formatNumber(bottles)}</Text>
                    </View>
                  </View>

                  {depotName ? (
                    <View style={styles.depotLocationPill}>
                      <LocationIcon size={12} color="#0284C7" />
                      <Text style={styles.depotLocationText} numberOfLines={1}>
                        {depotName}
                      </Text>
                    </View>
                  ) : null}
                </View>
              );
            }

            return null;
          })
        )}

        {/* Pagination Controls at Bottom */}
        {totalPages > 1 && (
          <View style={styles.paginationRow}>
            <TouchableOpacity
              style={[styles.pageBtn, currentPage === 1 ? styles.pageBtnDisabled : null]}
              onPress={() => setCurrentPage((p) => Math.max(p - 1, 1))}
              disabled={currentPage === 1}
              activeOpacity={0.7}
            >
              <ChevronLeftIcon size={14} color={currentPage === 1 ? '#94A3B8' : '#0F172A'} />
              <Text style={[styles.pageBtnText, currentPage === 1 ? styles.pageBtnTextDisabled : null]}>
                Prev
              </Text>
            </TouchableOpacity>

            <Text style={styles.pageInfoText}>
              Page <Text style={styles.boldPageText}>{currentPage}</Text> of {totalPages}
            </Text>

            <TouchableOpacity
              style={[styles.pageBtn, currentPage === totalPages ? styles.pageBtnDisabled : null]}
              onPress={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
              disabled={currentPage === totalPages}
              activeOpacity={0.7}
            >
              <Text style={[styles.pageBtnText, currentPage === totalPages ? styles.pageBtnTextDisabled : null]}>
                Next
              </Text>
              <ChevronRightIcon size={14} color={currentPage === totalPages ? '#94A3B8' : '#0F172A'} />
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      {/* Sort Options Modal */}
      <Modal visible={showSortModal} transparent={true} animationType="fade" onRequestClose={() => setShowSortModal(false)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setShowSortModal(false)}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Sort By</Text>
            <TouchableOpacity
              style={[styles.modalItem, sortOption === 'az' ? styles.modalItemActive : null]}
              onPress={() => {
                setSortOption('az');
                setShowSortModal(false);
              }}
            >
              <Text style={[styles.modalItemText, sortOption === 'az' ? styles.modalItemTextActive : null]}>
                A-Z (Name)
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modalItem, sortOption === 'za' ? styles.modalItemActive : null]}
              onPress={() => {
                setSortOption('za');
                setShowSortModal(false);
              }}
            >
              <Text style={[styles.modalItemText, sortOption === 'za' ? styles.modalItemTextActive : null]}>
                Z-A (Name)
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modalItem, sortOption === 'cases_desc' ? styles.modalItemActive : null]}
              onPress={() => {
                setSortOption('cases_desc');
                setShowSortModal(false);
              }}
            >
              <Text style={[styles.modalItemText, sortOption === 'cases_desc' ? styles.modalItemTextActive : null]}>
                Cases (High to Low)
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modalItem, sortOption === 'cases_asc' ? styles.modalItemActive : null]}
              onPress={() => {
                setSortOption('cases_asc');
                setShowSortModal(false);
              }}
            >
              <Text style={[styles.modalItemText, sortOption === 'cases_asc' ? styles.modalItemTextActive : null]}>
                Cases (Low to High)
              </Text>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>

      {/* Per Page Selection Modal */}
      <Modal visible={showPerPageModal} transparent={true} animationType="fade" onRequestClose={() => setShowPerPageModal(false)}>
        <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={() => setShowPerPageModal(false)}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Items Per Page</Text>
            {[10, 15, 25, 50].map((num) => (
              <TouchableOpacity
                key={num}
                style={[styles.modalItem, perPage === num ? styles.modalItemActive : null]}
                onPress={() => {
                  setPerPage(num);
                  setCurrentPage(1);
                  setShowPerPageModal(false);
                }}
              >
                <Text style={[styles.modalItemText, perPage === num ? styles.modalItemTextActive : null]}>
                  {num} items
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  breadcrumbBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#EEF2F6',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
    marginRight: 8,
  },
  backBtnText: {
    fontSize: 13,
    fontWeight: '800',
    color: '#0F172A',
    marginLeft: 4,
  },
  breadcrumbPathContainer: {
    flex: 1,
  },
  breadcrumbPathText: {
    fontSize: 13,
    color: '#64748B',
  },
  breadcrumbSeparator: {
    color: '#94A3B8',
    fontWeight: 'bold',
  },
  breadcrumbActive: {
    fontWeight: '800',
    color: '#0F172A',
  },
  breadcrumbMuted: {
    fontWeight: '500',
    color: '#64748B',
  },
  selectionBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#0A1128',
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 12,
  },
  bannerInfo: {
    flex: 1,
    marginRight: 10,
  },
  bannerSubtitle: {
    fontSize: 9,
    fontWeight: '800',
    color: 'rgba(255, 255, 255, 0.7)',
    letterSpacing: 0.6,
  },
  bannerTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#FFFFFF',
    marginTop: 2,
  },
  bannerPillRow: {
    flexDirection: 'row',
    gap: 8,
  },
  casesPill: {
    backgroundColor: 'rgba(245, 158, 11, 0.18)',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 6,
    alignItems: 'center',
    minWidth: 55,
  },
  casesPillValue: {
    color: '#F59E0B',
    fontSize: 14,
    fontWeight: '900',
    marginTop: 1,
  },
  bottlesPill: {
    backgroundColor: 'rgba(56, 189, 248, 0.18)',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 6,
    alignItems: 'center',
    minWidth: 55,
  },
  bottlesPillValue: {
    color: '#38BDF8',
    fontSize: 14,
    fontWeight: '900',
    marginTop: 1,
  },
  pillLabel: {
    fontSize: 8,
    fontWeight: '800',
    color: 'rgba(255, 255, 255, 0.7)',
    letterSpacing: 0.5,
  },
  searchControlsRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 10,
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
    height: 44,
  },
  searchInput: {
    flex: 1,
    fontSize: 13,
    color: '#0F172A',
    fontWeight: '500',
    paddingVertical: 0,
    marginLeft: 6,
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
    height: 44,
  },
  sortIcon: {
    fontSize: 13,
    color: '#64748B',
    marginRight: 4,
  },
  sortText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0F172A',
  },
  dropdownArrow: {
    fontSize: 10,
    color: '#94A3B8',
    marginLeft: 4,
  },
  itemsCountRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
    paddingHorizontal: 4,
  },
  showingText: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
  },
  perPageBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  perPageLabel: {
    fontSize: 11,
    color: '#64748B',
  },
  perPageValue: {
    fontSize: 11,
    fontWeight: '800',
    color: '#0F172A',
  },
  perPageArrow: {
    fontSize: 9,
    color: '#94A3B8',
  },
  scrollList: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 24,
  },
  loadingBox: {
    padding: 30,
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 12,
    color: '#64748B',
    marginTop: 8,
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
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 14,
    marginBottom: 10,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  titleWrapper: {
    flex: 1,
    marginRight: 8,
  },
  companyName: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
    letterSpacing: -0.2,
  },
  brandTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  brandEmoji: {
    fontSize: 14,
    marginRight: 6,
  },
  licenseeBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 3,
  },
  brandCount: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
    marginLeft: 4,
  },
  tradeBadge: {
    alignSelf: 'flex-start',
    backgroundColor: '#F1F5F9',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 2,
    marginTop: 4,
  },
  tradeBadgeText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#475569',
  },
  metricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 8,
    marginTop: 4,
    borderWidth: 1,
    borderColor: '#F1F5F9',
  },
  metricCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricLabel: {
    fontSize: 8,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  metricValue: {
    fontSize: 14,
    fontWeight: '900',
    color: '#0F172A',
    marginTop: 2,
  },
  depotLocationPill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#F0F9FF',
    borderWidth: 1,
    borderColor: '#BAE6FD',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginTop: 10,
  },
  depotPinIcon: {
    fontSize: 10,
    marginRight: 4,
  },
  depotLocationText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#0284C7',
  },
  paginationRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginTop: 10,
    marginBottom: 20,
  },
  pageBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#EEF2F6',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 7,
    gap: 4,
  },
  pageBtnDisabled: {
    backgroundColor: '#F1F5F9',
    opacity: 0.5,
  },
  pageBtnText: {
    fontSize: 12,
    fontWeight: '800',
    color: '#0F172A',
  },
  pageBtnTextDisabled: {
    color: '#94A3B8',
  },
  pageInfoText: {
    fontSize: 13,
    color: '#475569',
  },
  boldPageText: {
    fontWeight: '900',
    color: '#0F172A',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContent: {
    width: '100%',
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 16,
    maxHeight: '60%',
  },
  modalTitle: {
    fontSize: 13,
    fontWeight: 'bold',
    color: '#0F2042',
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  modalItem: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 10,
    marginBottom: 4,
  },
  modalItemActive: {
    backgroundColor: '#EEF2F6',
  },
  modalItemText: {
    fontSize: 12,
    color: '#64748B',
    fontWeight: '600',
  },
  modalItemTextActive: {
    color: '#0F2042',
    fontWeight: 'bold',
  },
});
