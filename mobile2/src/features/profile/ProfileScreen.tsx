import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { LogOutIcon, UserIcon, LocationIcon } from '../../components/Icons';
import { ProfileSkeleton } from '../../components/SkeletonLoaders';

interface ProfileScreenProps {
  user: any;
  onLogout: () => void;
  loading?: boolean;
}

export function ProfileScreen({ user, onLogout, loading = false }: ProfileScreenProps) {
  if (loading || !user) {
    return <ProfileSkeleton />;
  }

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
          <View style={styles.detailIconCircle}>
            <UserIcon size={16} color="#94A3B8" />
          </View>
          <View style={styles.detailTextWrapper}>
            <Text style={styles.detailLabel}>Phone Number</Text>
            <Text style={styles.detailValue}>{phone}</Text>
          </View>
        </View>

        {/* Email Address */}
        <View style={styles.detailItem}>
          <View style={styles.detailIconCircle}>
            <UserIcon size={16} color="#94A3B8" />
          </View>
          <View style={styles.detailTextWrapper}>
            <Text style={styles.detailLabel}>Email Address</Text>
            <Text style={styles.detailValue}>{email}</Text>
          </View>
        </View>

        {/* Designation */}
        <View style={styles.detailItem}>
          <View style={styles.detailIconCircle}>
            <UserIcon size={16} color="#94A3B8" />
          </View>
          <View style={styles.detailTextWrapper}>
            <Text style={styles.detailLabel}>Designation</Text>
            <Text style={styles.detailValue}>{designation}</Text>
          </View>
        </View>

        {/* Depot Assigned */}
        <View style={styles.detailItem}>
          <View style={styles.detailIconCircle}>
            <LocationIcon size={16} color="#94A3B8" />
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
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 10,
    elevation: 4,
  },
  avatar: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#1E293B',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.2)',
  },
  avatarText: {
    color: '#FFFFFF',
    fontSize: 22,
    fontWeight: '900',
  },
  headerInfo: {
    flex: 1,
  },
  fullNameText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '800',
  },
  roleSubtext: {
    color: '#94A3B8',
    fontSize: 12,
    fontWeight: '600',
    marginTop: 4,
  },
  detailsCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 20,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 2,
  },
  detailsCardTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
    marginBottom: 16,
  },
  detailItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  detailIconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#F1F5F9',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 14,
  },
  detailTextWrapper: {
    flex: 1,
  },
  detailLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#94A3B8',
  },
  detailValue: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0F172A',
    marginTop: 2,
  },
  signOutButton: {
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 16,
    paddingVertical: 14,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
    marginBottom: 24,
  },
  signOutButtonText: {
    color: '#EF4444',
    fontSize: 14,
    fontWeight: '800',
  },
  footer: {
    alignItems: 'center',
  },
  footerText: {
    fontSize: 11,
    color: '#94A3B8',
    fontWeight: '500',
  },
});
