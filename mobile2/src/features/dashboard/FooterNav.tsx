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
              color={isActive ? '#0D3B8E' : '#94A3B8'}
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
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: '#F1F5F9',
    paddingTop: 8,
    paddingBottom: Platform.OS === 'ios' ? 24 : 10,
    paddingHorizontal: 12,
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 3,
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
    backgroundColor: '#EFF6FF',
  },
  navText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#64748B',
    marginTop: 3,
  },
  navTextActive: {
    color: '#0D3B8E',
    fontWeight: '800',
  },
});
