import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Modal,
  TouchableOpacity,
  TouchableWithoutFeedback,
  BackHandler,
  Animated,
  RefreshControl,
} from 'react-native';
import { TSM, Period, ASE } from '../../types';
import { formatNumber } from '../../lib/utils';
import { TsmListSkeletonList } from '../../components/SkeletonLoaders';
import { MetricsCard } from '../../components/MetricsCard';
import { SegmentedTabs } from '../../components/SegmentedTabs';
import { SearchBar } from '../../components/SearchBar';
import { PaginationBar } from '../../components/PaginationBar';
import { SortModal, SortOptionValue } from '../../components/SortModal';
import {
  UserIcon,
  UsersIcon,
  BuildingIcon,
  ChevronLeftIcon,
  SwapVertIcon,
  ChevronDownIcon,
  XIcon,
} from '../../components/Icons';

interface TsmViewProps {
  tsms: TSM[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
  loading?: boolean;
  onRefresh?: () => Promise<void> | void;
}

export function TsmView({
  tsms,
  period,
  scaleFactor,
  selectedHq,
  loading = false,
  onRefresh,
}: TsmViewProps) {
  // Navigation level:
  // Level 1 = Root TSM List (Image 1)
  // Level 2 = TSM Detail (Image 2: Companies Tab, Image 3: ASE Tab)
  // Level 3 = ASE Detail (Image 4: Companies for selected ASE)
  const [level, setLevel] = useState<1 | 2 | 3>(1);
  const [activeTsmTab, setActiveTsmTab] = useState<'companies' | 'ase'>('companies');

  // Selected entities
  const [selectedTsm, setSelectedTsm] = useState<TSM | null>(null);
  const [selectedAse, setSelectedAse] = useState<ASE | null>(null);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sortOption, setSortOption] = useState<SortOptionValue>('az');
  const [showSortModal, setShowSortModal] = useState<boolean>(false);
  const [perPage, setPerPage] = useState<number>(15);
  const [showPerPageModal, setShowPerPageModal] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      if (onRefresh) {
        await onRefresh();
      }
    } catch (err) {
      console.error('Error refreshing TsmView:', err);
    } finally {
      setRefreshing(false);
    }
  }, [onRefresh]);

  const scaledFontSize = useCallback(
    (base: number) => Math.round(base * scaleFactor),
    [scaleFactor]
  );

  // Reset search and pagination on view changes
  const resetFilters = () => {
    setSearchQuery('');
    setSortOption('az');
    setCurrentPage(1);
  };

  // Selection Handlers
  const handleSelectTsm = (tsm: TSM) => {
    setSelectedTsm(tsm);
    setSelectedAse(null);
    setActiveTsmTab('companies'); // Default tab on opening TSM as shown in Image 2!
    setLevel(2);
    resetFilters();
  };

  const handleSelectAse = (ase: ASE) => {
    setSelectedAse(ase);
    setLevel(3);
    resetFilters();
  };

  const handleGoBack = useCallback(() => {
    if (level === 3) {
      // Return from ASE Companies view (Image 4) to TSM ASEs List view (Image 3)
      setSelectedAse(null);
      setLevel(2);
      setActiveTsmTab('ase');
      resetFilters();
    } else if (level === 2) {
      // Return from TSM Detail view (Image 2 or 3) to Root TSM List view (Image 1)
      setSelectedTsm(null);
      setSelectedAse(null);
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

  // 1. Filter Root TSMs by HQ Selection and Search Query
  const filteredTsms = useMemo(() => {
    return tsms.filter((t) => {
      const matchHq =
        selectedHq === 'All Headquarters' ||
        (t.hqLocation && t.hqLocation.toLowerCase() === selectedHq.toLowerCase());
      const matchSearch =
        !searchQuery.trim() ||
        t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (t.hqLocation && t.hqLocation.toLowerCase().includes(searchQuery.toLowerCase()));
      return matchHq && matchSearch;
    });
  }, [tsms, selectedHq, searchQuery]);

  const activeRawList = useMemo(() => {
    if (level === 1) return filteredTsms;

    if (level === 2) {
      if (activeTsmTab === 'companies') {
        const comps = (selectedTsm as any)?.companies || selectedTsm?.brands || [];
        return comps.filter((item: any) => {
          const raw = item.data?.[period] || { cases: 0, bottles: 0 };
          return (raw.cases || 0) > 0 || (raw.bottles || 0) > 0;
        });
      }
      return selectedTsm?.ases || [];
    }

    const aseComps = (selectedAse as any)?.companies || (selectedAse as any)?.brands || (selectedTsm as any)?.companies || [];
    return aseComps.filter((item: any) => {
      const raw = item.data?.[period] || { cases: 0, bottles: 0 };
      return (raw.cases || 0) > 0 || (raw.bottles || 0) > 0;
    });
  }, [level, activeTsmTab, filteredTsms, selectedTsm, selectedAse, period]);

  const filteredAndSortedList = useMemo(() => {
    let result = [...activeRawList];

    if (level > 1 && searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter((item: any) => {
        const name = (item.name || item.brandName || item.company_name || '').toLowerCase();
        const sub = (item.hqLocation || item.area || '').toLowerCase();
        return name.includes(q) || sub.includes(q);
      });
    }

    result.sort((a: any, b: any) => {
      const nameA = (a.name || a.brandName || a.company_name || '').toLowerCase();
      const nameB = (b.name || b.brandName || b.company_name || '').toLowerCase();

      const aRaw = a.data?.[period] || { cases: 0, bottles: 0 };
      const bRaw = b.data?.[period] || { cases: 0, bottles: 0 };
      const casesA = Math.round((aRaw.cases || a.total_cases || 0) * scaleFactor);
      const casesB = Math.round((bRaw.cases || b.total_cases || 0) * scaleFactor);

      if (sortOption === 'az') return nameA.localeCompare(nameB);
      if (sortOption === 'za') return nameB.localeCompare(nameA);
      if (sortOption === 'cases_desc') return casesB - casesA;
      if (sortOption === 'cases_asc') return casesA - casesB;
      return 0;
    });

    return result;
  }, [activeRawList, level, searchQuery, sortOption, period, scaleFactor]);

  const totalItems = filteredAndSortedList.length;
  const totalPages = Math.ceil(totalItems / perPage) || 1;
  const startIndex = (currentPage - 1) * perPage;
  const endIndex = Math.min(startIndex + perPage, totalItems);
  const paginatedList = filteredAndSortedList.slice(startIndex, endIndex);

  const searchPlaceholder = useMemo(() => {
    if (level === 1) return 'Search TSM name or HQ..';
    if (level === 2) {
      return activeTsmTab === 'companies'
        ? 'Search companies for this TSM...'
        : 'Search ASE name or area.';
    }
    const firstName = selectedAse?.name?.split(' ')[0] || 'ASE';
    return `Search companies for ${firstName}...`;
  }, [level, activeTsmTab, selectedAse]);

  return (
    <View style={styles.container}>
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
              { key: 'companies', label: 'Companies', icon: <BuildingIcon /> },
              { key: 'ase', label: 'ASE', icon: <UsersIcon /> },
            ]}
            activeTabKey={activeTsmTab}
            onTabChange={(tabKey) => {
              setActiveTsmTab(tabKey as any);
              if (level === 3 && tabKey === 'companies') {
                setLevel(2);
                setSelectedAse(null);
              }
              resetFilters();
            }}
            scaleFactor={scaleFactor}
          />
        </View>
      )}

      {/* Filter Row: SearchBar & Sort Pill */}
      <View style={styles.searchControlsRow}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <SearchBar
            value={searchQuery}
            onChangeText={(text) => {
              setSearchQuery(text);
              setCurrentPage(1);
            }}
            placeholder={searchPlaceholder}
            scaleFactor={scaleFactor}
          />
        </View>

        {/* Sort Pill Dropdown */}
        <TouchableOpacity
          style={styles.sortPillBtn}
          onPress={() => setShowSortModal(true)}
          activeOpacity={0.75}
        >
          <SwapVertIcon size={14} color="#64748B" />
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

      {/* Showing Items & Per Page Limit Info Row */}
      <View style={styles.showingInfoRow}>
        <Text style={[styles.showingText, { fontSize: scaledFontSize(12) }]}>
          Showing {totalItems === 0 ? 0 : startIndex + 1}-{endIndex} of {totalItems} item(s)
        </Text>

        <TouchableOpacity
          style={styles.perPageTrigger}
          onPress={() => setShowPerPageModal(true)}
          activeOpacity={0.75}
        >
          <Text style={[styles.perPageLabelText, { fontSize: scaledFontSize(12) }]}>
            Per page:
          </Text>
          <View style={styles.perPagePill}>
            <Text style={[styles.perPageValueText, { fontSize: scaledFontSize(12) }]}>
              {perPage}
            </Text>
            <ChevronDownIcon size={12} color="#64748B" />
          </View>
        </TouchableOpacity>
      </View>

      {/* Scrollable Content */}
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
          <TsmListSkeletonList count={5} />
        ) : paginatedList.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyText}>No items found matching criteria</Text>
          </View>
        ) : (
          paginatedList.map((item: any, index: number) => {
            // Level 1: Root TSM Card (Image 1)
            if (level === 1) {
              const rawData = item.data?.[period] || { cases: 0, bottles: 0 };
              const cases = Math.round((rawData.cases || 0) * scaleFactor);
              const bottles = Math.round((rawData.bottles || 0) * scaleFactor);
              const aseCount = item.ases?.length || 0;
              const companyCount = item.companyCount?.[period] ?? item.company_count?.[period] ?? (item.brands?.filter((b: any) => (b.data?.[period]?.cases || 0) > 0 || (b.data?.[period]?.bottles || 0) > 0).length || 0);
              const hqName = item.hqLocation || 'All Headquarters';

              return (
                <MetricsCard
                  key={item.id || index}
                  title={item.name}
                  titleIcon={<UserIcon size={18} color="#0F172A" />}
                  subtitle={`👥 ${aseCount} ASE(s)  •  🏢 ${companyCount} Companies`}
                  metrics={[
                    { label: 'Total Cases', value: cases },
                    { label: 'Total Bottles', value: bottles },
                  ]}
                  locationPill={`Headquarter: ${hqName}`}
                  pillTheme="blue"
                  onPress={() => handleSelectTsm(item)}
                  scaleFactor={scaleFactor}
                />
              );
            }

            // Level 2: TSM Companies View (Image 2)
            if (level === 2 && activeTsmTab === 'companies') {
              const rawData = item.data?.[period] || { cases: 0, bottles: 0 };
              const cases = Math.round((rawData.cases || item.total_cases || 0) * scaleFactor);
              const bottles = Math.round((rawData.bottles || item.total_bottles || 0) * scaleFactor);
              const compName = item.brandName || item.company_name || item.name || 'Company';
              const tsmName = selectedTsm?.name || 'TSM';
              const hqName = selectedTsm?.hqLocation || 'All Headquarters';

              return (
                <MetricsCard
                  key={item.brandId || item.id || index}
                  title={compName}
                  titleIcon={<BuildingIcon size={18} color="#0F172A" />}
                  metrics={[
                    { label: 'Cases', value: cases },
                    { label: 'Bottles', value: bottles },
                  ]}
                  locationPill={`TSM: ${tsmName} (${hqName})`}
                  pillTheme="red"
                  scaleFactor={scaleFactor}
                />
              );
            }

            // Level 2: TSM ASEs List View (Image 3)
            if (level === 2 && activeTsmTab === 'ase') {
              const rawData = item.data?.[period] || { cases: 0, bottles: 0 };
              const cases = Math.round((rawData.cases || 0) * scaleFactor);
              const bottles = Math.round((rawData.bottles || 0) * scaleFactor);
              const areaName = item.name.split(' ')[0] + ' North';
              const companyCount = item.companyCount?.[period] ?? item.company_count?.[period] ?? (item.brands?.filter((b: any) => (b.data?.[period]?.cases || 0) > 0 || (b.data?.[period]?.bottles || 0) > 0).length || 0);

              return (
                <MetricsCard
                  key={item.id || index}
                  title={item.name}
                  titleIcon={<UserIcon size={18} color="#0F172A" />}
                  subtitle={`${areaName}  •  🏢 ${companyCount} Companies`}
                  metrics={[
                    { label: 'Cases', value: cases },
                    { label: 'Bottles', value: bottles },
                  ]}
                  locationPill={areaName}
                  pillTheme="blue"
                  onPress={() => handleSelectAse(item)}
                  scaleFactor={scaleFactor}
                />
              );
            }

            // Level 3: ASE Companies View (Image 4)
            if (level === 3) {
              const rawData = item.data?.[period] || { cases: 0, bottles: 0 };
              const cases = Math.round((rawData.cases || item.total_cases || 0) * scaleFactor);
              const bottles = Math.round((rawData.bottles || item.total_bottles || 0) * scaleFactor);
              const compName = item.brandName || item.company_name || item.name || 'Company';
              const aseName = selectedAse?.name || 'ASE';
              const areaName = selectedAse?.name?.split(' ')[0] + ' North';

              return (
                <MetricsCard
                  key={item.brandId || item.id || index}
                  title={compName}
                  titleIcon={<BuildingIcon size={18} color="#0F172A" />}
                  metrics={[
                    { label: 'Cases', value: cases },
                    { label: 'Bottles', value: bottles },
                  ]}
                  locationPill={`ASE: ${aseName} (${areaName})`}
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
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  sortPillBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F1F5F9',
    paddingHorizontal: 10,
    height: 42,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    gap: 4,
  },
  sortText: {
    color: '#0F172A',
    fontSize: 12,
    fontWeight: '600',
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
