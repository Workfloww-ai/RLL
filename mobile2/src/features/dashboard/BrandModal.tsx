import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TextInput,
  TouchableOpacity,
  FlatList,
  TouchableWithoutFeedback,
  PanResponder,
  BackHandler,
} from 'react-native';
import { Company, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { XIcon, SearchIcon } from '../../components/Icons';

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

  // Handle hardware Back button to close modal
  useEffect(() => {
    if (!company) return;
    const onBackPress = () => {
      onClose();
      return true;
    };
    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [company, onClose]);

  // Swipe-down PanResponder gesture to close modal on swipe down
  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gestureState) => {
        return gestureState.dy > 10 && Math.abs(gestureState.dx) < 35;
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > 25) {
          onClose();
        }
      },
    })
  ).current;

  if (!company) return null;

  const rawCompanyData = company.data[period];
  const companyCases = Math.round(rawCompanyData.cases * scaleFactor);
  const companyBottles = Math.round(rawCompanyData.bottles * scaleFactor);

  // Filter brands based on search
  const filteredBrands = company.brands.filter((b) =>
    b.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <Modal
      visible={company !== null}
      transparent={true}
      animationType="slide"
      onRequestClose={onClose}
    >
      <TouchableOpacity
        style={styles.modalOverlay}
        activeOpacity={1}
        onPress={onClose}
      >
        <TouchableWithoutFeedback onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalContent}>
            {/* Top Drag Handle Indicator for Swipe Down */}
            <View style={styles.dragHeaderArea} {...panResponder.panHandlers}>
              <View style={styles.dragIndicatorPill} />
            </View>

            {/* Header */}
            <View style={styles.modalHeader} {...panResponder.panHandlers}>
              <View style={styles.headerTitleWrapper}>
                <Text style={styles.modalTitle} numberOfLines={1}>
                  {company.name}
                </Text>
                <Text style={styles.modalSubtitle}>
                  {company.brands.length} Active {company.brands.length === 1 ? 'Brand' : 'Brands'}
                </Text>
              </View>

              {/* Prominent Large Cross Button */}
              <TouchableOpacity
                onPress={onClose}
                style={styles.closeModalBtn}
                activeOpacity={0.7}
                hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
              >
                <XIcon size={18} color="#FFFFFF" />
              </TouchableOpacity>
            </View>

            {/* Quick Metrics summary panel */}
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

            {/* Search bar inside Modal */}
            <View style={styles.searchWrapper}>
              <View style={{ marginRight: 8 }}>
                <SearchIcon size={18} color="#94A3B8" />
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
                  <XIcon size={14} color="#94A3B8" />
                </TouchableOpacity>
              ) : null}
            </View>

            {/* Brand List */}
            <FlatList
              data={filteredBrands}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.listContent}
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

            {/* Bottom Close Button */}
            <TouchableOpacity
              onPress={onClose}
              style={styles.closeBtn}
              activeOpacity={0.8}
            >
              <Text style={styles.closeBtnText}>Close</Text>
            </TouchableOpacity>
          </View>
        </TouchableWithoutFeedback>
      </TouchableOpacity>
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
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '85%',
    paddingBottom: 20,
  },
  dragHeaderArea: {
    backgroundColor: '#0F2042',
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
    backgroundColor: 'rgba(255, 255, 255, 0.3)',
  },
  modalHeader: {
    backgroundColor: '#0F2042',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitleWrapper: {
    flex: 1,
    marginRight: 12,
  },
  modalTitle: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: -0.3,
  },
  modalSubtitle: {
    color: '#94A3B8',
    fontSize: 12,
    fontWeight: '600',
    marginTop: 3,
  },
  closeModalBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
  },
  metricsSummaryPanel: {
    flexDirection: 'row',
    backgroundColor: '#0B192C',
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.08)',
  },
  metricItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricBorderLeft: {
    borderLeftWidth: 1,
    borderLeftColor: 'rgba(255, 255, 255, 0.1)',
  },
  metricLabel: {
    fontSize: 8,
    color: '#94A3B8',
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  metricValue: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '900',
    marginTop: 2,
  },
  searchWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    marginHorizontal: 16,
    marginTop: 14,
    marginBottom: 10,
    paddingHorizontal: 14,
  },
  searchIcon: {
    fontSize: 14,
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 13,
    fontWeight: '500',
    color: '#334155',
    paddingVertical: 10,
  },
  clearBtn: {
    padding: 6,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  emptyText: {
    textAlign: 'center',
    color: '#94A3B8',
    fontSize: 12,
    fontWeight: '600',
    marginVertical: 24,
  },
  brandCard: {
    backgroundColor: '#F8FAFC',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 14,
    marginBottom: 10,
  },
  brandName: {
    fontSize: 14,
    fontWeight: '800',
    color: '#1E293B',
    marginBottom: 8,
  },
  brandMetrics: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
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
    fontSize: 8,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  brandMetricValPrimary: {
    fontSize: 14,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 2,
  },
  brandMetricValSecondary: {
    fontSize: 14,
    fontWeight: '800',
    color: '#334155',
    marginTop: 2,
  },
  closeBtn: {
    backgroundColor: '#0F2042',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
    marginHorizontal: 16,
    marginTop: 8,
  },
  closeBtnText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '800',
  },
});
