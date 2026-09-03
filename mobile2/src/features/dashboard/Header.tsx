import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  FlatList,
  Platform,
  BackHandler,
} from 'react-native';
import { Period } from '../../types';
import {
  LocationIcon,
  CalendarIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronDownIcon,
  CheckCircleIcon,
  XIcon,
} from '../../components/Icons';
import LogoSvg from '../../assets/rll logo.svg';

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
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const mIdx = parseInt(parts[1], 10) - 1;
    if (mIdx >= 0 && mIdx < 12) {
      return `${parts[2]} ${months[mIdx]} ${parts[0]}`;
    }
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
  return dateStr;
}

function formatShortDateDisplay(dateStr: string, includeYear: boolean = false): string {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length === 3) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const mIdx = parseInt(parts[1], 10) - 1;
    if (mIdx >= 0 && mIdx < 12) {
      return includeYear ? `${parts[2]} ${months[mIdx]} '${parts[0].slice(2)}` : `${parts[2]} ${months[mIdx]}`;
    }
  }
  return dateStr;
}

const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

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
  const [pickerTarget, setPickerTarget] = useState<'from' | 'to' | null>(null);
  const [showDatePicker, setShowDatePicker] = useState<boolean>(false);
  const [calendarViewDate, setCalendarViewDate] = useState<Date>(() => new Date(2026, 4, 31));
  const [pickerViewMode, setPickerViewMode] = useState<'days' | 'months' | 'years'>('days');
  const [yearRangeStart, setYearRangeStart] = useState<number>(2020);

  // Sync calendar view month/year when opening picker
  useEffect(() => {
    if (showDatePicker) {
      setPickerViewMode('days');
      const activeStr = pickerTarget === 'to' ? dateTo : dateFrom;
      if (activeStr) {
        const parts = activeStr.split('-');
        if (parts.length === 3) {
          const yr = parseInt(parts[0], 10);
          setCalendarViewDate(new Date(yr, parseInt(parts[1], 10) - 1, parseInt(parts[2], 10)));
          setYearRangeStart(Math.floor(yr / 12) * 12);
        }
      }
    }
  }, [showDatePicker, pickerTarget, dateFrom, dateTo]);

  // Hardware BackHandler for Header modals
  useEffect(() => {
    if (!showHqModal && !showDatePicker) return;
    const onBackPress = () => {
      if (showHqModal) setShowHqModal(false);
      if (showDatePicker) {
        if (pickerViewMode !== 'days') {
          setPickerViewMode('days');
        } else {
          setShowDatePicker(false);
        }
      }
      return true;
    };
    const subscription = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => subscription.remove();
  }, [showHqModal, showDatePicker, pickerViewMode]);

  const openDatePicker = (target: 'from' | 'to') => {
    setPickerTarget(target);
    setShowDatePicker(true);
  };

  const handlePeriodChange = (p: Period) => {
    setPeriod(p);
    const targetDate = dateTo || latestSaleDate || '2026-07-31';

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

  const changeCalendarMonth = (offset: number) => {
    setCalendarViewDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + offset, 1));
  };

  const changeCalendarYear = (offset: number) => {
    setCalendarViewDate((prev) => new Date(prev.getFullYear() + offset, prev.getMonth(), 1));
  };

  const handleSelectDay = (dateStr: string) => {
    if (pickerTarget === 'to') {
      setDateTo(dateStr);
    } else {
      setDateFrom(dateStr);
      if (period === 'Daily') {
        setDateTo(dateStr);
      }
    }
  };

  const getCalendarDays = () => {
    const year = calendarViewDate.getFullYear();
    const month = calendarViewDate.getMonth();

    const firstDayOfWeek = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const daysInPrevMonth = new Date(year, month, 0).getDate();

    const days: { day: number; isCurrent: boolean; dateStr: string }[] = [];

    // Prev month padding
    for (let i = firstDayOfWeek - 1; i >= 0; i--) {
      const pDay = daysInPrevMonth - i;
      const prevDate = new Date(year, month - 1, pDay);
      const y = prevDate.getFullYear();
      const m = String(prevDate.getMonth() + 1).padStart(2, '0');
      const d = String(pDay).padStart(2, '0');
      days.push({ day: pDay, isCurrent: false, dateStr: `${y}-${m}-${d}` });
    }

    // Current month days
    for (let d = 1; d <= daysInMonth; d++) {
      const m = String(month + 1).padStart(2, '0');
      const dayStr = String(d).padStart(2, '0');
      days.push({ day: d, isCurrent: true, dateStr: `${year}-${m}-${dayStr}` });
    }

    // Next month padding to complete exactly 42 grid cells
    let nextDayNum = 1;
    while (days.length < 42) {
      const nextDate = new Date(year, month + 1, nextDayNum);
      const y = nextDate.getFullYear();
      const m = String(nextDate.getMonth() + 1).padStart(2, '0');
      const dayStr = String(nextDayNum).padStart(2, '0');
      days.push({ day: nextDayNum, isCurrent: false, dateStr: `${y}-${m}-${dayStr}` });
      nextDayNum++;
    }

    return days;
  };

  return (
    <View style={styles.header}>
      {/* Row 1: Branding (Logo + Title) + Headquarters Dropdown Pill */}
      <View style={styles.topRow}>
        <View style={styles.branding}>
          <View style={styles.logoBox}>
            <LogoSvg width={28} height={28} />
          </View>
          <Text style={styles.title}>LucidX360</Text>
        </View>

        {/* Minimalist Headquarters Selector Pill */}
        <TouchableOpacity
          style={styles.hqSelectorPill}
          onPress={() => setShowHqModal(true)}
          activeOpacity={0.75}
        >
          <View style={styles.iconBox}>
            <LocationIcon size={13} color="#0D3B8E" />
          </View>
          <Text
            style={styles.hqText}
            numberOfLines={1}
            adjustsFontSizeToFit={true}
            minimumFontScale={0.75}
          >
            {selectedHq}
          </Text>
          <ChevronDownIcon size={14} color="#0D3B8E" />
        </TouchableOpacity>
      </View>

      {/* Row 2: Period Switcher (Daily | MTD | YTD) + Date Controls */}
      <View style={styles.controlsRow}>
        {/* Minimalist Period Switcher */}
        <View style={styles.periodSwitcher}>
          {periods.map((p) => {
            const isActive = period === p;
            return (
              <TouchableOpacity
                key={p}
                style={[
                  styles.periodBtn,
                  isActive ? styles.periodBtnActive : null,
                ]}
                onPress={() => handlePeriodChange(p)}
                activeOpacity={0.8}
              >
                <Text
                  style={[
                    styles.periodBtnText,
                    isActive ? styles.periodBtnTextActive : null,
                  ]}
                >
                  {p}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Minimalist Date Controls Pill */}
        {period === 'Daily' ? (
          <View style={styles.dateControlsPill}>
            <TouchableOpacity onPress={() => adjustDate(-1)} style={styles.dateAdjustBtn} activeOpacity={0.7}>
              <ChevronLeftIcon size={13} color="#0D3B8E" />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.dateDisplayInline}
              onPress={() => openDatePicker('from')}
              activeOpacity={0.75}
            >
              <View style={styles.iconBox}>
                <CalendarIcon size={13} color="#0D3B8E" />
              </View>
              <Text style={styles.dateInputText} numberOfLines={1}>
                {formatDateDisplay(dateFrom || latestSaleDate || '2026-07-31') || '31 Jul 2026'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={() => adjustDate(1)} style={styles.dateAdjustBtn} activeOpacity={0.7}>
              <ChevronRightIcon size={13} color="#0D3B8E" />
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.dateControlsPill}>
            <View style={styles.rangeInlineContainer}>
              <View style={styles.iconBox}>
                <CalendarIcon size={12} color="#0D3B8E" />
              </View>
              <TouchableOpacity
                style={styles.dateFieldPair}
                onPress={() => openDatePicker('from')}
                activeOpacity={0.75}
              >
                <Text style={styles.rangeInputText} numberOfLines={1}>
                  {formatShortDateDisplay(dateFrom, dateFrom?.substring(0, 4) !== dateTo?.substring(0, 4)) || 'Start'}
                </Text>
              </TouchableOpacity>

              <Text style={styles.rangeSeparatorText}>→</Text>

              <TouchableOpacity
                style={styles.dateFieldPair}
                onPress={() => openDatePicker('to')}
                activeOpacity={0.75}
              >
                <Text style={styles.rangeInputText} numberOfLines={1}>
                  {formatShortDateDisplay(dateTo, true) || 'End'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </View>

      {/* Date Picker Modal */}
      <Modal
        visible={showDatePicker}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setShowDatePicker(false)}
        statusBarTranslucent
      >
        <View style={styles.modalOverlay}>
          <TouchableOpacity
            style={StyleSheet.absoluteFill}
            activeOpacity={1}
            onPress={() => setShowDatePicker(false)}
          />

          <View style={styles.dateModalSheet}>
            <View style={styles.dragIndicatorPill} />

            <View style={styles.dateModalHeader}>
              <View>
                <Text style={styles.dateModalTitle}>
                  {pickerTarget === 'to' ? 'Select End Date' : period === 'Daily' ? 'Select Date' : 'Select Start Date'}
                </Text>
                <Text style={styles.dateModalSubtitle}>
                  Selected: {formatDateDisplay(pickerTarget === 'to' ? dateTo : dateFrom) || 'Not set'}
                </Text>
              </View>
              <TouchableOpacity
                onPress={() => setShowDatePicker(false)}
                style={styles.closeHqModalBtn}
                activeOpacity={0.7}
              >
                <XIcon size={16} color="#0D3B8E" />
              </TouchableOpacity>
            </View>

            <View style={styles.customCalendarCard}>
              <View style={styles.monthNavHeader}>
                <TouchableOpacity
                  onPress={() => {
                    if (pickerViewMode === 'days') changeCalendarMonth(-1);
                    else if (pickerViewMode === 'months') changeCalendarYear(-1);
                    else setYearRangeStart((prev) => prev - 12);
                  }}
                  style={styles.monthNavBtn}
                  activeOpacity={0.7}
                >
                  <ChevronLeftIcon size={16} color="#0D3B8E" />
                </TouchableOpacity>

                <View style={styles.headerSelectorGroup}>
                  <TouchableOpacity
                    onPress={() => setPickerViewMode(pickerViewMode === 'months' ? 'days' : 'months')}
                    style={[
                      styles.selectorPill,
                      pickerViewMode === 'months' ? styles.selectorPillActive : null,
                    ]}
                    activeOpacity={0.75}
                  >
                    <Text style={[styles.selectorPillText, pickerViewMode === 'months' ? styles.selectorPillTextActive : null]}>
                      {monthNames[calendarViewDate.getMonth()]}
                    </Text>
                    <ChevronDownIcon size={14} color={pickerViewMode === 'months' ? '#FFFFFF' : '#0D3B8E'} />
                  </TouchableOpacity>

                  <TouchableOpacity
                    onPress={() => setPickerViewMode(pickerViewMode === 'years' ? 'days' : 'years')}
                    style={[
                      styles.selectorPill,
                      pickerViewMode === 'years' ? styles.selectorPillActive : null,
                    ]}
                    activeOpacity={0.75}
                  >
                    <Text style={[styles.selectorPillText, pickerViewMode === 'years' ? styles.selectorPillTextActive : null]}>
                      {pickerViewMode === 'years' ? `${yearRangeStart}-${yearRangeStart + 11}` : calendarViewDate.getFullYear()}
                    </Text>
                    <ChevronDownIcon size={14} color={pickerViewMode === 'years' ? '#FFFFFF' : '#0D3B8E'} />
                  </TouchableOpacity>
                </View>

                <TouchableOpacity
                  onPress={() => {
                    if (pickerViewMode === 'days') changeCalendarMonth(1);
                    else if (pickerViewMode === 'months') changeCalendarYear(1);
                    else setYearRangeStart((prev) => prev + 12);
                  }}
                  style={styles.monthNavBtn}
                  activeOpacity={0.7}
                >
                  <ChevronRightIcon size={16} color="#0D3B8E" />
                </TouchableOpacity>
              </View>

              <View style={styles.gridContainer}>
                {pickerViewMode === 'months' && (
                  <View style={styles.chipGrid}>
                    {monthNames.map((mName, mIdx) => {
                      const isSel = calendarViewDate.getMonth() === mIdx;
                      return (
                        <TouchableOpacity
                          key={mName}
                          style={[styles.chipItem, isSel ? styles.chipItemActive : null]}
                          onPress={() => {
                            setCalendarViewDate(new Date(calendarViewDate.getFullYear(), mIdx, 1));
                            setPickerViewMode('days');
                          }}
                          activeOpacity={0.75}
                        >
                          <Text style={[styles.chipItemText, isSel ? styles.chipItemTextActive : null]}>
                            {mName.substring(0, 3)}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                )}

                {pickerViewMode === 'years' && (
                  <View style={styles.chipGrid}>
                    {Array.from({ length: 12 }, (_, i) => yearRangeStart + i).map((yNum) => {
                      const isSel = calendarViewDate.getFullYear() === yNum;
                      return (
                        <TouchableOpacity
                          key={yNum}
                          style={[styles.chipItem, isSel ? styles.chipItemActive : null]}
                          onPress={() => {
                            setCalendarViewDate(new Date(yNum, calendarViewDate.getMonth(), 1));
                            setPickerViewMode('days');
                          }}
                          activeOpacity={0.75}
                        >
                          <Text style={[styles.chipItemText, isSel ? styles.chipItemTextActive : null]}>
                            {yNum}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                )}

                {pickerViewMode === 'days' && (
                  <>
                    <View style={styles.weekHeadersRow}>
                      {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map((d) => (
                        <Text key={d} style={styles.weekHeaderCell}>{d}</Text>
                      ))}
                    </View>
                    <View style={styles.daysGrid}>
                      {getCalendarDays().map((cell, idx) => {
                        const targetStr = pickerTarget === 'to' ? dateTo : dateFrom;
                        const isSelected = cell.dateStr === targetStr;
                        const todayStr = new Date().toISOString().split('T')[0];
                        const isToday = cell.dateStr === todayStr;

                        return (
                          <TouchableOpacity
                            key={idx}
                            style={[
                              styles.dayCell,
                              isSelected ? styles.dayCellSelected : null,
                              isToday && !isSelected ? styles.dayCellToday : null,
                            ]}
                            onPress={() => handleSelectDay(cell.dateStr)}
                            activeOpacity={0.7}
                          >
                            <Text
                              style={[
                                styles.dayCellText,
                                !cell.isCurrent ? styles.dayCellTextMuted : null,
                                isToday && !isSelected ? styles.dayCellTextToday : null,
                                isSelected ? styles.dayCellTextSelected : null,
                              ]}
                            >
                              {cell.day}
                            </Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  </>
                )}
              </View>
            </View>

            <TouchableOpacity
              style={styles.confirmDateBtn}
              onPress={() => setShowDatePicker(false)}
              activeOpacity={0.8}
            >
              <Text style={styles.confirmDateBtnText}>Done</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Headquarters Selection Modal */}
      <Modal
        visible={showHqModal}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setShowHqModal(false)}
        statusBarTranslucent
      >
        <View style={styles.modalOverlay}>
          <TouchableOpacity
            style={StyleSheet.absoluteFill}
            activeOpacity={1}
            onPress={() => setShowHqModal(false)}
          />

          <View style={styles.hqModalSheet}>
            <View style={styles.dragIndicatorPill} />

            <View style={styles.hqModalHeader}>
              <View>
                <Text style={styles.hqModalTitle}>Select Headquarters</Text>
                <Text style={styles.hqModalSubtitle}>Filter sales dashboard metrics</Text>
              </View>
              <TouchableOpacity
                onPress={() => setShowHqModal(false)}
                style={styles.closeHqModalBtn}
                activeOpacity={0.7}
              >
                <XIcon size={16} color="#0D3B8E" />
              </TouchableOpacity>
            </View>

            <FlatList
              data={headquartersList}
              keyExtractor={(item) => item}
              contentContainerStyle={styles.hqListContent}
              renderItem={({ item }) => {
                const isActive = selectedHq === item;
                return (
                  <TouchableOpacity
                    style={[
                      styles.hqModalItem,
                      isActive ? styles.hqModalItemActive : null,
                    ]}
                    onPress={() => {
                      setSelectedHq(item);
                      setShowHqModal(false);
                    }}
                    activeOpacity={0.75}
                  >
                    <View style={styles.hqItemLeft}>
                      <View style={[styles.hqItemDot, isActive ? styles.hqItemDotActive : null]} />
                      <Text style={[styles.hqModalItemText, isActive ? styles.hqModalItemTextActive : null]}>
                        {item}
                      </Text>
                    </View>
                    {isActive ? (
                      <CheckCircleIcon size={16} color="#0D3B8E" />
                    ) : null}
                  </TouchableOpacity>
                );
              }}
            />
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingTop: Platform.OS === 'ios' ? 12 : 12,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 2,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  branding: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  logoBox: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    color: '#0D3B8E',
    fontSize: 17.5,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
  hqSelectorPill: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    alignItems: 'center',
    gap: 4,
    maxWidth: 170,
  },
  iconBox: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  hqText: {
    color: '#0D3B8E',
    fontSize: 12,
    fontWeight: '700',
    flex: 1,
  },
  controlsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  periodSwitcher: {
    flexDirection: 'row',
    backgroundColor: '#F1F5F9',
    borderRadius: 12,
    padding: 3,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    alignItems: 'center',
  },
  periodBtn: {
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 9,
    justifyContent: 'center',
    alignItems: 'center',
  },
  periodBtnActive: {
    backgroundColor: '#0D3B8E',
    shadowColor: '#0D3B8E',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 4,
    elevation: 2,
  },
  periodBtnText: {
    fontSize: 11.5,
    color: '#64748B',
    fontWeight: '700',
  },
  periodBtnTextActive: {
    color: '#FFFFFF',
    fontWeight: '800',
  },
  dateControlsPill: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    overflow: 'hidden',
  },
  rangeInlineContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flex: 1,
  },
  dateFieldPair: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
    paddingVertical: 2,
  },
  rangeInputText: {
    color: '#0F172A',
    fontSize: 11.5,
    fontWeight: '700',
    textAlign: 'center',
  },
  rangeSeparatorText: {
    color: '#0D3B8E',
    fontSize: 11,
    fontWeight: '800',
    marginHorizontal: 2,
  },
  dateDisplayInline: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    paddingHorizontal: 4,
    gap: 4,
  },
  dateAdjustBtn: {
    paddingHorizontal: 4,
    paddingVertical: 2,
  },
  dateInputText: {
    color: '#0F172A',
    fontSize: 11.5,
    fontWeight: '700',
    textAlign: 'center',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.4)',
    justifyContent: 'flex-end',
  },
  hqModalSheet: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '65%',
    paddingBottom: 20,
  },
  dateModalSheet: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingBottom: 24,
    minHeight: 450,
  },
  dragIndicatorPill: {
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#E2E8F0',
    alignSelf: 'center',
    marginTop: 10,
  },
  hqModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  hqModalTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0F172A',
    letterSpacing: -0.2,
  },
  hqModalSubtitle: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '600',
    marginTop: 2,
  },
  closeHqModalBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#F1F5F9',
    justifyContent: 'center',
    alignItems: 'center',
  },
  dateModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  dateModalTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0F172A',
    letterSpacing: -0.2,
  },
  dateModalSubtitle: {
    fontSize: 11,
    color: '#64748B',
    fontWeight: '700',
    marginTop: 2,
  },
  customCalendarCard: {
    backgroundColor: '#FAFAFA',
    borderRadius: 20,
    marginHorizontal: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    marginVertical: 12,
    height: 325,
  },
  monthNavHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
    paddingHorizontal: 4,
  },
  headerSelectorGroup: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
  },
  selectorPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#E2E8F0',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    gap: 4,
  },
  selectorPillActive: {
    backgroundColor: '#0D3B8E',
  },
  selectorPillText: {
    fontSize: 13,
    fontWeight: '800',
    color: '#0D3B8E',
  },
  selectorPillTextActive: {
    color: '#FFFFFF',
  },
  monthNavBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#FFFFFF',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  gridContainer: {
    paddingVertical: 4,
    height: 252,
    justifyContent: 'center',
  },
  chipGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    gap: 8,
    paddingHorizontal: 2,
  },
  chipItem: {
    width: '30%',
    paddingVertical: 12,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    alignItems: 'center',
    marginBottom: 4,
  },
  chipItemActive: {
    backgroundColor: '#0D3B8E',
    borderColor: '#0D3B8E',
  },
  chipItemText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#334155',
  },
  chipItemTextActive: {
    color: '#FFFFFF',
    fontWeight: '800',
  },
  weekHeadersRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
    paddingHorizontal: 2,
  },
  weekHeaderCell: {
    width: '14.28%',
    textAlign: 'center',
    fontSize: 11,
    fontWeight: '800',
    color: '#94A3B8',
  },
  daysGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  dayCell: {
    width: '14.28%',
    height: 35,
    justifyContent: 'center',
    alignItems: 'center',
    marginVertical: 1,
    borderRadius: 17.5,
  },
  dayCellSelected: {
    backgroundColor: '#0D3B8E',
  },
  dayCellToday: {
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#0D3B8E',
  },
  dayCellText: {
    fontSize: 12.5,
    fontWeight: '700',
    color: '#1E293B',
  },
  dayCellTextMuted: {
    color: '#CBD5E1',
    fontWeight: '500',
  },
  dayCellTextSelected: {
    color: '#FFFFFF',
    fontWeight: '900',
  },
  dayCellTextToday: {
    color: '#0D3B8E',
    fontWeight: '800',
  },
  confirmDateBtn: {
    backgroundColor: '#0D3B8E',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
    marginHorizontal: 16,
    marginTop: 4,
  },
  confirmDateBtnText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '800',
  },
  hqListContent: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 16,
  },
  hqModalItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderRadius: 14,
    marginBottom: 8,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  hqModalItemActive: {
    backgroundColor: '#EFF6FF',
    borderColor: '#0D3B8E',
  },
  hqItemLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  hqItemDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#CBD5E1',
    marginRight: 12,
  },
  hqItemDotActive: {
    backgroundColor: '#0D3B8E',
  },
  hqModalItemText: {
    fontSize: 13.5,
    color: '#475569',
    fontWeight: '600',
  },
  hqModalItemTextActive: {
    color: '#0D3B8E',
    fontWeight: '800',
  },
});
