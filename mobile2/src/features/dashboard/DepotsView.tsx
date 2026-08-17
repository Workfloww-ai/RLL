import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Modal,
  FlatList,
  TouchableWithoutFeedback,
} from 'react-native';
import { Depot, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { XIcon } from '../../components/Icons';

interface DepotsViewProps {
  depots: Depot[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
}

export function DepotsView({
  depots,
  period,
  scaleFactor,
  selectedHq,
}: DepotsViewProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeDepot, setActiveDepot] = useState<Depot | null>(null);

  // Filter depots by HQ and Search Term
  const filteredDepots = depots.filter((d) => {
    const matchHq = selectedHq === 'All Headquarters' || d.hqName.toLowerCase() === selectedHq.toLowerCase();
    const matchSearch =
      d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      d.hqName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (d.address && d.address.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchHq && matchSearch;
  });

  return (
    <View style={styles.container}>
      {/* Search Bar */}
      <View style={styles.searchWrapper}>
        <Text style={styles.searchIcon}>🔍</Text>
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
      {filteredDepots.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyText}>No depots found</Text>
        </View>
      ) : (
        <ScrollView style={styles.scrollList} contentContainerStyle={styles.listContent}>
          {filteredDepots.map((depot) => {
            const raw = depot.data[period];
            const cases = Math.round(raw.cases * scaleFactor);
            const bottles = Math.round(raw.bottles * scaleFactor);

            return (
              <TouchableOpacity
                key={depot.id}
                style={styles.depotCard}
                onPress={() => setActiveDepot(depot)}
                activeOpacity={0.7}
              >
                <View style={styles.depotHeader}>
                  <View style={styles.depotTitleWrapper}>
                    <Text style={styles.depotName}>{depot.name}</Text>
                    <Text style={styles.hqSubtext}>📍 HQ: {depot.hqName}</Text>
                  </View>
                  <Text style={styles.arrowIcon}>➔</Text>
                </View>

                {/* Metrics */}
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
          })}
        </ScrollView>
      )}

      {/* Depot Detail Modal */}
      <Modal
        visible={activeDepot !== null}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setActiveDepot(null)}
      >
      <View style={styles.modalOverlay}>
        <TouchableWithoutFeedback onPress={() => setActiveDepot(null)}>
          <View style={StyleSheet.absoluteFill} />
        </TouchableWithoutFeedback>
        <View style={styles.modalContent}>
            {/* Modal Header */}
            <View style={styles.modalHeader}>
              <View>
                <Text style={styles.modalTitle} numberOfLines={1}>
                  {activeDepot?.name}
                </Text>
                <Text style={styles.modalSubtitle}>HQ: {activeDepot?.hqName}</Text>
              </View>
              <TouchableOpacity
                onPress={() => setActiveDepot(null)}
                style={styles.closeModalBtn}
              >
                <XIcon size={14} color="#FFFFFF" />
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
            >
              <Text style={styles.closeBtnText}>Close</Text>
            </TouchableOpacity>
        </View>
      </View>
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
    fontSize: 13,
    fontWeight: '800',
    color: '#1E293B',
  },
  hqSubtext: {
    fontSize: 9,
    fontWeight: '600',
    color: '#94A3B8',
    marginTop: 2,
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
  },
  metricValuePrimary: {
    fontSize: 11,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 2,
  },
  metricValueSecondary: {
    fontSize: 11,
    fontWeight: '700',
    color: '#334155',
    marginTop: 2,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.6)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '85%',
    minHeight: '50%',
    paddingBottom: 24,
  },
  modalHeader: {
    backgroundColor: '#0F2042',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
    maxWidth: '85%',
  },
  modalSubtitle: {
    color: '#94A3B8',
    fontSize: 10,
    marginTop: 2,
  },
  closeModalBtn: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  breakdownTitle: {
    fontSize: 11,
    fontWeight: 'bold',
    color: '#64748B',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    padding: 16,
    paddingBottom: 4,
  },
  modalListContent: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  brandSalesItem: {
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 12,
    marginBottom: 8,
  },
  brandName: {
    fontSize: 11,
    fontWeight: 'bold',
    color: '#334155',
    marginBottom: 6,
  },
  modalMetricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  modalMetricCell: {
    flex: 1,
    alignItems: 'center',
  },
  modalMetricLabel: {
    fontSize: 7,
    fontWeight: '700',
    color: '#94A3B8',
  },
  modalMetricValPrimary: {
    fontSize: 10,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 1,
  },
  modalMetricValSecondary: {
    fontSize: 10,
    fontWeight: '700',
    color: '#475569',
    marginTop: 1,
  },
  closeBtn: {
    backgroundColor: '#0F2042',
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
    marginHorizontal: 16,
    marginTop: 8,
  },
  closeBtnText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: 'bold',
  },
});
