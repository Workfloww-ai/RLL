import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { ChevronLeftIcon, ChevronRightIcon, ChevronDownIcon } from './Icons';

export interface PaginationBarProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  perPage: number;
  onPageChange: (page: number) => void;
  onOpenPerPageModal?: () => void;
  scaleFactor?: number;
}

export function PaginationBar({
  currentPage,
  totalPages,
  totalItems,
  perPage,
  onPageChange,
  onOpenPerPageModal,
  scaleFactor = 1,
}: PaginationBarProps) {
  const scaledFontSize = (base: number) => Math.round(base * scaleFactor);

  if (totalItems <= 0) return null;

  return (
    <View style={styles.container}>
      {/* Per Page Limit Trigger */}
      {onOpenPerPageModal ? (
        <TouchableOpacity
          style={styles.perPageButton}
          onPress={onOpenPerPageModal}
          activeOpacity={0.7}
        >
          <Text style={[styles.perPageText, { fontSize: scaledFontSize(12) }]}>
            {perPage} / page
          </Text>
          <ChevronDownIcon size={scaledFontSize(12)} color="#64748B" />
        </TouchableOpacity>
      ) : (
        <View />
      )}

      {/* Page Info */}
      <Text style={[styles.pageInfoText, { fontSize: scaledFontSize(12) }]}>
        Page {currentPage} of {totalPages || 1} ({totalItems})
      </Text>

      {/* Navigation Buttons */}
      <View style={styles.navGroup}>
        <TouchableOpacity
          style={[
            styles.navButton,
            currentPage <= 1 && styles.disabledButton,
          ]}
          onPress={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          activeOpacity={0.7}
        >
          <ChevronLeftIcon
            size={scaledFontSize(16)}
            color={currentPage <= 1 ? '#CBD5E1' : '#0F172A'}
          />
        </TouchableOpacity>

        <TouchableOpacity
          style={[
            styles.navButton,
            currentPage >= totalPages && styles.disabledButton,
          ]}
          onPress={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          activeOpacity={0.7}
        >
          <ChevronRightIcon
            size={scaledFontSize(16)}
            color={currentPage >= totalPages ? '#CBD5E1' : '#0F172A'}
          />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: '#E2E8F0',
  },
  perPageButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F1F5F9',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  perPageText: {
    color: '#0F172A',
    fontWeight: '600',
    marginRight: 4,
  },
  pageInfoText: {
    color: '#64748B',
    fontWeight: '500',
  },
  navGroup: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  navButton: {
    backgroundColor: '#F1F5F9',
    width: 32,
    height: 32,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 6,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  disabledButton: {
    backgroundColor: '#F8FAFC',
    borderColor: '#F1F5F9',
  },
});
