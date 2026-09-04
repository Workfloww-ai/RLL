import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';

// Shared pulse animation hook
function usePulseAnim() {
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

  return pulseAnim;
}

// ─────────────────────────────────────────────────────────────
// 1. COMPANY CARD SKELETON
// ─────────────────────────────────────────────────────────────
export function CompanyCardSkeleton({ cardStyle }: { cardStyle?: object }) {
  const pulseAnim = usePulseAnim();

  return (
    <Animated.View style={[styles.card, { opacity: pulseAnim }, cardStyle]}>
      <View style={styles.cardMainRow}>
        <View style={styles.titleWrapper}>
          <View style={styles.nameRow}>
            <View style={styles.skeletonTitle} />
            <View style={styles.skeletonBadge} />
          </View>
          <View style={styles.skeletonSubText} />
        </View>

        <View style={styles.metricsRightRow}>
          <View style={styles.metricCell}>
            <View style={styles.skeletonValue} />
            <View style={styles.skeletonLabel} />
          </View>
          <View style={styles.metricCell}>
            <View style={styles.skeletonValue} />
            <View style={styles.skeletonLabel} />
          </View>
          <View style={styles.skeletonChevron} />
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

// ─────────────────────────────────────────────────────────────
// 2. GROUP / CASCADING CARD SKELETON
// ─────────────────────────────────────────────────────────────
export function GroupCardSkeleton() {
  const pulseAnim = usePulseAnim();

  return (
    <Animated.View style={[styles.card, { opacity: pulseAnim }]}>
      <View style={styles.cardMainRow}>
        <View style={{ flex: 1 }}>
          <View style={{ width: 140, height: 16, backgroundColor: '#CBD5E1', borderRadius: 6, marginBottom: 6 }} />
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <View style={{ width: 60, height: 12, backgroundColor: '#E2E8F0', borderRadius: 4 }} />
            <View style={{ width: 70, height: 12, backgroundColor: '#E2E8F0', borderRadius: 4 }} />
          </View>
        </View>

        <View style={styles.metricsRightRow}>
          <View style={styles.metricCell}>
            <View style={styles.skeletonValue} />
            <View style={styles.skeletonLabel} />
          </View>
          <View style={styles.metricCell}>
            <View style={styles.skeletonValue} />
            <View style={styles.skeletonLabel} />
          </View>
          <View style={styles.skeletonChevron} />
        </View>
      </View>
    </Animated.View>
  );
}

export function GroupListSkeletonList({ count = 5 }: { count?: number }) {
  return (
    <View style={styles.skeletonContainer}>
      {Array.from({ length: count }).map((_, index) => (
        <GroupCardSkeleton key={index} />
      ))}
    </View>
  );
}

// ─────────────────────────────────────────────────────────────
// 3. TSM CARD SKELETON
// ─────────────────────────────────────────────────────────────
export function TsmCardSkeleton() {
  const pulseAnim = usePulseAnim();

  return (
    <Animated.View style={[styles.card, { opacity: pulseAnim }]}>
      <View style={styles.cardMainRow}>
        <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center' }}>
          <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: '#E2E8F0', marginRight: 8 }} />
          <View style={{ flex: 1 }}>
            <View style={{ width: 120, height: 16, backgroundColor: '#CBD5E1', borderRadius: 6, marginBottom: 4 }} />
            <View style={{ width: 80, height: 12, backgroundColor: '#E2E8F0', borderRadius: 4 }} />
          </View>
        </View>

        <View style={styles.metricsRightRow}>
          <View style={styles.metricCell}>
            <View style={styles.skeletonValue} />
            <View style={styles.skeletonLabel} />
          </View>
          <View style={styles.metricCell}>
            <View style={styles.skeletonValue} />
            <View style={styles.skeletonLabel} />
          </View>
          <View style={styles.skeletonChevron} />
        </View>
      </View>
    </Animated.View>
  );
}

export function TsmListSkeletonList({ count = 5 }: { count?: number }) {
  return (
    <View style={styles.skeletonContainer}>
      {Array.from({ length: count }).map((_, index) => (
        <TsmCardSkeleton key={index} />
      ))}
    </View>
  );
}

