import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TextInput,
  TouchableOpacity,
  FlatList,
  PanResponder,
  BackHandler,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Company, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
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
} from '../../components/Icons';

export type BrandSortOption = 'default' | 'volume_desc' | 'volume_asc' | 'name_asc';

interface BrandModalProps {
  company: Company | null;
  period: Period;
  scaleFactor: number;
  onClose: () => void;
}

export function BrandModal({
  company,
  period,
  scaleFactor,
  onClose,
}: BrandModalProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState<BrandSortOption>('default');
  const [showSortDropdown, setShowSortDropdown] = useState<boolean>(false);
  const [dropdownPos, setDropdownPos] = useState<{ top: number; right: number }>({ top: 250, right: 16 });
  const sortBtnRef = useRef<View>(null);

  // Reset search and sort when company changes
  useEffect(() => {
    if (company) {
      setSearchTerm('');
      setSortBy('default');
      setShowSortDropdown(false);
    }
  }, [company]);

  // Handle hardware Back button to close modal
  useEffect(() => {
    if (!company) return;
    const onBackPress = () => {
      if (showSortDropdown) {
        setShowSortDropdown(false);
        return true;
      }
      onClose();
      return true;
    };
    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [company, showSortDropdown, onClose]);

  // Swipe-down PanResponder gesture to close modal on swipe down from header
  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gestureState) => {
        return gestureState.dy > 12 && Math.abs(gestureState.dx) < 35;
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > 25) {
          onClose();
        }
      },
    })
  ).current;

  // Filter and sort brands
  const sortedBrands = useMemo(() => {
    if (!company) return [];

    const list = company.brands.filter((b) =>
      b.name.toLowerCase().includes(searchTerm.toLowerCase())
    );

    list.sort((a, b) => {
      if (sortBy === 'volume_desc') {
        const casesA = a.data[period]?.cases || 0;
        const casesB = b.data[period]?.cases || 0;
        if (casesB !== casesA) return casesB - casesA;
        return a.name.localeCompare(b.name);
      }

      if (sortBy === 'volume_asc') {
        const casesA = a.data[period]?.cases || 0;
        const casesB = b.data[period]?.cases || 0;
        if (casesA !== casesB) return casesA - casesB;
        return a.name.localeCompare(b.name);
      }

      if (sortBy === 'name_asc') {
        return a.name.localeCompare(b.name);
      }

      return 0;
    });

    return list;
  }, [company, searchTerm, sortBy, period]);

  if (!company) return null;

  const rawCompanyData = company.data?.[period] || { cases: company.cases || 0, bottles: company.bottles || 0 };
  const companyCases = Math.round((rawCompanyData.cases ?? company.cases ?? 0) * scaleFactor);
  const companyBottles = Math.round((rawCompanyData.bottles ?? company.bottles ?? 0) * scaleFactor);

  const getSortLabel = () => {
    if (sortBy === 'volume_desc') return 'Top Sales';
    if (sortBy === 'volume_asc') return 'Low Sales';
    if (sortBy === 'name_asc') return 'A-Z';
    return 'Sort';
  };

  const toggleSortDropdown = () => {
    if (!showSortDropdown && sortBtnRef.current) {
      sortBtnRef.current.measureInWindow((x, y, width, height) => {
        if (y && height) {
          setDropdownPos({
            top: y + height + 4,
            right: 16,
          });
        }
        setShowSortDropdown(true);
      });
    } else {
      setShowSortDropdown(false);
    }
  };

  const sortDropdownOptions = [
    { key: 'default', label: 'Default Order', Icon: PinIcon },
    { key: 'volume_desc', label: 'Top Sales (High → Low)', Icon: TrendingUpIcon },
    { key: 'volume_asc', label: 'Lowest Sales (Low → High)', Icon: TrendingDownIcon },
    { key: 'name_asc', label: 'Brand Name (A → Z)', Icon: SortAlphabeticalIcon },
  ];

  return (
    <Modal
      visible={company !== null}
      transparent={true}
      animationType="slide"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.modalOverlay}
      >
        {/* Backdrop touchable to close modal when clicking outside */}
        <TouchableOpacity
          style={StyleSheet.absoluteFill}
          activeOpacity={1}
          onPress={onClose}
        />

        {/* Modal Bottom Sheet Content */}
        <View style={styles.modalContent}>
          {/* Top Drag Handle Header Area */}
          <View style={styles.dragHeaderArea} {...panResponder.panHandlers}>
            <View style={styles.dragIndicatorPill} />
          </View>

          {/* Clean White Sheet Header */}
          <View style={styles.modalHeader} {...panResponder.panHandlers}>
            <View style={styles.headerTitleWrapper}>
              <Text style={styles.modalTitle} numberOfLines={1}>
                {company.name}
              </Text>
              <Text style={styles.modalSubtitle}>
                {company.brands.length} Active {company.brands.length === 1 ? 'Brand' : 'Brands'}
              </Text>
            </View>

            <TouchableOpacity
              onPress={onClose}
              style={styles.closeModalBtn}
              activeOpacity={0.7}
              hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
            >
              <XIcon size={16} color="#475569" />
            </TouchableOpacity>
          </View>

          {/* Clean Metric Summary Card */}
          <View style={styles.metricsSummaryPanel}>
            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>TOTAL CASES</Text>
              <Text style={styles.metricValue}>{formatNumber(companyCases)}</Text>
            </View>
            <View style={[styles.metricItem, styles.metricBorderLeft]}>
              <Text style={styles.metricLabel}>TOTAL BOTTLES</Text>
              <Text style={styles.metricValue}>{formatNumber(companyBottles)}</Text>
            </View>
          </View>

          {/* Single Ultra-Compact 40px Control Bar with Inline Dropdown */}
          <View style={styles.searchAndFilterRow}>
            {/* Search Box */}
            <View style={styles.searchWrapper}>
              <View style={{ marginRight: 6 }}>
                <SearchIcon size={15} color="#94A3B8" />
              </View>
              <TextInput
                style={styles.searchInput}
                placeholder="Search brand name..."
                placeholderTextColor="#94A3B8"
                value={searchTerm}
                onChangeText={setSearchTerm}
              />
              {searchTerm ? (
                <TouchableOpacity onPress={() => setSearchTerm('')} style={styles.clearBtn}>
                  <XIcon size={12} color="#94A3B8" />
                </TouchableOpacity>
              ) : null}
            </View>

            {/* Inline Dropdown Pill Button */}
            <View ref={sortBtnRef} collapsable={false}>
              <TouchableOpacity
                style={[
                  styles.sortDropdownPill,
                  sortBy !== 'default' ? styles.sortDropdownPillActive : null,
                ]}
                onPress={toggleSortDropdown}
                activeOpacity={0.75}
              >
                <SwapVertIcon size={15} color={sortBy !== 'default' ? '#FFFFFF' : '#334155'} />
                <Text
                  style={[
                    styles.sortDropdownPillText,
                    sortBy !== 'default' ? styles.sortDropdownPillTextActive : null,
                  ]}
                >
                  {getSortLabel()}
                </Text>
                <ChevronDownIcon size={14} color={sortBy !== 'default' ? '#FFFFFF' : '#334155'} />
              </TouchableOpacity>
            </View>
          </View>

          {/* Brand List (flex: 1 allows FlatList to shrink & scroll smoothly above keyboard) */}
          <FlatList
            data={sortedBrands}
            keyExtractor={(item) => item.id || item.name}
            style={{ flex: 1 }}
            contentContainerStyle={styles.listContent}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="on-drag"
            showsVerticalScrollIndicator={true}
            nestedScrollEnabled={true}
            ListEmptyComponent={
              <Text style={styles.emptyText}>No brands match "{searchTerm}"</Text>
            }
            renderItem={({ item }) => {
              const rawBData = item.data[period];
              const bCases = Math.round(rawBData.cases * scaleFactor);
              const bBottles = Math.round(rawBData.bottles * scaleFactor);

              return (
                <View style={styles.brandCard}>
                  <Text style={styles.brandName}>{item.name}</Text>
                  <View style={styles.brandMetrics}>
                    <View style={styles.brandMetricItem}>
                      <Text style={styles.brandMetricLabel}>CASES</Text>
                      <Text style={styles.brandMetricValPrimary}>{formatNumber(bCases)}</Text>
                    </View>
                    <View style={styles.brandMetricItem}>
                      <Text style={styles.brandMetricLabel}>BOTTLES</Text>
                      <Text style={styles.brandMetricValSecondary}>{formatNumber(bBottles)}</Text>
                    </View>
                  </View>
                </View>
              );
            }}
          />
        </View>
      </KeyboardAvoidingView>

      {/* Floating Inline Dropdown Card (Rendered via transparent Modal layer to float above all cards) */}
      <Modal
        visible={showSortDropdown}
        transparent={true}
        animationType="none"
        onRequestClose={() => setShowSortDropdown(false)}
        statusBarTranslucent
      >
        <TouchableOpacity
          style={styles.dropdownModalOverlay}
          activeOpacity={1}
          onPress={() => setShowSortDropdown(false)}
        >
          <View
            style={[
              styles.dropdownMenuCardModal,
              { top: dropdownPos.top, right: dropdownPos.right },
            ]}
          >
            {sortDropdownOptions.map((opt) => {
              const isSelected = sortBy === opt.key;
              const IconComp = opt.Icon;
              return (
                <TouchableOpacity
                  key={opt.key}
                  style={[
                    styles.dropdownMenuItem,
                    isSelected ? styles.dropdownMenuItemActive : null,
                  ]}
                  onPress={() => {
                    setSortBy(opt.key as BrandSortOption);
                    setShowSortDropdown(false);
                  }}
                  activeOpacity={0.75}
                >
                  <View style={styles.dropdownIconBox}>
                    <IconComp size={15} color={isSelected ? '#0F172A' : '#64748B'} />
                  </View>
                  <Text
                    style={[
                      styles.dropdownMenuItemText,
                      isSelected ? styles.dropdownMenuItemTextActive : null,
                    ]}
                  >
                    {opt.label}
                  </Text>
                  {isSelected && <CheckCircleIcon size={16} color="#0F172A" />}
                </TouchableOpacity>
              );
            })}
          </View>
        </TouchableOpacity>
      </Modal>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.65)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#F8FAFC',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '88%',
    height: '82%',
    paddingBottom: Platform.OS === 'ios' ? 24 : 14,
    overflow: 'hidden',
  },
  dragHeaderArea: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    alignItems: 'center',
    paddingTop: 10,
    paddingBottom: 2,
  },
  dragIndicatorPill: {
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#CBD5E1',
  },
  modalHeader: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 20,
    paddingTop: 6,
    paddingBottom: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  headerTitleWrapper: {
    flex: 1,
    marginRight: 12,
  },
  modalTitle: {
    color: '#0F172A',
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: -0.3,
  },
  modalSubtitle: {
    color: '#64748B',
    fontSize: 11.5,
    fontWeight: '600',
    marginTop: 2,
  },
  closeModalBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: '#F1F5F9',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  metricsSummaryPanel: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    paddingVertical: 12,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 4,
    elevation: 1,
  },
  metricItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricBorderLeft: {
    borderLeftWidth: 1,
    borderLeftColor: '#E2E8F0',
  },
  metricLabel: {
    fontSize: 8.5,
    color: '#64748B',
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  metricValue: {
    color: '#0F172A',
    fontSize: 15,
    fontWeight: '900',
    marginTop: 1,
  },
  searchAndFilterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: 16,
    marginTop: 12,
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
    height: 40,
  },
  searchInput: {
    flex: 1,
    fontSize: 13,
    fontWeight: '600',
    color: '#0F172A',
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
    backgroundColor: '#0F172A',
    borderColor: '#0F172A',
  },
  sortDropdownPillText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#334155',
  },
  sortDropdownPillTextActive: {
    color: '#FFFFFF',
  },
  dropdownModalOverlay: {
    flex: 1,
    backgroundColor: 'transparent',
  },
  dropdownMenuCardModal: {
    position: 'absolute',
    width: 215,
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    paddingVertical: 6,
    paddingHorizontal: 4,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.18,
    shadowRadius: 10,
    elevation: 15,
  },
  dropdownMenuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 9,
    paddingHorizontal: 10,
    borderRadius: 10,
  },
  dropdownMenuItemActive: {
    backgroundColor: '#F1F5F9',
  },
  dropdownIconBox: {
    width: 20,
    alignItems: 'center',
    marginRight: 6,
  },
  dropdownMenuItemText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#334155',
    flex: 1,
  },
  dropdownMenuItemTextActive: {
    color: '#0F172A',
    fontWeight: '800',
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  emptyText: {
    textAlign: 'center',
    color: '#94A3B8',
    fontSize: 12,
    fontWeight: '600',
    marginVertical: 24,
  },
  brandCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 14,
    marginBottom: 10,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 2,
  },
  brandName: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
    marginBottom: 8,
  },
  brandMetrics: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  brandMetricItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandMetricLabel: {
    fontSize: 8.5,
    fontWeight: '700',
    color: '#64748B',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  brandMetricValPrimary: {
    fontSize: 14,
    fontWeight: '900',
    color: '#0F172A',
    marginTop: 1,
  },
  brandMetricValSecondary: {
    fontSize: 14,
    fontWeight: '800',
    color: '#475569',
    marginTop: 1,
  },
});
