import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { ViewMode } from '../../types';
import {
  BuildingIcon,
  StoreIcon,
  UsersIcon,
  UserIcon,
} from '../../components/Icons';

interface FooterNavProps {
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
}

export function FooterNav({ viewMode, setViewMode }: FooterNavProps) {
  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={[
          styles.navBtn,
          viewMode === 'companies' ? styles.navBtnActive : null,
        ]}
        onPress={() => setViewMode('companies')}
      >
        <BuildingIcon
          color={viewMode === 'companies' ? '#0F2042' : '#94A3B8'}
          size={16}
        />
        <Text
          style={[
            styles.navText,
            viewMode === 'companies' ? styles.navTextActive : null,
          ]}
        >
          Companies
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[
          styles.navBtn,
          viewMode === 'depots' ? styles.navBtnActive : null,
        ]}
        onPress={() => setViewMode('depots')}
      >
        <StoreIcon
          color={viewMode === 'depots' ? '#0F2042' : '#94A3B8'}
          size={16}
        />
        <Text
          style={[
            styles.navText,
            viewMode === 'depots' ? styles.navTextActive : null,
          ]}
        >
          Depots
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[
          styles.navBtn,
          viewMode === 'tsm' ? styles.navBtnActive : null,
        ]}
        onPress={() => setViewMode('tsm')}
      >
        <UsersIcon
          color={viewMode === 'tsm' ? '#0F2042' : '#94A3B8'}
          size={16}
        />
        <Text
          style={[
            styles.navText,
            viewMode === 'tsm' ? styles.navTextActive : null,
          ]}
        >
          TSM
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[
          styles.navBtn,
          viewMode === 'profile' ? styles.navBtnActive : null,
        ]}
        onPress={() => setViewMode('profile')}
      >
        <UserIcon
          color={viewMode === 'profile' ? '#0F2042' : '#94A3B8'}
          size={16}
        />
        <Text
          style={[
            styles.navText,
            viewMode === 'profile' ? styles.navTextActive : null,
          ]}
        >
          Profile
        </Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#0A1428',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.1)',
    paddingVertical: 10,
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
  },
  navBtn: {
    alignItems: 'center',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 12,
    minWidth: 70,
  },
  navBtnActive: {
    backgroundColor: '#FFFFFF',
  },
  navText: {
    fontSize: 9,
    fontWeight: '600',
    color: '#94A3B8',
    marginTop: 4,
  },
  navTextActive: {
    color: '#0F2042',
    fontWeight: '800',
  },
});
