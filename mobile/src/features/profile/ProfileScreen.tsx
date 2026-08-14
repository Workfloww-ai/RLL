import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { LogOutIcon } from '../../components/Icons';

interface ProfileScreenProps {
  user: any;
  onLogout: () => void;
}

export function ProfileScreen({ user, onLogout }: ProfileScreenProps) {
  const firstName = user?.first_name || user?.name?.split(' ')[0] || 'Executive';
  const lastName = user?.last_name || user?.name?.split(' ').slice(1).join(' ') || '';
  const fullName = `${firstName} ${lastName}`.trim() || user?.name || 'Account Holder';
  const email = user?.email || 'N/A';
  const phone = user?.phone || 'N/A';
  const designation = user?.role_name || user?.role || 'Territory Sales Manager (TSM)';
  const depotName = user?.depot_name || user?.depotName || user?.depot || user?.hq_location || 'Jaipur Central Depot';

  const initials = `${firstName.charAt(0)}${lastName ? lastName.charAt(0) : ''}`.toUpperCase() || 'U';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
      {/* Top Profile Header Card */}
      <View style={styles.profileHeaderCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials}</Text>
        </View>
        <View style={styles.headerInfo}>
          <Text style={styles.fullNameText}>{fullName}</Text>
          <Text style={styles.roleSubtext}>{designation}</Text>
        </View>
      </View>

      {/* Account Info Details Card */}
      <View style={styles.detailsCard}>
        <Text style={styles.detailsCardTitle}>Account Details</Text>

        {/* Phone Number */}
        <View style={styles.detailItem}>
          <View style={[styles.detailIconCircle, { backgroundColor: '#ECFDF5' }]}>
            <Text style={{ fontSize: 16 }}>📞</Text>
          </View>
          <View style={styles.detailTextWrapper}>
            <Text style={styles.detailLabel}>Phone Number</Text>
            <Text style={styles.detailValue}>{phone}</Text>
          </View>
        </View>

        {/* Email Address */}
        <View style={styles.detailItem}>
          <View style={[styles.detailIconCircle, { backgroundColor: '#F5F3FF' }]}>
            <Text style={{ fontSize: 16 }}>✉️</Text>
          </View>
          <View style={styles.detailTextWrapper}>
            <Text style={styles.detailLabel}>Email Address</Text>
            <Text style={styles.detailValue}>{email}</Text>
          </View>
        </View>

        {/* Designation */}
        <View style={styles.detailItem}>
          <View style={[styles.detailIconCircle, { backgroundColor: '#FEF3C7' }]}>
            <Text style={{ fontSize: 16 }}>🛡️</Text>
          </View>
          <View style={styles.detailTextWrapper}>
            <Text style={styles.detailLabel}>Designation</Text>
            <Text style={styles.detailValue}>{designation}</Text>
          </View>
        </View>

        {/* Depot Assigned */}
        <View style={styles.detailItem}>
          <View style={[styles.detailIconCircle, { backgroundColor: '#EEF2F6' }]}>
            <Text style={{ fontSize: 16 }}>🏢</Text>
          </View>
          <View style={styles.detailTextWrapper}>
            <Text style={styles.detailLabel}>Belongs to Depot</Text>
            <Text style={styles.detailValue}>{depotName}</Text>
          </View>
        </View>
      </View>

      {/* Sign Out Action Button */}
      <TouchableOpacity
        style={styles.signOutButton}
        onPress={onLogout}
      >
        <LogOutIcon color="#EF4444" size={16} />
        <Text style={styles.signOutButtonText}>Sign Out of Account</Text>
      </TouchableOpacity>

      <View style={styles.footer}>
        <Text style={styles.footerText}>Rajasthan Liquor Limited • Mobile Portal v1.0</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  profileHeaderCard: {
    backgroundColor: '#0F2042',
    borderRadius: 20,
    padding: 20,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
    shadowColor: '#0F2042',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 10,
    elevation: 4,
  },
  avatar: {
    width: 60,
    height: 60,
    borderRadius: 16,
    backgroundColor: '#F59E0B',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: '#FCD34D',
  },
  avatarText: {
    fontSize: 22,
    fontWeight: '900',
    color: '#0F2042',
  },
  headerInfo: {
    marginLeft: 16,
    flex: 1,
  },
  fullNameText: {
    fontSize: 18,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: -0.5,
  },
  roleSubtext: {
    fontSize: 12,
    color: '#94A3B8',
    marginTop: 2,
  },
  detailsCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    marginBottom: 20,
  },
  detailsCardTitle: {
    fontSize: 11,
    fontWeight: '900',
    color: '#94A3B8',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 16,
    paddingLeft: 4,
  },
  detailItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#F1F5F9',
    padding: 12,
    marginBottom: 12,
  },
  detailIconCircle: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  detailTextWrapper: {
    marginLeft: 12,
    flex: 1,
  },
  detailLabel: {
    fontSize: 10,
    color: '#64748B',
    fontWeight: '600',
  },
  detailValue: {
    fontSize: 13,
    fontWeight: 'bold',
    color: '#334155',
    marginTop: 2,
  },
  signOutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FEF2F2',
    borderColor: '#FEE2E2',
    borderWidth: 1,
    borderRadius: 16,
    paddingVertical: 14,
  },
  signOutButtonText: {
    color: '#EF4444',
    fontSize: 13,
    fontWeight: 'bold',
    marginLeft: 8,
  },
  footer: {
    alignItems: 'center',
    marginTop: 20,
  },
  footerText: {
    fontSize: 10,
    color: '#94A3B8',
  },
});
