import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import {
  LogOutIcon,
  PhoneIcon,
  EmailIcon,
  BadgeIcon,
  LocationIcon,
  ShieldCheckIcon,
} from '../../components/Icons';
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

  const roleLower = String(designation).toLowerCase();
  const isLeaderRole =
    roleLower.includes('leader') ||
    roleLower.includes('admin') ||
    roleLower.includes('director') ||
    roleLower.includes('management') ||
    user?.is_leader === true;

  const isActive = user?.is_active !== undefined ? Boolean(user.is_active) : true;
  const initials = `${firstName.charAt(0)}${lastName ? lastName.charAt(0) : ''}`.toUpperCase() || 'U';

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Top Profile Hero Card */}
        <View style={styles.profileHeroCard}>
          <View style={styles.heroTopRow}>
            <View style={styles.avatarWrapper}>
              <View style={styles.avatar}>
                <Text style={styles.avatarText}>{initials}</Text>
              </View>
            </View>

            <View style={styles.heroInfo}>
              <Text style={styles.fullNameText} numberOfLines={1}>{fullName}</Text>
            </View>
          </View>
        </View>

        {/* Overview Metric Highlights */}
        <View style={styles.statsRow}>
          <View style={styles.statCard}>
            <Text style={styles.statLabel}>ACCESS LEVEL</Text>
            <Text style={styles.statValue}>
              {isLeaderRole ? 'Statewide' : 'Territory Scope'}
            </Text>
          </View>
          <View style={styles.statCard}>
            <Text style={styles.statLabel}>ACCOUNT STATUS</Text>
            <View style={styles.statStatusWrapper}>
              <ShieldCheckIcon size={14} color={isActive ? "#10B981" : "#EF4444"} />
              <Text style={[styles.statStatusText, { color: isActive ? "#10B981" : "#EF4444" }]}>
                {isActive ? 'Active' : 'Inactive'}
              </Text>
            </View>
          </View>
        </View>

        {/* Account Details Card */}
        <View style={styles.detailsCard}>
          <Text style={styles.sectionHeaderTitle}>ACCOUNT INFORMATION</Text>

          {/* Designation */}
          <View style={styles.detailItem}>
            <View style={styles.detailIconCircle}>
              <BadgeIcon size={16} color="#0F2042" />
            </View>
            <View style={styles.detailTextWrapper}>
              <Text style={styles.detailLabel}>Designation / Role</Text>
              <Text style={styles.detailValue}>{designation}</Text>
            </View>
          </View>

          <View style={styles.divider} />

          {/* Phone Number */}
          <View style={styles.detailItem}>
            <View style={styles.detailIconCircle}>
              <PhoneIcon size={16} color="#0F2042" />
            </View>
            <View style={styles.detailTextWrapper}>
              <Text style={styles.detailLabel}>Phone Number</Text>
              <Text style={styles.detailValue}>{phone}</Text>
            </View>
          </View>

          <View style={styles.divider} />

          {/* Email Address */}
          <View style={styles.detailItem}>
            <View style={styles.detailIconCircle}>
              <EmailIcon size={16} color="#0F2042" />
            </View>
            <View style={styles.detailTextWrapper}>
              <Text style={styles.detailLabel}>Email Address</Text>
              <Text style={styles.detailValue}>{email}</Text>
            </View>
          </View>

          {/* Depot Assigned (Shown ONLY for Non-Leader roles) */}
          {!isLeaderRole && (
            <>
              <View style={styles.divider} />
              <View style={styles.detailItem}>
                <View style={styles.detailIconCircle}>
                  <LocationIcon size={16} color="#0F2042" />
                </View>
                <View style={styles.detailTextWrapper}>
                  <Text style={styles.detailLabel}>Belongs to Depot</Text>
                  <Text style={styles.detailValue}>{depotName}</Text>
                </View>
              </View>
            </>
          )}
        </View>
      </ScrollView>

      {/* Pinned Bottom Area for Sign Out Button & Footer */}
      <View style={styles.bottomFixedArea}>
        <TouchableOpacity
          style={styles.signOutButton}
          onPress={onLogout}
          activeOpacity={0.8}
        >
          <LogOutIcon color="#EF4444" size={18} />
          <Text style={styles.signOutButtonText}>Sign Out of Account</Text>
        </TouchableOpacity>

        <View style={styles.footer}>
          <Text style={styles.footerText}>Rajasthan Liquor Limited • Powered by Workfloww.ai</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 20,
  },
  profileHeroCard: {
    backgroundColor: '#0F2042',
    borderRadius: 24,
    padding: 20,
    marginBottom: 16,
    shadowColor: '#0F2042',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.18,
    shadowRadius: 12,
    elevation: 5,
  },
  heroTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatarWrapper: {
    position: 'relative',
    marginRight: 16,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#1E293B',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.25)',
  },
  avatarText: {
    color: '#FFFFFF',
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: -0.5,
  },
  heroInfo: {
    flex: 1,
  },
  fullNameText: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: '800',
    letterSpacing: -0.3,
  },
  statsRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
  },
  statCard: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 4,
    elevation: 1,
  },
  statLabel: {
    fontSize: 9,
    fontWeight: '800',
    color: '#94A3B8',
    letterSpacing: 0.5,
  },
  statValue: {
    fontSize: 13,
    fontWeight: '800',
    color: '#0F172A',
    marginTop: 4,
  },
  statStatusWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 4,
  },
  statStatusText: {
    fontSize: 13,
    fontWeight: '800',
  },
  detailsCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 18,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 2,
  },
  sectionHeaderTitle: {
    fontSize: 11,
    fontWeight: '800',
    color: '#64748B',
    letterSpacing: 0.6,
    marginBottom: 14,
  },
  detailItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 4,
  },
  detailIconCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F1F5F9',
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
  divider: {
    height: 1,
    backgroundColor: '#F1F5F9',
    marginVertical: 10,
  },
  bottomFixedArea: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 20,
    backgroundColor: '#F8FAFC',
    borderTopWidth: 1,
    borderTopColor: '#F1F5F9',
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
    marginBottom: 12,
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
    fontWeight: '600',
  },
});
