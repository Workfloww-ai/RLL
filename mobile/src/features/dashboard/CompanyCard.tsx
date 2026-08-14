import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Company, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { PinIcon } from '../../components/Icons';

interface CompanyCardProps {
  company: Company;
  period: Period;
  scaleFactor: number;
  onClick: () => void;
}

export function CompanyCard({
  company,
  period,
  scaleFactor,
  onClick,
}: CompanyCardProps) {
  const rawData = company.data[period];
  const cases = Math.round(rawData.cases * scaleFactor);
  const bottles = Math.round(rawData.bottles * scaleFactor);

  return (
    <TouchableOpacity
      style={[
        styles.card,
        company.isPinned ? styles.cardPinned : null,
      ]}
      onPress={onClick}
      activeOpacity={0.7}
    >
      <View style={styles.cardHeader}>
        <View style={styles.titleWrapper}>
          <View style={styles.nameRow}>
            <Text style={styles.companyName} numberOfLines={1}>
              {company.name}
            </Text>
            {company.isPinned ? (
              <View style={styles.pinnedBadge}>
                <PinIcon color="#FFFFFF" size={8} />
                <Text style={styles.pinnedBadgeText}>Pinned</Text>
              </View>
            ) : null}
          </View>
          <Text style={styles.brandCount}>
            {company.brands.length} {company.brands.length === 1 ? 'Brand' : 'Brands'}
          </Text>
        </View>
        <Text style={styles.arrowIcon}>➔</Text>
      </View>

      {/* Primary Metrics grid */}
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
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 14,
    marginBottom: 10,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  cardPinned: {
    borderColor: '#0F2042',
    backgroundColor: '#F8FAFC',
    borderLeftWidth: 4,
    borderLeftColor: '#F59E0B',
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
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  companyName: {
    fontSize: 13,
    fontWeight: '800',
    color: '#1E293B',
    flexShrink: 1,
  },
  pinnedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0F2042',
    borderRadius: 4,
    paddingHorizontal: 4,
    paddingVertical: 1,
    marginLeft: 6,
  },
  pinnedBadgeText: {
    color: '#FFFFFF',
    fontSize: 8,
    fontWeight: 'bold',
    marginLeft: 2,
  },
  brandCount: {
    fontSize: 10,
    color: '#94A3B8',
    fontWeight: '500',
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
    justifyContent: 'center',
  },
  metricLabel: {
    fontSize: 8,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.5,
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
});
