import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  TouchableOpacity,
  TouchableWithoutFeedback,
} from 'react-native';
import { XIcon } from './Icons';

export type SortOptionValue = string;

export interface SortOptionItem<T = string> {
  label: string;
  value: T;
}

export interface SortModalProps<T = string> {
  visible: boolean;
  onClose: () => void;
  selectedOption: T;
  onSelectOption: (option: T) => void;
  options?: SortOptionItem<T>[];
  scaleFactor?: number;
  title?: string;
}

export const DEFAULT_SORT_OPTIONS: SortOptionItem<string>[] = [
  { label: 'Name (A to Z)', value: 'az' },
  { label: 'Name (Z to A)', value: 'za' },
  { label: 'Cases: (High to Low)', value: 'cases_desc' },
  { label: 'Cases: (Low to High)', value: 'cases_asc' },
];

export function SortModal<T extends string = string>({
  visible,
  onClose,
  selectedOption,
  onSelectOption,
  options = DEFAULT_SORT_OPTIONS as SortOptionItem<T>[],
  scaleFactor = 1,
  title = 'Sort By',
}: SortModalProps<T>) {
  const scaledFontSize = (base: number) => Math.round(base * scaleFactor);

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <TouchableWithoutFeedback onPress={onClose}>
        <View style={styles.overlay}>
          <TouchableWithoutFeedback>
            <View style={styles.modalCard}>
              <View style={styles.header}>
                <Text style={[styles.headerTitle, { fontSize: scaledFontSize(16) }]}>
                  {title}
                </Text>
                <TouchableOpacity onPress={onClose} activeOpacity={0.7} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <XIcon size={scaledFontSize(18)} color="#64748B" />
                </TouchableOpacity>
              </View>

              {options.map((opt) => {
                const isSelected = selectedOption === opt.value;
                return (
                  <TouchableOpacity
                    key={String(opt.value)}
                    style={[
                      styles.optionRow,
                      isSelected && styles.selectedOptionRow,
                    ]}
                    onPress={() => {
                      onSelectOption(opt.value);
                      onClose();
                    }}
                    activeOpacity={0.75}
                  >
                    <Text
                      style={[
                        styles.optionText,
                        { fontSize: scaledFontSize(14) },
                        isSelected && styles.selectedOptionText,
                      ]}
                    >
                      {opt.label}
                    </Text>
                    {isSelected && <View style={styles.radioDot} />}
                  </TouchableOpacity>
                );
              })}
            </View>
          </TouchableWithoutFeedback>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.4)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalCard: {
    width: '100%',
    maxWidth: 360,
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 8,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  headerTitle: {
    fontWeight: '700',
    color: '#0F172A',
  },
  optionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 10,
    marginBottom: 4,
  },
  selectedOptionRow: {
    backgroundColor: '#EFF6FF',
  },
  optionText: {
    color: '#334155',
    fontWeight: '500',
  },
  selectedOptionText: {
    color: '#0D3B8E',
    fontWeight: '700',
  },
  radioDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#0D3B8E',
  },
});
