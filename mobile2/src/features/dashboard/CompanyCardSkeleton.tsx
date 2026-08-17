import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';

interface CompanyCardSkeletonProps {
  cardStyle?: object;
}

export function CompanyCardSkeleton({ cardStyle }: CompanyCardSkeletonProps) {
  const pulseAnim = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 0.9,
          duration: 700,
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 0.4,
          duration: 700,
          useNativeDriver: true,
        }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [pulseAnim]);

  return (
    <Animated.View style={[styles.card, { opacity: pulseAnim }, cardStyle]}>
      {/* Card Header Skeleton */}
      <View style={styles.cardHeader}>
        <View style={styles.titleWrapper}>
          <View style={styles.nameRow}>
            <View style={styles.skeletonTitle} />
            <View style={styles.skeletonBadge} />
          </View>
          <View style={styles.skeletonSubText} />
        </View>
        <View style={styles.skeletonChevron} />
      </View>

      {/* Primary Metrics Inset Box Skeleton */}
      <View style={styles.metricsGrid}>
        <View style={styles.metricCell}>
          <View style={styles.skeletonLabel} />
          <View style={styles.skeletonValue} />
        </View>
        <View style={styles.metricCell}>
          <View style={styles.skeletonLabel} />
          <View style={styles.skeletonValue} />
        </View>
      </View>
    </Animated.View>
  );
}

export function CompanyListSkeletonList({ count = 5 }: { count?: number }) {
  return (
    <View style={styles.skeletonContainer}>
      {Array.from({ length: count }).map((_, index) => (
        <CompanyCardSkeleton key={index} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  skeletonContainer: {
    width: '100%',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 12,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  titleWrapper: {
    flex: 1,
    marginRight: 8,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  skeletonTitle: {
    width: 140,
    height: 18,
    backgroundColor: '#CBD5E1',
    borderRadius: 6,
  },
  skeletonBadge: {
    width: 50,
    height: 16,
    backgroundColor: '#E2E8F0',
    borderRadius: 6,
    marginLeft: 8,
  },
  skeletonSubText: {
    width: 65,
    height: 12,
    backgroundColor: '#E2E8F0',
    borderRadius: 4,
  },
  skeletonChevron: {
    width: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: '#E2E8F0',
  },
  metricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 8,
  },
  metricCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  skeletonLabel: {
    width: 45,
    height: 10,
    backgroundColor: '#CBD5E1',
    borderRadius: 4,
    marginBottom: 6,
  },
  skeletonValue: {
    width: 60,
    height: 20,
    backgroundColor: '#94A3B8',
    borderRadius: 6,
  },
});
