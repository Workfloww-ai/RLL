import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Modal,
  FlatList,
  Platform,
} from 'react-native';
import { Period } from '../../types';

interface HeaderProps {
  period: Period;
  setPeriod: (period: Period) => void;
  dateFrom: string;
  setDateFrom: (date: string) => void;
  dateTo: string;
  setDateTo: (date: string) => void;
  selectedHq: string;
  setSelectedHq: (hq: string) => void;
  headquartersList: string[];
  latestSaleDate?: string;
}

export function Header({
  period,
  setPeriod,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  selectedHq,
  setSelectedHq,
  headquartersList,
  latestSaleDate,
}: HeaderProps) {
  const periods: Period[] = ['Daily', 'MTD', 'YTD'];
  const [showHqModal, setShowHqModal] = useState(false);

  const handlePeriodChange = (p: Period) => {
    setPeriod(p);
    const activeDate = dateTo || dateFrom || latestSaleDate || new Date().toISOString().split('T')[0];
    const year = activeDate.substring(0, 4);
    const month = activeDate.substring(5, 7);

    if (p === 'MTD') {
      setDateFrom(`${year}-${month}-01`);
      setDateTo(activeDate);
    } else if (p === 'YTD') {
      const m = parseInt(month, 10);
      const y = parseInt(year, 10);
      const fyStartYear = m >= 4 ? y : y - 1;
      setDateFrom(`${fyStartYear}-04-01`);
      setDateTo(activeDate);
    } else if (p === 'Daily') {
      setDateFrom(activeDate);
      setDateTo(activeDate);
    }
  };

  const adjustDate = (days: number) => {
    const currentDate = new Date(dateFrom || latestSaleDate || new Date());
    currentDate.setDate(currentDate.getDate() + days);
    const dateStr = currentDate.toISOString().split('T')[0];
    if (period === 'Daily') {
      setDateFrom(dateStr);
      setDateTo(dateStr);
    } else {
      setDateFrom(dateStr);
    }
  };

  return (
    <View style={styles.header}>
      {/* Row 1: Logo & Title + Period Switcher */}
      <View style={styles.topRow}>
        <View style={styles.branding}>
          <View style={styles.logoCircle}>
            <Text style={styles.logoText}>🍷</Text>
          </View>
          <View style={styles.brandingText}>
            <Text style={styles.title}>Sales Dashboard</Text>
            <Text style={styles.subtitle}>Rajasthan</Text>
          </View>
        </View>

        {/* Period Switcher */}
        <View style={styles.periodSwitcher}>
          {periods.map((p) => (
            <TouchableOpacity
              key={p}
              style={[
                styles.periodBtn,
                period === p ? styles.periodBtnActive : null,
              ]}
              onPress={() => handlePeriodChange(p)}
            >
              <Text
                style={[
                  styles.periodBtnText,
                  period === p ? styles.periodBtnTextActive : null,
                ]}
              >
                {p}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Row 2: Controls Bar */}
      <View style={styles.controlsRow}>
        {/* Headquarters Selector */}
        <TouchableOpacity
          style={[
            styles.hqSelector,
            period === 'Daily' ? styles.hqSelectorWide : styles.hqSelectorNarrow,
          ]}
          onPress={() => setShowHqModal(true)}
        >
          <Text style={styles.controlIcon}>📍</Text>
          <Text style={styles.hqText} numberOfLines={1}>
            {selectedHq}
          </Text>
          <Text style={styles.dropdownArrow}>▼</Text>
        </TouchableOpacity>

        {/* Date Controls (Increment/Decrement button + Date Input) */}
        {period === 'Daily' ? (
          <View style={styles.dateControlsDaily}>
            <TouchableOpacity onPress={() => adjustDate(-1)} style={styles.dateAdjustBtn}>
              <Text style={styles.adjustText}>◀</Text>
            </TouchableOpacity>
            <TextInput
              style={styles.dateInputText}
              value={dateFrom}
              onChangeText={(val) => {
                setDateFrom(val);
                setDateTo(val);
              }}
              placeholder="YYYY-MM-DD"
              placeholderTextColor="#94A3B8"
            />
            <TouchableOpacity onPress={() => adjustDate(1)} style={styles.dateAdjustBtn}>
              <Text style={styles.adjustText}>▶</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.dateControlsRange}>
            <TextInput
              style={styles.rangeInputText}
              value={dateFrom}
              onChangeText={setDateFrom}
              placeholder="Start"
              placeholderTextColor="#94A3B8"
            />
            <Text style={styles.rangeSeparator}>-</Text>
            <TextInput
              style={styles.rangeInputText}
              value={dateTo}
              onChangeText={setDateTo}
              placeholder="End"
              placeholderTextColor="#94A3B8"
            />
          </View>
        )}
      </View>

      {/* Headquarters Selector Modal */}
      <Modal
        visible={showHqModal}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setShowHqModal(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowHqModal(false)}
        >
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Select Headquarters</Text>
            <FlatList
              data={headquartersList}
              keyExtractor={(item) => item}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={[
                    styles.modalItem,
                    selectedHq === item ? styles.modalItemActive : null,
                  ]}
                  onPress={() => {
                    setSelectedHq(item);
                    setShowHqModal(false);
                  }}
                >
                  <Text
                    style={[
                      styles.modalItemText,
                      selectedHq === item ? styles.modalItemTextActive : null,
                    ]}
                  >
                    {item}
                  </Text>
                </TouchableOpacity>
              )}
            />
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    backgroundColor: '#0F2042',
    borderBottomLeftRadius: 20,
    borderBottomRightRadius: 20,
    paddingHorizontal: 14,
    paddingTop: Platform.OS === 'ios' ? 12 : 16,
    paddingBottom: 14,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
    elevation: 3,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  branding: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  logoCircle: {
    width: 28,
    height: 28,
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 1,
  },
  logoText: {
    fontSize: 16,
  },
  brandingText: {
    marginLeft: 8,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '800',
  },
  subtitle: {
    color: '#94A3B8',
    fontSize: 9,
    fontWeight: '500',
    marginTop: 1,
  },
  periodSwitcher: {
    flexDirection: 'row',
    backgroundColor: 'rgba(0, 0, 0, 0.25)',
    borderRadius: 8,
    padding: 2,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  periodBtn: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 6,
  },
  periodBtnActive: {
    backgroundColor: '#FFFFFF',
  },
  periodBtnText: {
    fontSize: 10,
    color: '#94A3B8',
    fontWeight: 'bold',
  },
  periodBtnTextActive: {
    color: '#0F2042',
  },
  controlsRow: {
    flexDirection: 'row',
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    borderRadius: 12,
    padding: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    alignItems: 'center',
  },
  hqSelector: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    alignItems: 'center',
  },
  hqSelectorWide: {
    flex: 1.2,
    marginRight: 6,
  },
  hqSelectorNarrow: {
    flex: 0.9,
    marginRight: 6,
  },
  controlIcon: {
    fontSize: 11,
    marginRight: 4,
  },
  hqText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: 'bold',
    flex: 1,
  },
  dropdownArrow: {
    color: '#94A3B8',
    fontSize: 8,
    marginLeft: 4,
  },
  dateControlsDaily: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    paddingHorizontal: 4,
  },
  dateAdjustBtn: {
    padding: 6,
  },
  adjustText: {
    color: '#94A3B8',
    fontSize: 9,
  },
  dateInputText: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: 'bold',
    textAlign: 'center',
    paddingVertical: Platform.OS === 'ios' ? 6 : 2,
  },
  dateControlsRange: {
    flex: 1.1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    paddingHorizontal: 6,
    justifyContent: 'space-between',
  },
  rangeInputText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: 'bold',
    width: 62,
    textAlign: 'center',
    paddingVertical: Platform.OS === 'ios' ? 6 : 2,
  },
  rangeSeparator: {
    color: '#94A3B8',
    fontSize: 9,
    fontWeight: 'bold',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContent: {
    width: '100%',
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 16,
    maxHeight: '60%',
  },
  modalTitle: {
    fontSize: 13,
    fontWeight: 'bold',
    color: '#0F2042',
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  modalItem: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 10,
    marginBottom: 4,
  },
  modalItemActive: {
    backgroundColor: '#EEF2F6',
  },
  modalItemText: {
    fontSize: 12,
    color: '#64748B',
    fontWeight: '600',
  },
  modalItemTextActive: {
    color: '#0F2042',
    fontWeight: 'bold',
  },
});
