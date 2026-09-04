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
  subtitle?: string | React.ReactNode;
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
      <View style={styles.cardMainRow}>
        {/* Left Column: Title (Row 1), Subtitle (Row 2), Location Pill (Row 3) */}
        <View style={styles.titleContainer}>
          {/* Row 1: Name + Pinned Badge */}
          <View style={styles.titleBadgeRow}>
            {titleIcon && <View style={styles.iconWrapper}>{titleIcon}</View>}
            <Text style={[styles.titleText, { fontSize: scaledFontSize(14) }]} numberOfLines={1}>
              {title}
            </Text>
            {isPinned && (
              <View style={styles.pinnedTag}>
                <Text style={styles.pinnedText}>Pinned</Text>
              </View>
            )}
          </View>

          {/* Row 2: Subtitle & Company Badge */}
          <View style={styles.subtextContainer}>
            {!!subtitle && (
              typeof subtitle === 'string' ? (
                <Text style={[styles.subtitleText, { fontSize: scaledFontSize(11) }]} numberOfLines={1}>
                  {subtitle}
                </Text>
              ) : (
                subtitle
              )
            )}

            {!!companyBadge && (
              <View style={styles.companyBadgePill}>
                <Text style={[styles.companyBadgeText, { fontSize: scaledFontSize(10) }]} numberOfLines={1}>
                  {companyBadge}
                </Text>
              </View>
            )}
          </View>

          {/* Row 3: Dedicated Headquarter Location Pill */}
          {!!locationPill && (
            <View
              style={[
                styles.locationPillContainerRow3,
                pillTheme === 'red' ? styles.redPillContainer : styles.bluePillContainer,
              ]}
            >
              <LocationIcon
                size={scaledFontSize(9)}
                color={pillTheme === 'red' ? '#DC2626' : '#0284C7'}
              />
              <Text
                style={[
                  styles.locationPillText,
                  { fontSize: scaledFontSize(10) },
                  pillTheme === 'red' ? styles.redPillText : styles.bluePillText,
                ]}
                numberOfLines={1}
              >
                {locationPill.startsWith('Headquarter:') || locationPill.startsWith('Depot:') || locationPill.startsWith('HQ:')
                  ? locationPill
                  : `Headquarter: ${locationPill}`}
              </Text>
            </View>
          )}
        </View>

        {/* Right Column: Inline Metrics & Chevron */}
        <View style={styles.metricsRightRow}>
          {metrics.map((item, idx) => (
            <View key={`${item.label}-${idx}`} style={styles.metricCell}>
              <Text style={[styles.metricValue, { fontSize: scaledFontSize(14) }]}>
                {typeof item.value === 'number'
                  ? formatNumber(item.value)
                  : item.value}
              </Text>
              <Text style={[styles.metricLabel, { fontSize: scaledFontSize(9) }]}>
                {item.label.toUpperCase()}
              </Text>
            </View>
          ))}

          {!!onPress && (
            <View style={styles.chevronContainer}>
              <ChevronRightIcon size={scaledFontSize(16)} color="#94A3B8" />
            </View>
          )}
        </View>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 2,
    elevation: 1,
  },
  cardMainRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  titleContainer: {
    flex: 1,
    marginRight: 10,
  },
  titleBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconWrapper: {
    marginRight: 6,
  },
  titleText: {
    fontWeight: '800',
    color: '#0F172A',
    marginRight: 6,
    letterSpacing: -0.2,
    flexShrink: 1,
  },
  subtextContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 3,
  },
  subtitleText: {
    color: '#64748B',
    fontWeight: '500',
  },
  companyBadgePill: {
    backgroundColor: '#F1F5F9',
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 4,
    marginLeft: 4,
  },
  companyBadgeText: {
    color: '#475569',
    fontWeight: '600',
  },
  pinnedTag: {
    backgroundColor: '#1E293B',
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 4,
    marginRight: 4,
  },
  pinnedText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: '700',
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
    color: '#94A3B8',
    fontWeight: '700',
    letterSpacing: 0.5,
    marginTop: 1,
  },
  metricValue: {
    fontWeight: '900',
    color: '#0F172A',
  },
  chevronContainer: {
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 2,
  },
  locationPillContainerRow3: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
    marginTop: 4,
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
    marginLeft: 3,
  },
  bluePillText: {
    color: '#0284C7',
  },
  redPillText: {
    color: '#DC2626',
  },
});
