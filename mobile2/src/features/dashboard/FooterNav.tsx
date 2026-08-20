import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Platform } from 'react-native';
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
  const tabs: { key: ViewMode; label: string; Icon: React.ComponentType<{ color: string; size: number }> }[] = [
    { key: 'companies', label: 'Companies', Icon: BuildingIcon },
    { key: 'depots', label: 'Groups', Icon: StoreIcon },
    { key: 'tsm', label: 'TSM', Icon: UsersIcon },
    { key: 'profile', label: 'Profile', Icon: UserIcon },
  ];

  return (
    <View style={styles.container}>
      {tabs.map(({ key, label, Icon }) => {
        const isActive = viewMode === key;
        return (
          <TouchableOpacity
            key={key}
            style={[
              styles.navBtn,
              isActive ? styles.navBtnActive : null,
            ]}
            onPress={() => setViewMode(key)}
            activeOpacity={0.75}
          >
            <Icon
              color={isActive ? '#0F2042' : '#94A3B8'}
              size={19}
            />
            <Text
              style={[
                styles.navText,
                isActive ? styles.navTextActive : null,
              ]}
            >
              {label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#0A1128',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.1)',
    paddingTop: 8,
    paddingBottom: Platform.OS === 'ios' ? 24 : 10,
    paddingHorizontal: 12,
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    elevation: 8,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.18,
    shadowRadius: 8,
  },
  navBtn: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    paddingHorizontal: 16,
    borderRadius: 16,
    minWidth: 72,
  },
  navBtnActive: {
    backgroundColor: '#FFFFFF',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 4,
    elevation: 3,
  },
  navText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#94A3B8',
    marginTop: 3,
  },
  navTextActive: {
    color: '#0F2042',
    fontWeight: '800',
  },
});
