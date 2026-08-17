import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { TSM, Period } from '../../types';
import { formatNumber } from '../../lib/utils';
import { XIcon } from '../../components/Icons';

interface TsmViewProps {
  tsms: TSM[];
  period: Period;
  scaleFactor: number;
  selectedHq: string;
}

export function TsmView({
  tsms,
  period,
  scaleFactor,
  selectedHq,
}: TsmViewProps) {
  const [searchTerm, setSearchTerm] = useState('');

  // Filter TSMs by HQ selection and Search Term
  const filteredTsms = tsms.filter((t) => {
    const matchHq =
      selectedHq === 'All Headquarters' ||
      (t.hqLocation && t.hqLocation.toLowerCase() === selectedHq.toLowerCase());
    const matchSearch =
      t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (t.hqLocation && t.hqLocation.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchHq && matchSearch;
  });

  return (
    <View style={styles.container}>
      {/* Search Input */}
      <View style={styles.searchWrapper}>
        <Text style={styles.searchIcon}>🔍</Text>
        <TextInput
          style={styles.searchInput}
          placeholder="Search TSM name..."
          placeholderTextColor="#94A3B8"
          value={searchTerm}
          onChangeText={setSearchTerm}
        />
        {searchTerm ? (
          <TouchableOpacity onPress={() => setSearchTerm('')} style={styles.clearBtn}>
            <XIcon size={12} color="#94A3B8" />
          </TouchableOpacity>
        ) : null}
      </View>

      {/* TSM Cards List */}
      {filteredTsms.length === 0 ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyText}>No TSM found</Text>
        </View>
      ) : (
        <ScrollView style={styles.scrollList} contentContainerStyle={styles.listContent}>
          {filteredTsms.map((tsm) => {
            const raw = tsm.data[period];
            const cases = Math.round(raw.cases * scaleFactor);
            const bottles = Math.round(raw.bottles * scaleFactor);

            return (
              <View key={tsm.id} style={styles.tsmCard}>
                {/* Header */}
                <View style={styles.tsmHeader}>
                  <View style={styles.avatarCircle}>
                    <Text style={styles.avatarText}>👤</Text>
                  </View>
                  <View style={styles.tsmInfo}>
                    <Text style={styles.tsmName}>{tsm.name}</Text>
                    <Text style={styles.tsmRole}>Territory Sales Manager</Text>
                  </View>
                </View>

                {/* Total Metrics (Cases & Bottles) */}
                <View style={styles.metricsGrid}>
                  <View style={styles.metricCell}>
                    <Text style={styles.metricLabel}>TOTAL CASES</Text>
                    <Text style={styles.metricValuePrimary}>{formatNumber(cases)}</Text>
                  </View>

                  <View style={styles.metricCell}>
                    <Text style={styles.metricLabel}>TOTAL BOTTLES</Text>
                    <Text style={styles.metricValueSecondary}>{formatNumber(bottles)}</Text>
                  </View>
                </View>
              </View>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  searchWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    paddingHorizontal: 12,
    marginBottom: 12,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  searchIcon: {
    fontSize: 14,
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    fontSize: 12,
    color: '#334155',
    paddingVertical: 10,
  },
  clearBtn: {
    padding: 6,
  },
  emptyCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 24,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#64748B',
  },
  scrollList: {
    flex: 1,
  },
  listContent: {
    paddingBottom: 20,
  },
  tsmCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 14,
    marginBottom: 10,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 1,
  },
  tsmHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  avatarCircle: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: '#EEF2F6',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 14,
  },
  tsmInfo: {
    marginLeft: 10,
    flex: 1,
  },
  tsmName: {
    fontSize: 13,
    fontWeight: '800',
    color: '#1E293B',
  },
  tsmRole: {
    fontSize: 9,
    fontWeight: '600',
    color: '#94A3B8',
    marginTop: 1,
  },
  metricsGrid: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: '#F1F5F9',
  },
  metricCell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricLabel: {
    fontSize: 8,
    fontWeight: '700',
    color: '#94A3B8',
  },
  metricValuePrimary: {
    fontSize: 11,
    fontWeight: '900',
    color: '#0F2042',
    marginTop: 2,
  },
  metricValueSecondary: {
    fontSize: 11,
    fontWeight: '700',
    color: '#334155',
    marginTop: 2,
  },
});
