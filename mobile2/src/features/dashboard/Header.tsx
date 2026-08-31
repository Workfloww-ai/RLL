import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  FlatList,
  Platform,
  Image,
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
    const targetDate = latestSaleDate || '2026-07-31';

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

  // Always returns exactly 42 cells (6 rows * 7 days) to ensure fixed grid height across all months
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

    // Next month padding to complete exactly 42 grid cells (6 rows)
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
          <View style={styles.logoCircle}>
            <Image
              source={require('../../assets/rll.png')}
              style={styles.logoImage}
              resizeMode="contain"
            />
          </View>
          <View style={styles.brandingText}>
            <Text style={styles.title}>Sales Dashboard</Text>
            {/* <Text style={styles.subtitle}>Rajasthan</Text> */}
          </View>
        </View>

        {/* Modern Headquarters Selector Dropdown Pill */}
        <TouchableOpacity
          style={styles.hqSelectorPill}
          onPress={() => setShowHqModal(true)}
          activeOpacity={0.75}
        >
          <View style={styles.iconBox}>
            <LocationIcon size={13} color="#FFFFFF" />
          </View>
          <Text
            style={styles.hqText}
            numberOfLines={1}
            adjustsFontSizeToFit={true}
            minimumFontScale={0.75}
          >
            {selectedHq}
          </Text>
          <View style={{ marginLeft: 2 }}>
            <ChevronDownIcon size={14} color="#FFFFFF" />
          </View>
        </TouchableOpacity>
      </View>

      {/* Row 2: Period Switcher (Daily | MTD | YTD) + Date Controls */}
      <View style={styles.controlsRow}>
        {/* Premium Executive Period Switcher */}
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

        {/* Modern Date Controls Range Pill */}
        {period === 'Daily' ? (
          <View style={styles.dateControlsPill}>
            <TouchableOpacity onPress={() => adjustDate(-1)} style={styles.dateAdjustBtn} activeOpacity={0.7}>
              <ChevronLeftIcon size={13} color="#FFFFFF" />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.dateDisplayInline}
              onPress={() => openDatePicker('from')}
              activeOpacity={0.75}
            >
              <View style={styles.iconBox}>
                <CalendarIcon size={13} color="#FFFFFF" />
              </View>
              <Text style={styles.dateInputText} numberOfLines={1}>
                {formatDateDisplay(dateFrom || latestSaleDate || '') || 'Select Date'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={() => adjustDate(1)} style={styles.dateAdjustBtn} activeOpacity={0.7}>
              <ChevronRightIcon size={13} color="#FFFFFF" />
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.dateControlsPill}>
            <View style={styles.rangeInlineContainer}>
              <View style={styles.iconBox}>
                <CalendarIcon size={12} color="#FFFFFF" />
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

      {/* Custom Modern Executive Calendar Bottom Sheet Modal */}
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
                <XIcon size={16} color="#0F2042" />
              </TouchableOpacity>
            </View>

            {/* Custom Modern Interactive Calendar Card with Fixed Dimensions */}
            <View style={styles.customCalendarCard}>
              {/* Month / Year Header Controls */}
              <View style={styles.monthNavHeader}>
                {/* Left Arrow Button */}
                <TouchableOpacity
                  onPress={() => {
                    if (pickerViewMode === 'days') changeCalendarMonth(-1);
                    else if (pickerViewMode === 'months') changeCalendarYear(-1);
                    else setYearRangeStart((prev) => prev - 12);
                  }}
                  style={styles.monthNavBtn}
                  activeOpacity={0.7}
                >
                  <ChevronLeftIcon size={16} color="#0F2042" />
                </TouchableOpacity>

                {/* Header Interactive Selector Group */}
                <View style={styles.headerSelectorGroup}>
                  {/* Month Pill */}
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
                    <View style={{ marginLeft: 4 }}>
                      <ChevronDownIcon size={14} color={pickerViewMode === 'months' ? '#FFFFFF' : '#0F2042'} />
                    </View>
                  </TouchableOpacity>

                  {/* Year Pill */}
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
                    <View style={{ marginLeft: 4 }}>
                      <ChevronDownIcon size={14} color={pickerViewMode === 'years' ? '#FFFFFF' : '#0F2042'} />
                    </View>
                  </TouchableOpacity>
                </View>

                {/* Right Arrow Button */}
                <TouchableOpacity
                  onPress={() => {
                    if (pickerViewMode === 'days') changeCalendarMonth(1);
                    else if (pickerViewMode === 'months') changeCalendarYear(1);
                    else setYearRangeStart((prev) => prev + 12);
                  }}
                  style={styles.monthNavBtn}
                  activeOpacity={0.7}
                >
                  <ChevronRightIcon size={16} color="#0F2042" />
                </TouchableOpacity>
              </View>

              {/* VIEW MODE 1: Years Selection Grid */}
              {pickerViewMode === 'years' && (
                <View style={styles.gridContainer}>
                  <View style={styles.chipGrid}>
                    {Array.from({ length: 12 }, (_, i) => yearRangeStart + i).map((yVal) => {
                      const isCurrentYear = calendarViewDate.getFullYear() === yVal;
                      return (
                        <TouchableOpacity
                          key={yVal}
                          style={[
                            styles.chipItem,
                            isCurrentYear ? styles.chipItemActive : null,
                          ]}
                          onPress={() => {
                            setCalendarViewDate((prev) => new Date(yVal, prev.getMonth(), 1));
                            setPickerViewMode('months');
                          }}
                          activeOpacity={0.75}
                        >
                          <Text
                            style={[
                              styles.chipItemText,
                              isCurrentYear ? styles.chipItemTextActive : null,
                            ]}
                          >
                            {yVal}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              )}

              {/* VIEW MODE 2: Months Selection Grid */}
              {pickerViewMode === 'months' && (
                <View style={styles.gridContainer}>
                  <View style={styles.chipGrid}>
                    {monthNames.map((mName, mIdx) => {
                      const isCurrentMonth = calendarViewDate.getMonth() === mIdx;
                      return (
                        <TouchableOpacity
                          key={mIdx}
                          style={[
                            styles.chipItem,
                            isCurrentMonth ? styles.chipItemActive : null,
                          ]}
                          onPress={() => {
                            setCalendarViewDate((prev) => new Date(prev.getFullYear(), mIdx, 1));
                            setPickerViewMode('days');
                          }}
                          activeOpacity={0.75}
                        >
                          <Text
                            style={[
                              styles.chipItemText,
                              isCurrentMonth ? styles.chipItemTextActive : null,
                            ]}
                          >
                            {mName.substring(0, 3)}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              )}

              {/* VIEW MODE 3: Days Calendar Grid */}
              {pickerViewMode === 'days' && (
                <View style={styles.gridContainer}>
                  {/* Day of Week Headers */}
                  <View style={styles.weekHeadersRow}>
                    {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((dayName, index) => (
                      <Text key={index} style={styles.weekHeaderCell}>
                        {dayName}
                      </Text>
                    ))}
                  </View>

                  {/* Calendar Days 7-column Grid (Fixed 6 rows) */}
                  <View style={styles.daysGrid}>
                    {getCalendarDays().map((item, idx) => {
                      const activeTargetStr = pickerTarget === 'to' ? dateTo : dateFrom;
                      const isSelected = item.dateStr === activeTargetStr;
                      const isToday = item.dateStr === new Date().toISOString().split('T')[0];

                      return (
                        <TouchableOpacity
                          key={idx}
                          style={[
                            styles.dayCell,
                            isSelected ? styles.dayCellSelected : null,
                            !isSelected && isToday ? styles.dayCellToday : null,
                          ]}
                          onPress={() => handleSelectDay(item.dateStr)}
                          activeOpacity={0.7}
                        >
                          <Text
                            style={[
                              styles.dayCellText,
                              !item.isCurrent ? styles.dayCellTextMuted : null,
                              isSelected ? styles.dayCellTextSelected : null,
                              !isSelected && isToday ? styles.dayCellTextToday : null,
                            ]}
                          >
                            {item.day}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
              )}
            </View>

            {/* Apply & Close Action Button */}
            <TouchableOpacity
              style={styles.confirmDateBtn}
              onPress={() => setShowDatePicker(false)}
              activeOpacity={0.8}
            >
              <Text style={styles.confirmDateBtnText}>Apply & Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Headquarters Selector Dropdown Sheet Modal */}
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
                <Text style={styles.hqModalSubtitle}>Filter sales data by location</Text>
              </View>
              <TouchableOpacity
                onPress={() => setShowHqModal(false)}
                style={styles.closeHqModalBtn}
                activeOpacity={0.7}
              >
                <XIcon size={16} color="#0F2042" />
              </TouchableOpacity>
            </View>

            <FlatList
              data={headquartersList}
              keyExtractor={(item) => item}
              contentContainerStyle={styles.hqListContent}
              showsVerticalScrollIndicator={true}
              renderItem={({ item }) => {
                const isSelected = selectedHq === item;
                return (
                  <TouchableOpacity
                    style={[
                      styles.hqModalItem,
                      isSelected ? styles.hqModalItemActive : null,
                    ]}
                    onPress={() => {
                      setSelectedHq(item);
                      setShowHqModal(false);
                    }}
                    activeOpacity={0.7}
                  >
                    <View style={styles.hqItemLeft}>
                      <View style={[styles.hqItemDot, isSelected ? styles.hqItemDotActive : null]} />
                      <Text
                        style={[
                          styles.hqModalItemText,
                          isSelected ? styles.hqModalItemTextActive : null,
                        ]}
                      >
                        {item}
                      </Text>
                    </View>
                    {isSelected && (
                      <CheckCircleIcon size={18} color="#3B82F6" />
                    )}
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
    width: 38,
    height: 38,
    backgroundColor: '#FFFFFF',
    borderRadius: 19,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  logoImage: {
    width: 32,
    height: 32,
  },
  brandingText: {
    marginLeft: 10,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 16.5,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
  subtitle: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '600',
    marginTop: 1,
  },
  hqSelectorPill: {
    flexDirection: 'row',
    backgroundColor: '#131F37',
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    alignItems: 'center',
    maxWidth: 155,
  },
  iconBox: {
    marginRight: 4,
    justifyContent: 'center',
    alignItems: 'center',
  },
  hqText: {
    color: '#FFFFFF',
    fontSize: 11.5,
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
    backgroundColor: '#131F37',
    borderRadius: 12,
    padding: 3,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    alignItems: 'center',
  },
  periodBtn: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 9,
    justifyContent: 'center',
    alignItems: 'center',
  },
  periodBtnActive: {
    backgroundColor: '#FFFFFF',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 4,
    elevation: 3,
  },
  periodBtnText: {
    fontSize: 11.5,
    color: '#94A3B8',
    fontWeight: '700',
  },
  periodBtnTextActive: {
    color: '#0F2042',
    fontWeight: '900',
  },
  dateControlsPill: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#131F37',
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
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
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '700',
    textAlign: 'center',
  },
  rangeSeparatorText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '800',
    marginHorizontal: 2,
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
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: 6,
  },
  dateInputText: {
    color: '#FFFFFF',
    fontSize: 11.5,
    fontWeight: '700',
    textAlign: 'center',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.65)',
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
    color: '#0F2042',
    letterSpacing: -0.2,
  },
  hqModalSubtitle: {
    fontSize: 11,
    color: '#94A3B8',
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
    color: '#0F2042',
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
  },
  selectorPillActive: {
    backgroundColor: '#0F2042',
  },
  selectorPillText: {
    fontSize: 13,
    fontWeight: '800',
    color: '#0F2042',
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
    backgroundColor: '#0F2042',
    borderColor: '#0F2042',
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
    backgroundColor: '#0F2042',
  },
  dayCellToday: {
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#3B82F6',
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
    color: '#3B82F6',
    fontWeight: '800',
  },
  confirmDateBtn: {
    backgroundColor: '#0F2042',
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
    borderColor: '#3B82F6',
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
    backgroundColor: '#3B82F6',
  },
  hqModalItemText: {
    fontSize: 13.5,
    color: '#475569',
    fontWeight: '600',
  },
  hqModalItemTextActive: {
    color: '#0F2042',
    fontWeight: '800',
  },
});