// ─────────────────────────────────────────────────────────────
// 4. DEPOT CARD SKELETON
// ─────────────────────────────────────────────────────────────
export function DepotCardSkeleton() {
  const pulseAnim = usePulseAnim();

  return (
    <Animated.View style={[styles.card, { opacity: pulseAnim }]}>
      <View style={styles.cardMainRow}>
        <View style={{ flex: 1 }}>
          <View style={{ width: 130, height: 16, backgroundColor: '#CBD5E1', borderRadius: 6, marginBottom: 4 }} />
          <View style={{ width: 85, height: 12, backgroundColor: '#E2E8F0', borderRadius: 4 }} />
        </View>

        <View style={styles.metricsRightRow}>
          <View style={styles.metricCell}>
            <View style={styles.skeletonValue} />
            <View style={styles.skeletonLabel} />
          </View>
          <View style={styles.metricCell}>
            <View style={styles.skeletonValue} />
            <View style={styles.skeletonLabel} />
          </View>
          <View style={styles.skeletonChevron} />
        </View>
      </View>
    </Animated.View>
  );
}

export function DepotListSkeletonList({ count = 5 }: { count?: number }) {
  return (
    <View style={styles.skeletonContainer}>
      {Array.from({ length: count }).map((_, index) => (
        <DepotCardSkeleton key={index} />
      ))}
    </View>
  );
}

// ─────────────────────────────────────────────────────────────
// 5. PROFILE SCREEN SKELETON
// ─────────────────────────────────────────────────────────────
export function ProfileSkeleton() {
  const pulseAnim = usePulseAnim();

  return (
    <Animated.View style={[styles.skeletonContainer, { opacity: pulseAnim, padding: 16 }]}>
      {/* Profile Header Skeleton */}
      <View style={{ backgroundColor: '#0F2042', borderRadius: 20, padding: 20, flexDirection: 'row', alignItems: 'center', marginBottom: 20 }}>
        <View style={{ width: 60, height: 60, borderRadius: 16, backgroundColor: '#1E293B' }} />
        <View style={{ marginLeft: 16, flex: 1 }}>
          <View style={{ width: 150, height: 20, backgroundColor: '#334155', borderRadius: 6, marginBottom: 6 }} />
          <View style={{ width: 110, height: 14, backgroundColor: '#1E293B', borderRadius: 4 }} />
        </View>
      </View>

      {/* Account Details Box Skeleton */}
      <View style={{ backgroundColor: '#FFFFFF', borderRadius: 20, padding: 16, borderWidth: 1, borderColor: '#E2E8F0', marginBottom: 20 }}>
        <View style={{ width: 120, height: 14, backgroundColor: '#CBD5E1', borderRadius: 4, marginBottom: 16 }} />
        {[1, 2, 3, 4].map((i) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: '#F8FAFC', borderRadius: 14, padding: 12, marginBottom: 12 }}>
            <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: '#E2E8F0' }} />
            <View style={{ marginLeft: 12, flex: 1 }}>
              <View style={{ width: 80, height: 10, backgroundColor: '#E2E8F0', borderRadius: 4, marginBottom: 4 }} />
              <View style={{ width: 140, height: 14, backgroundColor: '#CBD5E1', borderRadius: 4 }} />
            </View>
          </View>
        ))}
      </View>
    </Animated.View>
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
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 10,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 3,
    elevation: 1,
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
    marginBottom: 4,
  },
  skeletonTitle: {
    width: 130,
    height: 16,
    backgroundColor: '#CBD5E1',
    borderRadius: 5,
  },
  skeletonBadge: {
    width: 45,
    height: 14,
    backgroundColor: '#E2E8F0',
    borderRadius: 4,
    marginLeft: 8,
  },
  skeletonSubText: {
    width: 60,
    height: 11,
    backgroundColor: '#E2E8F0',
    borderRadius: 4,
  },
  skeletonChevron: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: '#E2E8F0',
    marginLeft: 4,
  },
  metricsRightRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  metricCell: {
    alignItems: 'flex-end',
  },
  skeletonLabel: {
    width: 35,
    height: 8,
    backgroundColor: '#CBD5E1',
    borderRadius: 3,
    marginTop: 4,
  },
  skeletonValue: {
    width: 50,
    height: 14,
    backgroundColor: '#94A3B8',
    borderRadius: 4,
  },
});
