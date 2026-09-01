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
  const rawData = company.data?.[period] || { cases: company.cases || 0, bottles: company.bottles || 0 };
  const cases = Math.round((rawData.cases ?? company.cases ?? 0) * scaleFactor);
  const bottles = Math.round((rawData.bottles ?? company.bottles ?? 0) * scaleFactor);

  const cId = (company.id || '').toLowerCase();
  const cName = (company.name || '').toLowerCase();
  const isPinned = company.isPinned || cId === 'rll' || cName === 'rll' || cName.startsWith('rll') || cId.includes('diageo') || cName.includes('diageo');

  return (
    <TouchableOpacity
      style={[
        styles.card,
        isPinned ? styles.cardPinned : null,
        cardStyle,
      ]}
      onPress={onClick}
      activeOpacity={0.75}
    >
      {/* Left Column: Company Name & Brand Count */}
      <View style={styles.leftInfo}>
        <View style={styles.nameRow}>
          <Text style={styles.companyName} numberOfLines={2}>
            {company.name}
          </Text>
          {isPinned ? (
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

      {/* Right Column: Inline Metrics */}
      <View style={styles.rightSection}>
        <View style={styles.metricBlock}>
          <Text style={styles.metricLabel}>CASES</Text>
          <Text style={styles.casesValue}>{formatNumber(cases)}</Text>
        </View>

        <View style={styles.metricDivider} />

        <View style={styles.metricBlock}>
          <Text style={styles.metricLabel}>BOTTLES</Text>
          <Text style={styles.bottlesValue}>{formatNumber(bottles)}</Text>
        </View>

        <ChevronRightIcon size={15} color="#94A3B8" />
      </View>
    </TouchableOpacity>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginBottom: 8,
    minHeight: 68,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.02,
    shadowRadius: 3,
    elevation: 1,
  },
  cardPinned: {
    borderColor: '#CBD5E1',
    backgroundColor: '#FAFCFF',
  },
  leftInfo: {
    flex: 1,
    marginRight: 10,
    justifyContent: 'center',
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 6,
  },
  companyName: {
    fontSize: 14.5,
    fontWeight: '800',
    color: '#0F172A',
    flexShrink: 1,
    letterSpacing: -0.2,
    lineHeight: 19,
  },
  pinnedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0D3B8E',
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1.5,
    gap: 2,
  },
  pinnedBadgeText: {
    color: '#FFFFFF',
    fontSize: 8.5,
    fontWeight: '700',
  },
  brandCount: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
    marginTop: 1,
  },
  rightSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  metricBlock: {
    alignItems: 'flex-end',
    minWidth: 50,
  },
  metricLabel: {
    fontSize: 8.5,
    fontWeight: '700',
    color: '#64748B',
    letterSpacing: 0.4,
  },
  casesValue: {
    fontSize: 14.5,
    fontWeight: '800',
    color: '#0D3B8E',
    marginTop: 1,
  },
  bottlesValue: {
    fontSize: 14.5,
    fontWeight: '800',
    color: '#0F172A',
    marginTop: 1,
  },
  metricDivider: {
    width: 1,
    height: 24,
    backgroundColor: '#E2E8F0',
  },
});
