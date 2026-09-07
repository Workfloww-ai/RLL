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
      <View style={styles.cardMainRow}>
        {/* Left Section: Company Name, Pinned Badge & Subtitle */}
        <View style={styles.titleWrapper}>
          <View style={styles.nameRow}>
            <Text style={styles.companyName}>
              {company.name}
            </Text>
            {company.isPinned ? (
              <View style={styles.pinnedBadge}>
                <PinIcon color="#FFFFFF" size={9} />
                <Text style={styles.pinnedBadgeText}>Pinned</Text>
              </View>
            ) : null}
          </View>

          <View style={styles.subtextRow}>
            <Text style={styles.subtext}>
              {company.brands.length} {company.brands.length === 1 ? 'Brand' : 'Brands'}
            </Text>
          </View>
        </View>

        {/* Right Section: Metrics (Cases & Bottles) + Chevron Arrow */}
        <View style={styles.metricsRightRow}>
          <View style={styles.metricCell}>
            <Text style={styles.casesValue}>{formatNumber(cases)}</Text>
            <Text style={styles.metricLabel}>CASES</Text>
          </View>

          <View style={styles.metricCell}>
            <Text style={styles.bottlesValue}>{formatNumber(bottles)}</Text>
            <Text style={styles.metricLabel}>BOTTLES</Text>
          </View>

          <ChevronRightIcon size={16} color="#94A3B8" />
        </View>
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
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 10,
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
  cardMainRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  titleWrapper: {
    flex: 1,
    marginRight: 10,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  companyName: {
    fontSize: 14.5,
    fontWeight: '800',
    color: '#0F172A',
    letterSpacing: -0.2,
    lineHeight: 19,
  },
  pinnedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0F172A',
    borderRadius: 6,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginLeft: 6,
    gap: 3,
  },
  pinnedBadgeText: {
    color: '#FFFFFF',
    fontSize: 8.5,
    fontWeight: '700',
  },
  subtextRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
    flexWrap: 'wrap',
  },
  subtext: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
  },
  subtextDot: {
    fontSize: 11,
    color: '#94A3B8',
    fontWeight: '600',
  },
  hqPill: {
    backgroundColor: '#F1F5F9',
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 1,
  },
  hqPillText: {
    fontSize: 10,
    color: '#475569',
    fontWeight: '600',
  },
  metricsRightRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  metricCell: {
    alignItems: 'flex-end',
  },
  metricLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: '#94A3B8',
    letterSpacing: 0.5,
    marginTop: 1,
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
  },
});
