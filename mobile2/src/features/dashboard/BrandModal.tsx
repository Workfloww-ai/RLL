import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TextInput,
  TouchableOpacity,
  FlatList,
  TouchableWithoutFeedback,
} from 'react-native';
import { Company, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { XIcon } from '../../components/Icons';

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
      <View style={styles.modalOverlay}>
        <TouchableWithoutFeedback onPress={onClose}>
          <View style={StyleSheet.absoluteFill} />
        </TouchableWithoutFeedback>
        <View style={styles.modalContent}>
          {/* Header */}
          <View style={styles.modalHeader}>
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
            >
              <XIcon size={14} color="#FFFFFF" />
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
            <Text style={styles.searchIcon}>🔍</Text>
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
          >
            <Text style={styles.closeBtnText}>Close</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
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
  headerTitleWrapper: {
    flex: 1,
    marginRight: 8,
  },
  modalTitle: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
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
  metricsSummaryPanel: {
    flexDirection: 'row',
    backgroundColor: '#1E293B',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
  },
  metricItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricBorderLeft: {
    borderLeftWidth: 1,
    borderLeftColor: '#334155',
  },
  metricLabel: {
    fontSize: 8,
    color: '#94A3B8',
    fontWeight: '700',
  },
  metricValue: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 2,
  },
  searchWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 12,
    margin: 16,
    marginBottom: 8,
    paddingHorizontal: 12,
  },
  searchIcon: {
    fontSize: 12,
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 11,
    color: '#334155',
    paddingVertical: 8,
  },
  clearBtn: {
    padding: 6,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  emptyText: {
    textAlign: 'center',
    color: '#94A3B8',
    fontSize: 11,
    marginVertical: 20,
  },
  brandCard: {
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
  brandMetrics: {
    flexDirection: 'row',
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  brandMetricItem: {
    flex: 1,
    alignItems: 'center',
  },
  brandMetricLabel: {
    fontSize: 7,
    fontWeight: '700',
    color: '#94A3B8',
  },
  brandMetricValPrimary: {
    fontSize: 10,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 1,
  },
  brandMetricValSecondary: {
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
