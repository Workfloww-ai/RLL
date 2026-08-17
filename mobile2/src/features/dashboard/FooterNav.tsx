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
        activeOpacity={0.8}
      >
        <BuildingIcon
          color={viewMode === 'companies' ? '#0F172A' : '#94A3B8'}
          size={18}
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
        activeOpacity={0.8}
      >
        <StoreIcon
          color={viewMode === 'depots' ? '#0F172A' : '#94A3B8'}
          size={18}
        />
        <Text
          style={[
            styles.navText,
            viewMode === 'depots' ? styles.navTextActive : null,
          ]}
        >
          Groups
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[
          styles.navBtn,
          viewMode === 'tsm' ? styles.navBtnActive : null,
        ]}
        onPress={() => setViewMode('tsm')}
        activeOpacity={0.8}
      >
        <UsersIcon
          color={viewMode === 'tsm' ? '#0F172A' : '#94A3B8'}
          size={18}
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
        activeOpacity={0.8}
      >
        <UserIcon
          color={viewMode === 'profile' ? '#0F172A' : '#94A3B8'}
          size={18}
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
    backgroundColor: '#0A1128',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.08)',
    paddingVertical: 10,
    paddingHorizontal: 12,
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
  },
  navBtn: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    paddingHorizontal: 16,
    borderRadius: 20,
    minWidth: 80,
  },
  navBtnActive: {
    backgroundColor: '#FFFFFF',
    borderWidth: 2,
    borderColor: '#38BDF8',
  },
  navText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#94A3B8',
    marginTop: 3,
  },
  navTextActive: {
    color: '#0F172A',
    fontWeight: '900',
  },
});

