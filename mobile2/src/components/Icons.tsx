import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export const SearchIcon = ({ color = '#94A3B8', size = 16 }) => (
  <View style={[styles.searchContainer, { width: size, height: size }]}>
    <View style={[styles.searchCircle, { borderColor: color }]} />
    <View style={[styles.searchHandle, { backgroundColor: color }]} />
  </View>
);

export const BuildingIcon = ({ color = '#94A3B8', size = 16 }) => (
  <View style={[styles.buildingContainer, { width: size, height: size }]}>
    <View style={[styles.buildingRoof, { borderBottomColor: color }]} />
    <View style={[styles.buildingBody, { borderColor: color }]} />
    <View style={[styles.buildingDoor, { backgroundColor: color }]} />
  </View>
);

export const StoreIcon = ({ color = '#94A3B8', size = 16 }) => (
  <View style={[styles.storeContainer, { width: size, height: size }]}>
    <View style={[styles.storeRoof, { borderBottomColor: color }]} />
    <View style={[styles.storeBody, { borderColor: color }]} />
  </View>
);

export const UsersIcon = ({ color = '#94A3B8', size = 16 }) => (
  <View style={[styles.usersContainer, { width: size, height: size }]}>
    <View style={[styles.userHead, { backgroundColor: color, left: 2, top: 1 }]} />
    <View style={[styles.userBody, { borderColor: color, left: 0, top: 7, borderTopLeftRadius: 3, borderTopRightRadius: 3 }]} />
    <View style={[styles.userHead, { backgroundColor: color, left: 8, top: 2 }]} />
    <View style={[styles.userBody, { borderColor: color, left: 6, top: 8, borderTopLeftRadius: 3, borderTopRightRadius: 3 }]} />
  </View>
);

export const UserIcon = ({ color = '#94A3B8', size = 16 }) => (
  <View style={[styles.userContainer, { width: size, height: size }]}>
    <View style={[styles.userHeadSolo, { backgroundColor: color }]} />
    <View style={[styles.userBodySolo, { borderColor: color }]} />
  </View>
);

export const LogOutIcon = ({ color = '#FFFFFF', size = 16 }) => (
  <Text style={{ color, fontSize: size, fontWeight: 'bold' }}>⎋</Text>
);

export const ShieldAlertIcon = ({ color = '#EF4444', size = 24 }) => (
  <View style={[styles.shieldContainer, { width: size, height: size }]}>
    <Text style={{ color, fontSize: size - 4, fontWeight: 'bold' }}>⚠️</Text>
  </View>
);

export const XIcon = ({ color = '#94A3B8', size = 16 }) => (
  <Text style={{ color, fontSize: size, fontWeight: '900', lineHeight: size }}>✕</Text>
);

export const ArrowRightIcon = ({ color = '#000000', size = 16 }) => (
  <Text style={{ color, fontSize: size, fontWeight: 'bold' }}>➔</Text>
);

export const KeyIcon = ({ color = '#F59E0B', size = 20 }) => (
  <Text style={{ color, fontSize: size, fontWeight: 'bold' }}>🔑</Text>
);

export const RefreshIcon = ({ color = '#94A3B8', size = 14 }) => (
  <Text style={{ color, fontSize: size, fontWeight: 'bold' }}>↻</Text>
);

export const EditIcon = ({ color = '#94A3B8', size = 14 }) => (
  <Text style={{ color, fontSize: size, fontWeight: 'bold' }}>✏️</Text>
);

export const PinIcon = ({ color = '#F59E0B', size = 14 }) => (
  <Text style={{ color, fontSize: size }}>📌</Text>
);

export const CheckCircleIcon = ({ color = '#10B981', size = 14 }) => (
  <Text style={{ color, fontSize: size }}>✓</Text>
);

const styles = StyleSheet.create({
  searchContainer: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchCircle: {
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 1.8,
    position: 'absolute',
    top: 1,
    left: 1,
  },
  searchHandle: {
    width: 2,
    height: 6,
    transform: [{ rotate: '-45deg' }],
    position: 'absolute',
    bottom: 0,
    right: 2,
  },
  buildingContainer: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  buildingRoof: {
    width: 0,
    height: 0,
    borderLeftWidth: 6,
    borderRightWidth: 6,
    borderBottomWidth: 4,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    position: 'absolute',
    top: 1,
  },
  buildingBody: {
    width: 10,
    height: 9,
    borderWidth: 1.5,
    position: 'absolute',
    bottom: 1,
  },
  buildingDoor: {
    width: 3,
    height: 4,
    position: 'absolute',
    bottom: 1.5,
  },
  storeContainer: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  storeRoof: {
    width: 0,
    height: 0,
    borderLeftWidth: 7,
    borderRightWidth: 7,
    borderBottomWidth: 4,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
    position: 'absolute',
    top: 1,
  },
  storeBody: {
    width: 12,
    height: 8,
    borderWidth: 1.5,
    position: 'absolute',
    bottom: 2,
  },
  usersContainer: {
    position: 'relative',
  },
  userHead: {
    width: 4,
    height: 4,
    borderRadius: 2,
    position: 'absolute',
  },
  userBody: {
    width: 8,
    height: 7,
    borderWidth: 1.2,
    borderBottomWidth: 0,
    position: 'absolute',
  },
  userContainer: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  userHeadSolo: {
    width: 6,
    height: 6,
    borderRadius: 3,
    position: 'absolute',
    top: 1,
  },
  userBodySolo: {
    width: 12,
    height: 7,
    borderWidth: 1.5,
    borderBottomWidth: 0,
    borderTopLeftRadius: 4,
    borderTopRightRadius: 4,
    position: 'absolute',
    bottom: 1,
  },
  shieldContainer: {
    justifyContent: 'center',
    alignItems: 'center',
  },
});
