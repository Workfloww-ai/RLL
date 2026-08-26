import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { ChevronLeftIcon, ChevronRightIcon } from './Icons';

export interface BreadcrumbItem {
  label: string;
  onPress?: () => void;
}

export interface BreadcrumbHeaderProps {
  items: BreadcrumbItem[];
  onBackPress?: () => void;
  scaleFactor?: number;
}

export function BreadcrumbHeader({
  items,
  onBackPress,
  scaleFactor = 1,
}: BreadcrumbHeaderProps) {
  const scaledFontSize = (base: number) => Math.round(base * scaleFactor);

  return (
    <View style={styles.container}>
      {onBackPress && (
        <TouchableOpacity
          style={styles.backButton}
          onPress={onBackPress}
          activeOpacity={0.7}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <ChevronLeftIcon size={scaledFontSize(18)} color="#1E293B" />
        </TouchableOpacity>
      )}

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1;
          return (
            <React.Fragment key={`${item.label}-${idx}`}>
              {idx > 0 && (
                <View style={styles.separator}>
                  <ChevronRightIcon size={scaledFontSize(12)} color="#94A3B8" />
                </View>
              )}

              {isLast || !item.onPress ? (
                <Text
                  style={[
                    styles.currentText,
                    { fontSize: scaledFontSize(14) },
                  ]}
                  numberOfLines={1}
                >
                  {item.label}
                </Text>
              ) : (
                <TouchableOpacity
                  onPress={item.onPress}
                  activeOpacity={0.7}
                >
                  <Text
                    style={[
                      styles.linkText,
                      { fontSize: scaledFontSize(14) },
                    ]}
                    numberOfLines={1}
                  >
                    {item.label}
                  </Text>
                </TouchableOpacity>
              )}
            </React.Fragment>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  backButton: {
    paddingRight: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollContent: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  separator: {
    paddingHorizontal: 6,
    justifyContent: 'center',
    alignItems: 'center',
  },
  linkText: {
    fontWeight: '600',
    color: '#0284C7',
  },
  currentText: {
    fontWeight: '700',
    color: '#0F172A',
  },
});
