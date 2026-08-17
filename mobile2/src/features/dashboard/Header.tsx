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
  Image,
} from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { Period } from '../../types';
import {
  LocationIcon,
  CalendarIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from '../../components/Icons';

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
  fetchTimeMs?: number;
  processTimeMs?: number;
}

function formatDateDisplay(dateStr: string): string {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length === 3) {
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
  return dateStr;
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
  fetchTimeMs,
  processTimeMs,
}: HeaderProps) {
  const periods: Period[] = ['Daily', 'MTD', 'YTD'];
  const [showHqModal, setShowHqModal] = useState(false);
  const [pickerTarget, setPickerTarget] = useState<'from' | 'to' | null>(null);
  const [showDatePicker, setShowDatePicker] = useState<boolean>(false);

  const openDatePicker = (target: 'from' | 'to') => {
    setPickerTarget(target);
    setShowDatePicker(true);
  };

  const handleDateChange = (event: any, selectedDate?: Date) => {
    setShowDatePicker(Platform.OS === 'ios');
    if (selectedDate) {
      const year = selectedDate.getFullYear();
      const month = String(selectedDate.getMonth() + 1).padStart(2, '0');
      const day = String(selectedDate.getDate()).padStart(2, '0');
      const formatted = `${year}-${month}-${day}`;

      if (pickerTarget === 'from') {
        setDateFrom(formatted);
        if (period === 'Daily') {
          setDateTo(formatted);
        }
      } else if (pickerTarget === 'to') {
        setDateTo(formatted);
      }
    }
  };

  const handlePeriodChange = (p: Period) => {
    setPeriod(p);
    const targetDate = latestSaleDate || '2026-05-31';

    if (p === 'Daily') {
      setDateFrom(targetDate);
      setDateTo(targetDate);
    } else if (p === 'MTD') {
      const year = targetDate.substring(0, 4);
      const month = targetDate.substring(5, 7);
      setDateFrom(`${year}-${month}-01`);
      setDateTo(targetDate);
    } else if (p === 'YTD') {
      const year = parseInt(targetDate.substring(0, 4), 10);
      const month = parseInt(targetDate.substring(5, 7), 10);
      const fyStartYear = month >= 4 ? year : year - 1;
      setDateFrom(`${fyStartYear}-04-01`);
      setDateTo(targetDate);
    }
  };

  const adjustDate = (days: number) => {
    const baseDateStr = dateFrom || latestSaleDate || new Date().toISOString().split('T')[0];
    const parts = baseDateStr.split('-');
    const currentDate = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    currentDate.setDate(currentDate.getDate() + days);

    const y = currentDate.getFullYear();
    const m = String(currentDate.getMonth() + 1).padStart(2, '0');
    const d = String(currentDate.getDate()).padStart(2, '0');
    const dateStr = `${y}-${m}-${d}`;

    if (period === 'Daily') {
      setDateFrom(dateStr);
      setDateTo(dateStr);
    } else {
      setDateFrom(dateStr);
    }
  };

  const activePickerValue = () => {
    const rawStr = pickerTarget === 'to' ? dateTo : dateFrom;
    if (!rawStr) return new Date();
    const parts = rawStr.split('-');
    if (parts.length === 3) {
      return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    }
    return new Date();
  };

  return (
    <View style={styles.header}>
      {/* Row 1: Branding Logo & Title + Period Switcher */}
      <View style={styles.topRow}>
        <View style={styles.branding}>
          <View style={styles.logoCircle}>
            <Image
              source={require('../../assets/rll.png')}
              style={styles.logoImage}
              resizeMode="contain"
            />
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
              activeOpacity={0.8}
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
        {/* Headquarters Selector Pill */}
        <TouchableOpacity
          style={styles.hqSelectorPill}
          onPress={() => setShowHqModal(true)}
          activeOpacity={0.7}
        >
          <View style={styles.iconBox}>
            <LocationIcon size={14} color="#FFFFFF" />
          </View>
          <Text
            style={styles.hqText}
            numberOfLines={1}
            adjustsFontSizeToFit={true}
            minimumFontScale={0.7}
          >
            {selectedHq}
          </Text>
        </TouchableOpacity>

        {/* Date Controls Range Pill */}
        {period === 'Daily' ? (
          <View style={styles.dateControlsPill}>
            <TouchableOpacity onPress={() => adjustDate(-1)} style={styles.dateAdjustBtn}>
              <ChevronLeftIcon size={14} color="#94A3B8" />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.dateDisplayInline}
              onPress={() => openDatePicker('from')}
              activeOpacity={0.7}
            >
              <View style={styles.iconBox}>
                <CalendarIcon size={14} color="#FFFFFF" />
              </View>
              <Text style={styles.dateInputText} numberOfLines={1}>
                {formatDateDisplay(dateFrom || latestSaleDate || '') || 'Select Date'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={() => adjustDate(1)} style={styles.dateAdjustBtn}>
              <ChevronRightIcon size={14} color="#94A3B8" />
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.dateControlsPill}>
            <View style={styles.rangeInlineContainer}>
              <TouchableOpacity
                style={styles.dateFieldPair}
                onPress={() => openDatePicker('from')}
                activeOpacity={0.7}
              >
                <View style={styles.iconBox}>
                  <CalendarIcon size={14} color="#FFFFFF" />
                </View>
                <Text style={styles.rangeInputText} numberOfLines={1}>
                  {formatDateDisplay(dateFrom) || 'Start Date'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.dateFieldPair}
                onPress={() => openDatePicker('to')}
                activeOpacity={0.7}
              >
                <View style={styles.iconBox}>
                  <CalendarIcon size={14} color="#FFFFFF" />
                </View>
                <Text style={styles.rangeInputText} numberOfLines={1}>
                  {formatDateDisplay(dateTo) || 'End Date'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </View>

      {/* DatePicker Component */}
      {showDatePicker && (
        <DateTimePicker
          value={activePickerValue()}
          mode="date"
          display={Platform.OS === 'ios' ? 'spinner' : 'default'}
          onChange={handleDateChange}
        />
      )}

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
    backgroundColor: '#0A1128',
    borderBottomLeftRadius: 22,
    borderBottomRightRadius: 22,
    paddingHorizontal: 16,
    paddingTop: Platform.OS === 'ios' ? 14 : 18,
    paddingBottom: 16,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.18,
    shadowRadius: 10,
    elevation: 5,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  branding: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  logoCircle: {
    width: 40,
    height: 40,
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  logoImage: {
    width: 28,
    height: 28,
  },
  brandingText: {
    marginLeft: 10,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
  subtitle: {
    color: '#94A3B8',
    fontSize: 11.5,
    fontWeight: '500',
    marginTop: 1,
  },
  periodSwitcher: {
    flexDirection: 'row',
    backgroundColor: '#131F37',
    borderRadius: 12,
    padding: 3,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.12)',
  },
  periodBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 9,
  },
  periodBtnActive: {
    backgroundColor: '#FFFFFF',
  },
  periodBtnText: {
    fontSize: 11.5,
    color: '#94A3B8',
    fontWeight: '700',
  },
  periodBtnTextActive: {
    color: '#0F172A',
    fontWeight: '900',
  },
  controlsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  hqSelectorPill: {
    flex: 1,
    flexDirection: 'row',
    backgroundColor: '#131F37',
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    alignItems: 'center',
    overflow: 'hidden',
  },
  controlIcon: {
    fontSize: 13,
    marginRight: 5,
  },
  iconBox: {
    marginRight: 5,
    justifyContent: 'center',
    alignItems: 'center',
  },
  hqText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
    flex: 1,
  },
  dateControlsPill: {
    flex: 1.45,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#131F37',
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    overflow: 'hidden',
  },
  rangeInlineContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dateFieldPair: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
  calendarIcon: {
    fontSize: 11,
    marginRight: 2,
  },
  rangeInputText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'center',
    paddingVertical: 0,
    paddingHorizontal: 0,
    flex: 1,
  },
  dateControlsDaily: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  dateDisplayInline: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    paddingHorizontal: 2,
  },
  dateAdjustBtn: {
    paddingHorizontal: 6,
    paddingVertical: 4,
  },
  adjustText: {
    color: '#94A3B8',
    fontSize: 10,
  },
  dateInputText: {
    color: '#FFFFFF',
    fontSize: 11.5,
    fontWeight: '700',
    textAlign: 'center',
    paddingVertical: 0,
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

