import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  FlatList,
  Modal,
  ScrollView,
  TouchableWithoutFeedback,
  PanResponder,
  BackHandler,
} from 'react-native';
import { TSM, Period, ASE } from '../../types';
import { formatNumber } from '../../lib/utils';
import { TsmListSkeletonList } from '../../components/SkeletonLoaders';
import {
  SearchIcon,
  XIcon,
  ChevronRightIcon,
  ChevronLeftIcon,
  UserIcon,
  UsersIcon,
  SwapVertIcon,
  ChevronDownIcon,
} from '../../components/Icons';

interface TsmViewProps {
  tsms: TSM[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
  loading?: boolean;
}

export function TsmView({
  tsms,
  period,
  scaleFactor,
  selectedHq,
  loading = false,
}: TsmViewProps) {
  // Modal & Selection State
  const [selectedTsm, setSelectedTsm] = useState<TSM | null>(null);

  // Swipe-down PanResponder gesture to close modal
  const tsmPanResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gestureState) => {
        return gestureState.dy > 10 && Math.abs(gestureState.dx) < 35;
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > 25) {
          setSelectedTsm(null);
        }
      },
    })
  ).current;

  // Search & Filter State
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [sortOption, setSortOption] = useState<'az' | 'za' | 'cases_desc' | 'cases_asc'>('az');
  const [showSortModal, setShowSortModal] = useState<boolean>(false);
  const [perPage, setPerPage] = useState<number>(15);
  const [showPerPageModal, setShowPerPageModal] = useState<boolean>(false);

  // Hardware BackHandler for TSM modals
  useEffect(() => {
    if (!selectedTsm && !showSortModal && !showPerPageModal) return;
    const onBackPress = () => {
      if (selectedTsm) setSelectedTsm(null);
      if (showSortModal) setShowSortModal(false);
      if (showPerPageModal) setShowPerPageModal(false);
      return true;
    };
    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [selectedTsm, showSortModal, showPerPageModal]);
  
  const [currentPage, setCurrentPage] = useState<number>(1);

  // 1. Filter TSMs by HQ selection and Search Term
  const filteredTsms = useMemo(() => {
    return tsms.filter((t) => {
      const matchHq =
        selectedHq === 'All Headquarters' ||
        (t.hqLocation && t.hqLocation.toLowerCase() === selectedHq.toLowerCase());
      const matchSearch =
        !searchTerm.trim() ||
        t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (t.hqLocation && t.hqLocation.toLowerCase().includes(searchTerm.toLowerCase()));
      return matchHq && matchSearch;
    });
  }, [tsms, selectedHq, searchTerm]);

  // 2. Sort TSMs
  const sortedTsms = useMemo(() => {
    const list = [...filteredTsms];
    list.sort((a, b) => {
      const aRaw = a.data[period] || { cases: 0, bottles: 0 };
      const bRaw = b.data[period] || { cases: 0, bottles: 0 };
      const aCases = Math.round(aRaw.cases * scaleFactor);
      const bCases = Math.round(bRaw.cases * scaleFactor);

      if (sortOption === 'az') return a.name.localeCompare(b.name);
      if (sortOption === 'za') return b.name.localeCompare(a.name);
      if (sortOption === 'cases_desc') return bCases - aCases;
      if (sortOption === 'cases_asc') return aCases - bCases;
      return 0;
    });
    return list;
  }, [filteredTsms, period, scaleFactor, sortOption]);

  // 3. Paginate TSMs
  const totalPages = Math.max(1, Math.ceil(sortedTsms.length / perPage));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const paginatedTsms = useMemo(() => {
    const startIndex = (safeCurrentPage - 1) * perPage;
    return sortedTsms.slice(startIndex, startIndex + perPage);
  }, [sortedTsms, safeCurrentPage, perPage]);

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage);
    }
  };

  // 4. Sorted ASEs inside Modal (Sorted by Highest Cases First)
  const modalAses = useMemo(() => {
    if (!selectedTsm || !selectedTsm.ases) return [];
    const aseList: ASE[] = [...selectedTsm.ases];
    aseList.sort((a, b) => {
      const aRaw = a.data?.[period] || { cases: 0, bottles: 0 };
      const bRaw = b.data?.[period] || { cases: 0, bottles: 0 };
      const aCases = Math.round((aRaw.cases || 0) * scaleFactor);
      const bCases = Math.round((bRaw.cases || 0) * scaleFactor);
      if (bCases !== aCases) return bCases - aCases;
      return a.name.localeCompare(b.name);
    });
    return aseList;
  }, [selectedTsm, period, scaleFactor]);

  // Summary metrics for selected TSM inside Modal
  const modalTsmMetrics = useMemo(() => {
    if (!selectedTsm) return { cases: 0, bottles: 0 };
    const raw = selectedTsm.data[period] || { cases: 0, bottles: 0 };
    return {
      cases: Math.round(raw.cases * scaleFactor),
      bottles: Math.round(raw.bottles * scaleFactor),
    };
  }, [selectedTsm, period, scaleFactor]);

  // Render Individual TSM Card (Matches Image 1)
  const renderTsmItem = useCallback(
    ({ item: tsm }: { item: TSM }) => {
      const raw = tsm.data[period] || { cases: 0, bottles: 0 };
      const cases = Math.round(raw.cases * scaleFactor);
      const bottles = Math.round(raw.bottles * scaleFactor);
      const aseCount = tsm.ases ? tsm.ases.length : 0;

      return (
        <TouchableOpacity
          style={styles.tsmCard}
          activeOpacity={0.75}
          onPress={() => setSelectedTsm(tsm)}
        >
          {/* Card Top Row: Avatar, Name, ASE count, and Chevron */}
          <View style={styles.tsmHeader}>
            <View style={styles.avatarCircle}>
              <UserIcon size={16} color="#94A3B8" />
            </View>
            <View style={styles.tsmInfo}>
              <Text style={styles.tsmName}>{tsm.name}</Text>
              <Text style={styles.tsmSubtext}>
                {aseCount} {aseCount === 1 ? 'ASE' : 'ASEs'} assigned
              </Text>
            </View>
            <ChevronRightIcon size={18} color="#CBD5E1" />
          </View>

          {/* Card Metrics Grid Box */}
          <View style={styles.metricsGrid}>
            <View style={styles.metricCell}>
              <Text style={styles.metricLabel}>TOTAL CASES</Text>
              <Text style={styles.metricValuePrimary}>{formatNumber(cases)}</Text>
            </View>
            <View style={styles.metricCell}>
              <Text style={styles.metricLabel}>TOTAL BOTTLES</Text>
              <Text style={styles.metricValueSecondary}>{formatNumber(bottles)}</Text>
            </View>
          </View>
        </TouchableOpacity>
      );
    },
    [period, scaleFactor]
  );

  return (
    <View style={styles.container}>
      {/* Search Input Bar */}
      <View style={styles.searchWrapper}>
        <View style={{ marginRight: 8 }}>
          <SearchIcon size={18} color="#94A3B8" />
        </View>
        <TextInput
          style={styles.searchInput}
          placeholder="Search TSM name"
          placeholderTextColor="#94A3B8"
          value={searchTerm}
          onChangeText={(text) => {
            setSearchTerm(text);
            setCurrentPage(1);
          }}
        />
        {searchTerm ? (
          <TouchableOpacity onPress={() => setSearchTerm('')} style={styles.clearBtn}>
            <XIcon size={12} color="#94A3B8" />
          </TouchableOpacity>
        ) : null}
      </View>

      {/* Control Bar: Sort & Per Page Selector */}
      <View style={styles.controlsRow}>
        <TouchableOpacity
          style={styles.sortDropdownBtn}
          onPress={() => setShowSortModal(true)}
          activeOpacity={0.7}
        >
          <SwapVertIcon size={14} color="#94A3B8" />
          <Text style={styles.sortBtnText}>
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

      {/* Results Count Summary Header */}
      <View style={styles.countRow}>
        <Text style={styles.countText}>
          Showing {sortedTsms.length > 0 ? (safeCurrentPage - 1) * perPage + 1 : 0}-
          {Math.min(safeCurrentPage * perPage, sortedTsms.length)} of {sortedTsms.length} TSM(s)
        </Text>
      </View>

      {/* TSM Cards List */}
      {loading ? (
        <TsmListSkeletonList count={5} />
      ) : paginatedTsms.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyText}>No TSM found matching criteria</Text>
        </View>
      ) : (
        <FlatList
          data={paginatedTsms}
          keyExtractor={(item) => item.id}
          renderItem={renderTsmItem}
          contentContainerStyle={styles.listContent}
          initialNumToRender={10}
          maxToRenderPerBatch={8}
          windowSize={5}
          removeClippedSubviews={true}
          showsVerticalScrollIndicator={false}
        />
      )}

      {/* Pagination Footer Controls */}
      {totalPages > 1 && (
        <View style={styles.paginationRow}>
          <TouchableOpacity
            style={[styles.pageBtn, safeCurrentPage === 1 && styles.pageBtnDisabled]}
            disabled={safeCurrentPage === 1}
            onPress={() => handlePageChange(safeCurrentPage - 1)}
          >
            <ChevronLeftIcon size={16} color={safeCurrentPage === 1 ? '#CBD5E1' : '#0F2042'} />
            <Text style={[styles.pageBtnText, safeCurrentPage === 1 && styles.pageBtnTextDisabled]}>
              Prev
            </Text>
          </TouchableOpacity>

          <Text style={styles.pageIndicatorText}>
            Page <Text style={styles.boldPageText}>{safeCurrentPage}</Text> of {totalPages}
          </Text>

          <TouchableOpacity
            style={[styles.pageBtn, safeCurrentPage === totalPages && styles.pageBtnDisabled]}
            disabled={safeCurrentPage === totalPages}
            onPress={() => handlePageChange(safeCurrentPage + 1)}
          >
            <Text style={[styles.pageBtnText, safeCurrentPage === totalPages && styles.pageBtnTextDisabled]}>
              Next
            </Text>
            <ChevronRightIcon size={16} color={safeCurrentPage === totalPages ? '#CBD5E1' : '#0F2042'} />
          </TouchableOpacity>
        </View>
      )}

      {/* Sort Option Selection Modal */}
      <Modal
        visible={showSortModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowSortModal(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowSortModal(false)}
        >
          <View style={styles.optionModalBox}>
            <Text style={styles.optionModalTitle}>Sort TSMs By</Text>
            {[
              { id: 'az', label: 'A-Z (Name)' },
              { id: 'za', label: 'Z-A (Name)' },
              { id: 'cases_desc', label: 'Cases (High to Low)' },
              { id: 'cases_asc', label: 'Cases (Low to High)' },
            ].map((opt) => (
              <TouchableOpacity
                key={opt.id}
                style={[
                  styles.optionRow,
                  sortOption === opt.id && styles.optionRowSelected,
                ]}
                onPress={() => {
                  setSortOption(opt.id as any);
                  setShowSortModal(false);
                  setCurrentPage(1);
                }}
              >
                <Text
                  style={[
                    styles.optionText,
                    sortOption === opt.id && styles.optionTextSelected,
                  ]}
                >
                  {opt.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </TouchableOpacity>
      </Modal>

      {/* Per Page Items Modal */}
      <Modal
        visible={showPerPageModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowPerPageModal(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowPerPageModal(false)}
        >
          <View style={styles.optionModalBox}>
            <Text style={styles.optionModalTitle}>Items Per Page</Text>
            {[10, 15, 25, 50].map((num) => (
              <TouchableOpacity
                key={num}
                style={[
                  styles.optionRow,
                  perPage === num && styles.optionRowSelected,
                ]}
                onPress={() => {
                  setPerPage(num);
                  setShowPerPageModal(false);
                  setCurrentPage(1);
                }}
              >
                <Text
                  style={[
                    styles.optionText,
                    perPage === num && styles.optionTextSelected,
                  ]}
                >
                  {num} TSMs per page
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </TouchableOpacity>
      </Modal>

      {/* ───────────────────────────────────────────────────────────── */}
      {/* ASE BREAKDOWN DRILL-DOWN MODAL (Matches Image 2)               */}
      {/* ───────────────────────────────────────────────────────────── */}
      <Modal
        visible={selectedTsm !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setSelectedTsm(null)}
      >
        <TouchableOpacity
          style={styles.modalBackdrop}
          activeOpacity={1}
          onPress={() => setSelectedTsm(null)}
        >
          <TouchableWithoutFeedback onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalContainer}>
              {/* Drag Handle Indicator */}
              <View style={styles.dragHeaderArea} {...tsmPanResponder.panHandlers}>
                <View style={styles.dragIndicatorPill} />
              </View>

              {/* Modal Header Card (Dark Navy Accent) */}
              <View style={styles.darkHeaderCard} {...tsmPanResponder.panHandlers}>
                <View style={styles.darkHeaderTopRow}>
                  <View style={styles.darkHeaderTitleCol}>
                    <Text style={styles.darkHeaderTitle}>{selectedTsm?.name}</Text>
                    <Text style={styles.darkHeaderSubtext}>
                      {modalAses.length} Assigned {modalAses.length === 1 ? 'ASE' : 'ASEs'}
                    </Text>
                  </View>
                  <TouchableOpacity
                    style={styles.closeCircleBtn}
                    onPress={() => setSelectedTsm(null)}
                    activeOpacity={0.7}
                    hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                  >
                    <XIcon size={18} color="#FFFFFF" />
                  </TouchableOpacity>
                </View>

                {/* Header Dark Navy Summary Metrics Box */}
                <View style={styles.darkSummaryBox}>
                  <View style={styles.darkSummaryCell}>
                    <Text style={styles.darkSummaryLabel}>TOTAL CASES</Text>
                    <Text style={styles.darkSummaryValue}>{formatNumber(modalTsmMetrics.cases)}</Text>
                  </View>

                  <View style={styles.darkSummaryDivider} />

                  <View style={styles.darkSummaryCell}>
                    <Text style={styles.darkSummaryLabel}>TOTAL BOTTLES</Text>
                    <Text style={styles.darkSummaryValue}>{formatNumber(modalTsmMetrics.bottles)}</Text>
                  </View>
                </View>
              </View>

              {/* Modal Content Body */}
              <View style={styles.modalBody}>
                {/* Section Subheader */}
                <View style={styles.aseSectionHeader}>
                  <UsersIcon size={14} color="#94A3B8" />
                  <Text style={styles.aseSectionTitle}>
                    ASE-WISE SALES ({period.toUpperCase()})
                  </Text>
                </View>

                {/* List of ASE Cards */}
                <ScrollView
                  style={styles.aseScrollView}
                  contentContainerStyle={styles.aseScrollContent}
                  showsVerticalScrollIndicator={false}
                >
                  {modalAses.length === 0 ? (
                    <View style={styles.emptyAseCard}>
                      <Text style={styles.emptyAseText}>No ASE assigned to this TSM</Text>
                    </View>
                  ) : (
                    modalAses.map((ase) => {
                      const aseRaw = ase.data?.[period] || { cases: 0, bottles: 0, bl: 0.0 };
                      const cases = Math.round((aseRaw.cases || 0) * scaleFactor);
                      const bottles = Math.round((aseRaw.bottles || 0) * scaleFactor);

                      return (
                        <View key={ase.id} style={styles.aseCard}>
                          <View style={styles.aseHeaderRow}>
                            <View style={styles.aseAvatarCircle}>
                              <UserIcon size={14} color="#94A3B8" />
                            </View>
                            <Text style={styles.aseName}>{ase.name}</Text>
                          </View>
                          <View style={styles.aseMetricsGrid}>
                            <View style={styles.aseMetricCell}>
                              <Text style={styles.aseMetricLabel}>CASES</Text>
                              <Text style={styles.aseMetricValue}>{formatNumber(cases)}</Text>
                            </View>
                            <View style={styles.aseMetricCell}>
                              <Text style={styles.aseMetricLabel}>BOTTLES</Text>
                              <Text style={styles.aseMetricValue}>{formatNumber(bottles)}</Text>
                            </View>
                          </View>
                        </View>
                      );
                    })
                  )}
                </ScrollView>

                <TouchableOpacity
                  style={styles.stickyCloseButton}
                  onPress={() => setSelectedTsm(null)}
                  activeOpacity={0.8}
                >
                  <Text style={styles.stickyCloseButtonText}>Close</Text>
                </TouchableOpacity>
              </View>
            </View>
          </TouchableWithoutFeedback>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}
const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  // Search Bar
  searchWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    paddingHorizontal: 12,
    marginBottom: 10,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 2,
    elevation: 1,
  },
  searchInput: {
    flex: 1,
    fontSize: 12,
    fontWeight: '500',
    color: '#334155',
    paddingVertical: 10,
  },
  clearBtn: {
    padding: 6,
  },
  // Controls Row (Sort & Per Page)
  controlsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
    gap: 8,
  },
  sortDropdownBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 6,
  },
  sortBtnText: {
    flex: 1,
    fontSize: 11,
    fontWeight: '700',
    color: '#1E293B',
  },
  perPageBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  perPageLabel: {
    fontSize: 11,
    fontWeight: '500',
    color: '#64748B',
  },
  perPageValue: {
    fontSize: 11,
    fontWeight: '700',
    color: '#0F172A',
    marginRight: 4,
  },
  // Count Bar
  countRow: {
    marginBottom: 10,
    paddingHorizontal: 2,
  },
  countText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#64748B',
  },
  emptyCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 24,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#64748B',
  },
  listContent: {
    paddingBottom: 16,
  },
  // TSM Card Item (Matches Image 1)
  tsmCard: {
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
  tsmHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  avatarCircle: {
    width: 34,
    height: 34,
    borderRadius: 10,
    backgroundColor: '#EEF2F6',
    justifyContent: 'center',
    alignItems: 'center',
  },
  tsmInfo: {
    marginLeft: 10,
    flex: 1,
  },
  tsmName: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
  },
  tsmSubtext: {
    fontSize: 10,
    fontWeight: '600',
    color: '#64748B',
    marginTop: 2,
  },
  metricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: '#F1F5F9',
  },
  metricCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.5,
  },
  metricValuePrimary: {
    fontSize: 13,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 2,
  },
  metricValueSecondary: {
    fontSize: 13,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 2,
  },
  // Pagination
  paginationRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderTopWidth: 1,
    borderColor: '#E2E8F0',
    marginTop: 4,
  },
  pageBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#F1F5F9',
  },
  pageBtnDisabled: {
    backgroundColor: '#F8FAFC',
    opacity: 0.6,
  },
  pageBtnText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#0F2042',
  },
  pageBtnTextDisabled: {
    color: '#94A3B8',
  },
  pageIndicatorText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#64748B',
  },
  boldPageText: {
    fontWeight: '800',
    color: '#0F172A',
  },
  // Option Select Modals
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  optionModalBox: {
    width: '100%',
    maxWidth: 320,
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 10,
    elevation: 5,
  },
  optionModalTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
    marginBottom: 12,
    textAlign: 'center',
  },
  optionRow: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    marginBottom: 4,
  },
  optionRowSelected: {
    backgroundColor: '#EFF6FF',
  },
  optionText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#334155',
  },
  optionTextSelected: {
    fontWeight: '800',
    color: '#0F2042',
  },

  // ─────────────────────────────────────────────────────────────
  // ASE BREAKDOWN MODAL STYLES (Matches Image 2)
  // ─────────────────────────────────────────────────────────────
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.6)',
    justifyContent: 'flex-end',
  },
  modalContainer: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '90%',
    overflow: 'hidden',
  },
  // Dark Navy Header Box
  darkHeaderCard: {
    backgroundColor: '#0B192C',
    paddingTop: 18,
    paddingHorizontal: 18,
    paddingBottom: 16,
  },
  darkHeaderTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 14,
  },
  darkHeaderTitleCol: {
    flex: 1,
    paddingRight: 10,
  },
  darkHeaderTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: '#FFFFFF',
  },
  darkHeaderSubtext: {
    fontSize: 11,
    fontWeight: '600',
    color: '#94A3B8',
    marginTop: 2,
  },
  dragHeaderArea: {
    backgroundColor: '#0B192C',
    alignItems: 'center',
    paddingTop: 10,
    paddingBottom: 2,
  },
  dragIndicatorPill: {
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255, 255, 255, 0.3)',
  },
  closeCircleBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
  },
  darkSummaryBox: {
    flexDirection: 'row',
    backgroundColor: '#071120',
    borderRadius: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  darkSummaryCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  darkSummaryDivider: {
    width: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
  },
  darkSummaryLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.5,
  },
  darkSummaryValue: {
    fontSize: 14,
    fontWeight: '900',
    color: '#FFFFFF',
    marginTop: 2,
  },

  // Modal Body
  modalBody: {
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 16,
    backgroundColor: '#FFFFFF',
  },
  aseSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 12,
  },
  aseSectionTitle: {
    fontSize: 11,
    fontWeight: '800',
    color: '#64748B',
    letterSpacing: 0.5,
  },
  aseScrollView: {
    maxHeight: 380,
  },
  aseScrollContent: {
    paddingBottom: 10,
  },
  emptyAseCard: {
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
  },
  emptyAseText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#64748B',
  },
  // ASE List Card
  aseCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 12,
    marginBottom: 10,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 2,
    elevation: 1,
  },
  aseHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  aseAvatarCircle: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: '#EEF2F6',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 10,
  },
  aseName: {
    fontSize: 13,
    fontWeight: '800',
    color: '#0F172A',
  },
  aseMetricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#F1F5F9',
  },
  aseMetricCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  aseMetricLabel: {
    fontSize: 8,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.5,
  },
  aseMetricValue: {
    fontSize: 12,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 2,
  },
  // Bottom Sticky Close Button
  stickyCloseButton: {
    backgroundColor: '#0B192C',
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 10,
  },
  stickyCloseButtonText: {
    fontSize: 13,
    fontWeight: '800',
    color: '#FFFFFF',
  },
});
