import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { formatNumber } from '../lib/utils';
import { ChevronRightIcon, LocationIcon } from './Icons';

export interface MetricItem {
  label: string;
  value: number | string;
}

export interface MetricsCardProps {
  title: string;
  subtitle?: string;
  companyBadge?: string;
  titleIcon?: React.ReactNode;
  metrics: MetricItem[];
  locationPill?: string;
  pillTheme?: 'blue' | 'red';
  isPinned?: boolean;
  onPress?: () => void;
  scaleFactor?: number;
}

export function MetricsCard({
  title,
  subtitle,
  companyBadge,
  titleIcon,
  metrics,
  locationPill,
  pillTheme = 'blue',
  isPinned = false,
  onPress,
  scaleFactor = 1,
}: MetricsCardProps) {
  const scaledFontSize = (base: number) => Math.round(base * scaleFactor);

  return (
    <TouchableOpacity
      style={styles.card}
      onPress={onPress}
      disabled={!onPress}
      activeOpacity={0.75}
    >
      {/* Header Row: Title, Badges & Chevron */}
      <View style={styles.headerRow}>
        <View style={styles.titleContainer}>
          <View style={styles.titleBadgeRow}>
            {titleIcon && <View style={styles.iconWrapper}>{titleIcon}</View>}
            <Text
              style={[styles.titleText, { fontSize: scaledFontSize(15) }]}
              numberOfLines={1}
            >
              {title}
            </Text>
            {isPinned && (
              <View style={styles.pinnedTag}>
                <Text style={styles.pinnedText}>Pinned</Text>
              </View>
            )}
          </View>

          {/* Subtitle Line or Badges */}
          {!!subtitle && (
            <Text
              style={[styles.subtitleText, { fontSize: scaledFontSize(12) }]}
              numberOfLines={1}
            >
              {subtitle}
            </Text>
          )}

          {/* Company Badge (for Brands) */}
          {!!companyBadge && (
            <View style={styles.companyBadgePill}>
              <Text
                style={[
                  styles.companyBadgeText,
                  { fontSize: scaledFontSize(11) },
                ]}
              >
                {companyBadge}
              </Text>
            </View>
          )}
        </View>

        {!!onPress && (
          <View style={styles.chevronContainer}>
            <ChevronRightIcon size={scaledFontSize(18)} color="#94A3B8" />
          </View>
        )}
      </View>

      {/* Metrics Grid */}
      <View style={styles.metricsBox}>
        {metrics.map((item, idx) => (
          <React.Fragment key={`${item.label}-${idx}`}>
            {idx > 0 && <View style={styles.metricDivider} />}
            <View style={styles.metricItem}>
              <Text
                style={[styles.metricLabel, { fontSize: scaledFontSize(10) }]}
              >
                {item.label.toUpperCase()}
              </Text>
              <Text
                style={[styles.metricValue, { fontSize: scaledFontSize(15) }]}
              >
                {typeof item.value === 'number'
                  ? formatNumber(item.value)
                  : item.value}
              </Text>
            </View>
          </React.Fragment>
        ))}
      </View>

      {/* Location Pill */}
      {!!locationPill && (
        <View
          style={[
            styles.locationPillContainer,
            pillTheme === 'red' ? styles.redPillContainer : styles.bluePillContainer,
          ]}
        >
          <LocationIcon
            size={scaledFontSize(12)}
            color={pillTheme === 'red' ? '#DC2626' : '#0284C7'}
          />
          <Text
            style={[
              styles.locationPillText,
              { fontSize: scaledFontSize(11) },
              pillTheme === 'red' ? styles.redPillText : styles.bluePillText,
            ]}
            numberOfLines={1}
          >
            {locationPill}
          </Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 2,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  titleContainer: {
    flex: 1,
    marginRight: 8,
  },
  titleBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  iconWrapper: {
    marginRight: 6,
  },
  titleText: {
    fontWeight: '800',
    color: '#0F172A',
    marginRight: 6,
    flexShrink: 1,
  },
  subtitleText: {
    color: '#64748B',
    marginTop: 3,
    fontWeight: '500',
  },
  companyBadgePill: {
    backgroundColor: '#F1F5F9',
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    marginTop: 4,
  },
  companyBadgeText: {
    color: '#475569',
    fontWeight: '600',
  },
  pinnedTag: {
    backgroundColor: '#1E293B',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  pinnedText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '600',
  },
  chevronContainer: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  metricsBox: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'space-around',
    borderWidth: 1,
    borderColor: '#F1F5F9',
  },
  metricItem: {
    flex: 1,
    alignItems: 'center',
  },
  metricDivider: {
    width: 1,
    height: 24,
    backgroundColor: '#CBD5E1',
  },
  metricLabel: {
    color: '#64748B',
    fontWeight: '600',
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  metricValue: {
    fontWeight: '800',
    color: '#0F172A',
  },
  locationPillContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 20,
    marginTop: 10,
    borderWidth: 1,
  },
  bluePillContainer: {
    backgroundColor: '#F0F9FF',
    borderColor: '#BAE6FD',
  },
  redPillContainer: {
    backgroundColor: '#FEF2F2',
    borderColor: '#FCA5A5',
  },
  locationPillText: {
    fontWeight: '600',
    marginLeft: 4,
  },
  bluePillText: {
    color: '#0284C7',
  },
  redPillText: {
    color: '#DC2626',
  },
});
