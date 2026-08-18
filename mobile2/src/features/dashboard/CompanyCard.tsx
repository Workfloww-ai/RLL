import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Company, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { PinIcon, ChevronRightIcon } from '../../components/Icons';

interface CompanyCardProps {
  company: Company;
  period: Period;
  scaleFactor: number;
  onClick: () => void;
  cardStyle?: object;
}

export const CompanyCard = React.memo(function CompanyCard({
  company,
  period,
  scaleFactor,
  onClick,
  cardStyle,
}: CompanyCardProps) {
  const rawData = company.data[period];
  const cases = Math.round(rawData.cases * scaleFactor);
  const bottles = Math.round(rawData.bottles * scaleFactor);

  return (
    <TouchableOpacity
      style={[
        styles.card,
        company.isPinned ? styles.cardPinned : null,
        cardStyle,
      ]}
      onPress={onClick}
      activeOpacity={0.75}
    >
      <View style={styles.cardHeader}>
        <View style={styles.titleWrapper}>
          <View style={styles.nameRow}>
            <Text style={styles.companyName} numberOfLines={1}>
              {company.name}
            </Text>
            {company.isPinned ? (
              <View style={styles.pinnedBadge}>
                <PinIcon color="#FFFFFF" size={9} />
                <Text style={styles.pinnedBadgeText}>Pinned</Text>
              </View>
            ) : null}
          </View>
          <Text style={styles.brandCount}>
            {company.brands.length} {company.brands.length === 1 ? 'Brand' : 'Brands'}
          </Text>
        </View>
        <ChevronRightIcon size={16} color="#94A3B8" />
      </View>

      {/* Primary Metrics Inset Box */}
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
});

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
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
  },
  cardPinned: {
    borderColor: '#E2E8F0',
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
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
    flexShrink: 1,
    letterSpacing: -0.2,
  },
  pinnedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0F172A',
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginLeft: 8,
    gap: 3,
  },
  pinnedBadgeText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: '700',
  },
  brandCount: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
    marginTop: 2,
  },
  metricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 8,
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
});
