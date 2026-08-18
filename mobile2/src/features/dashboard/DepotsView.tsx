import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  Modal,
  FlatList,
  TouchableWithoutFeedback,
  PanResponder,
  BackHandler,
} from 'react-native';
import { Depot, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { XIcon, SearchIcon, LocationIcon, ChevronRightIcon } from '../../components/Icons';
import { DepotListSkeletonList } from '../../components/SkeletonLoaders';

interface DepotsViewProps {
  depots: Depot[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
  loading?: boolean;
}

export function DepotsView({
  depots,
  period,
  scaleFactor,
  selectedHq,
  loading = false,
}: DepotsViewProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeDepot, setActiveDepot] = useState<Depot | null>(null);

  // Hardware BackHandler to close active depot modal
  useEffect(() => {
    if (!activeDepot) return;
    const onBackPress = () => {
      setActiveDepot(null);
      return true;
    };
    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [activeDepot]);

  // Swipe-down PanResponder gesture to close modal
  const depotPanResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gestureState) => {
        return gestureState.dy > 10 && Math.abs(gestureState.dx) < 35;
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > 25) {
          setActiveDepot(null);
        }
      },
    })
  ).current;

  // Filter depots by HQ and Search Term
  const filteredDepots = depots.filter((d) => {
    const matchHq = selectedHq === 'All Headquarters' || d.hqName.toLowerCase() === selectedHq.toLowerCase();
    const matchSearch =
      d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      d.hqName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (d.address && d.address.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchHq && matchSearch;
  });

  const renderDepotItem = useCallback(
    ({ item: depot }: { item: typeof filteredDepots[0] }) => {
      const raw = depot.data[period];
      const cases = Math.round(raw.cases * scaleFactor);
      const bottles = Math.round(raw.bottles * scaleFactor);
      return (
        <TouchableOpacity
          style={styles.depotCard}
          onPress={() => setActiveDepot(depot)}
          activeOpacity={0.7}
        >
          <View style={styles.depotHeader}>
            <View style={styles.depotTitleWrapper}>
              <Text style={styles.depotName}>{depot.name}</Text>
              <View style={styles.hqSubtextRow}>
                <LocationIcon size={10} color="#94A3B8" />
                <Text style={styles.hqSubtext}>HQ: {depot.hqName}</Text>
              </View>
            </View>
            <ChevronRightIcon size={16} color="#94A3B8" />
          </View>
          <View style={styles.metricsGrid}>
            <View style={styles.metricCell}>
              <Text style={styles.metricLabel}>CASES</Text>
              <Text style={styles.metricValuePrimary}>{formatNumber(cases)}</Text>
            </View>
            <View style={styles.metricCell}>
              <Text style={styles.metricLabel}>BOTTLES</Text>
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
      {/* Search Bar */}
      <View style={styles.searchWrapper}>
        <View style={{ marginRight: 8 }}>
          <SearchIcon size={18} color="#94A3B8" />
        </View>
        <TextInput
          style={styles.searchInput}
          placeholder="Search depots..."
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

      {/* Depots Cards List */}
      {loading ? (
        <DepotListSkeletonList count={5} />
      ) : filteredDepots.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyText}>No depots found</Text>
        </View>
      ) : (
        <FlatList
          data={filteredDepots}
          keyExtractor={(item) => item.id}
          renderItem={renderDepotItem}
          contentContainerStyle={styles.listContent}
          initialNumToRender={10}
          maxToRenderPerBatch={8}
          windowSize={5}
          removeClippedSubviews={true}
          showsVerticalScrollIndicator={false}
        />
      )}

      {/* Depot Detail Modal */}
      <Modal
        visible={activeDepot !== null}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setActiveDepot(null)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setActiveDepot(null)}
        >
          <TouchableWithoutFeedback onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalContent}>
              {/* Drag Handle Indicator */}
              <View style={styles.dragHeaderArea} {...depotPanResponder.panHandlers}>
                <View style={styles.dragIndicatorPill} />
              </View>

              {/* Modal Header */}
              <View style={styles.modalHeader} {...depotPanResponder.panHandlers}>
                <View>
                  <Text style={styles.modalTitle} numberOfLines={1}>
                    {activeDepot?.name}
                  </Text>
                  <Text style={styles.modalSubtitle}>HQ: {activeDepot?.hqName}</Text>
                </View>
                <TouchableOpacity
                  onPress={() => setActiveDepot(null)}
                  style={styles.closeModalBtn}
                  activeOpacity={0.7}
                  hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                >
                  <XIcon size={18} color="#FFFFFF" />
                </TouchableOpacity>
              </View>

              {/* Brands list */}
              <Text style={styles.breakdownTitle}>Depot Brand Sales ({period})</Text>
              <FlatList
                data={activeDepot?.brands || []}
                keyExtractor={(item) => item.brandId}
                contentContainerStyle={styles.modalListContent}
                renderItem={({ item }) => {
                  const bRaw = item.data[period];
                  const bCases = Math.round(bRaw.cases * scaleFactor);
                  const bBottles = Math.round(bRaw.bottles * scaleFactor);

                  return (
                    <View style={styles.brandSalesItem}>
                      <Text style={styles.brandName}>{item.brandName}</Text>
                      <View style={styles.modalMetricsGrid}>
                        <View style={styles.modalMetricCell}>
                          <Text style={styles.modalMetricLabel}>CASES</Text>
                          <Text style={styles.modalMetricValPrimary}>{formatNumber(bCases)}</Text>
                        </View>
                        <View style={styles.modalMetricCell}>
                          <Text style={styles.modalMetricLabel}>BOTTLES</Text>
                          <Text style={styles.modalMetricValSecondary}>{formatNumber(bBottles)}</Text>
                        </View>
                      </View>
                    </View>
                  );
                }}
              />

              {/* Close Button */}
              <TouchableOpacity
                onPress={() => setActiveDepot(null)}
                style={styles.closeBtn}
                activeOpacity={0.8}
              >
                <Text style={styles.closeBtnText}>Close</Text>
              </TouchableOpacity>
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
  scrollList: {
    flex: 1,
  },
  listContent: {
    paddingBottom: 20,
  },
  depotCard: {
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
  depotHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  depotTitleWrapper: {
    flex: 1,
    marginRight: 8,
  },
  depotName: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
  },
  hqSubtextRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 2,
  },
  hqSubtext: {
    fontSize: 11,
    fontWeight: '600',
    color: '#64748B',
  },
  arrowIcon: {
    fontSize: 12,
    color: '#CBD5E1',
  },
  metricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#F1F5F9',
  },
  metricCell: {
    flex: 1,
    alignItems: 'center',
  },
  metricLabel: {
    fontSize: 8,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  metricValuePrimary: {
    fontSize: 14,
    fontWeight: '900',
    color: '#0F172A',
    marginTop: 2,
  },
  metricValueSecondary: {
    fontSize: 14,
    fontWeight: '800',
    color: '#334155',
    marginTop: 2,
  },
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
  modalTitle: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '800',
    maxWidth: '85%',
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
  breakdownTitle: {
    fontSize: 12,
    fontWeight: '800',
    color: '#64748B',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 8,
  },
  modalListContent: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  brandSalesItem: {
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
  modalMetricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    borderRadius: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  modalMetricCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalMetricLabel: {
    fontSize: 10,
    fontWeight: '800',
    color: '#64748B',
    letterSpacing: 0.5,
  },
  modalMetricValPrimary: {
    fontSize: 14,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 2,
  },
  modalMetricValSecondary: {
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
