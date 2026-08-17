import React from 'react';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';

interface IconProps {
  color?: string;
  size?: number;
}

export const SearchIcon = ({ color = '#94A3B8', size = 16 }: IconProps) => (
  <MaterialIcons name="search" size={size} color={color} />
);

export const BuildingIcon = ({ color = '#94A3B8', size = 16 }: IconProps) => (
  <MaterialIcons name="business" size={size} color={color} />
);

export const StoreIcon = ({ color = '#94A3B8', size = 16 }: IconProps) => (
  <MaterialIcons name="store" size={size} color={color} />
);

export const UsersIcon = ({ color = '#94A3B8', size = 16 }: IconProps) => (
  <MaterialIcons name="group" size={size} color={color} />
);

export const UserIcon = ({ color = '#94A3B8', size = 16 }: IconProps) => (
  <MaterialIcons name="person" size={size} color={color} />
);

export const LogOutIcon = ({ color = '#FFFFFF', size = 16 }: IconProps) => (
  <MaterialIcons name="logout" size={size} color={color} />
);

export const ShieldAlertIcon = ({ color = '#EF4444', size = 24 }: IconProps) => (
  <MaterialIcons name="error-outline" size={size} color={color} />
);

export const XIcon = ({ color = '#94A3B8', size = 16 }: IconProps) => (
  <MaterialIcons name="close" size={size} color={color} />
);

export const ArrowRightIcon = ({ color = '#000000', size = 16 }: IconProps) => (
  <MaterialIcons name="chevron-right" size={size} color={color} />
);

export const KeyIcon = ({ color = '#F59E0B', size = 20 }: IconProps) => (
  <MaterialIcons name="vpn-key" size={size} color={color} />
);

export const RefreshIcon = ({ color = '#94A3B8', size = 14 }: IconProps) => (
  <MaterialIcons name="refresh" size={size} color={color} />
);

export const EditIcon = ({ color = '#94A3B8', size = 14 }: IconProps) => (
  <MaterialIcons name="edit" size={size} color={color} />
);

export const PinIcon = ({ color = '#F59E0B', size = 14 }: IconProps) => (
  <MaterialIcons name="push-pin" size={size} color={color} />
);

export const CheckCircleIcon = ({ color = '#10B981', size = 14 }: IconProps) => (
  <MaterialIcons name="check-circle" size={size} color={color} />
);

export const LocationIcon = ({ color = '#FFFFFF', size = 16 }: IconProps) => (
  <MaterialIcons name="location-on" size={size} color={color} />
);

export const CalendarIcon = ({ color = '#FFFFFF', size = 16 }: IconProps) => (
  <MaterialIcons name="event" size={size} color={color} />
);

export const ChevronLeftIcon = ({ color = '#94A3B8', size = 16 }: IconProps) => (
  <MaterialIcons name="chevron-left" size={size} color={color} />
);

export const ChevronRightIcon = ({ color = '#94A3B8', size = 16 }: IconProps) => (
  <MaterialIcons name="chevron-right" size={size} color={color} />
);

export const WineIcon = ({ color = '#0F172A', size = 14 }: IconProps) => (
  <MaterialIcons name="local-bar" size={size} color={color} />
);

export const SwapVertIcon = ({ color = '#64748B', size = 14 }: IconProps) => (
  <MaterialIcons name="swap-vert" size={size} color={color} />
);

export const ChevronDownIcon = ({ color = '#94A3B8', size = 14 }: IconProps) => (
  <MaterialIcons name="arrow-drop-down" size={size} color={color} />
);


