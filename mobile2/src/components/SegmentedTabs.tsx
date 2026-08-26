import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';

export type GroupTabType = 'brands' | 'licensees' | 'companies' | 'ase';

export interface TabItem {
  key: string;
  label: string;
  icon?: React.ReactNode;
}

export interface SegmentedTabsProps {
  tabs: [TabItem, TabItem];
  activeTabKey: string;
  onTabChange: (tabKey: string) => void;
  scaleFactor?: number;
}

export function SegmentedTabs({
  tabs,
  activeTabKey,
  onTabChange,
  scaleFactor = 1,
}: SegmentedTabsProps) {
  const scaledFontSize = (base: number) => Math.round(base * scaleFactor);

  return (
    <View style={styles.container}>
      {tabs.map((tab) => {
        const isActive = activeTabKey === tab.key;
        return (
          <TouchableOpacity
            key={tab.key}
            style={[
              styles.tabButton,
              isActive && styles.activeTabButton,
            ]}
            onPress={() => onTabChange(tab.key)}
            activeOpacity={0.8}
          >
            {tab.icon && (
              <View style={styles.iconWrapper}>
                {React.cloneElement(tab.icon as React.ReactElement<any>, {
                  color: isActive ? '#FFFFFF' : '#475569',
                  size: scaledFontSize(14),
                })}
              </View>
            )}
            <Text
              style={[
                styles.tabText,
                { fontSize: scaledFontSize(13) },
                isActive && styles.activeTabText,
              ]}
              numberOfLines={1}
            >
              {tab.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    backgroundColor: '#F1F5F9',
    borderRadius: 12,
    padding: 3,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    flex: 1,
  },
  tabButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    borderRadius: 9,
    gap: 6,
  },
  activeTabButton: {
    backgroundColor: '#0F172A',
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.15,
    shadowRadius: 2,
    elevation: 2,
  },
  iconWrapper: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  tabText: {
    color: '#475569',
    fontWeight: '600',
  },
  activeTabText: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
});
