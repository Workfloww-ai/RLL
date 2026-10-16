import React, { useState, useEffect, useMemo } from 'react';
import FileUpload from '../components/FileUpload';
import { UserPlus, Search, Trash2, Edit2, UploadCloud, User as UserIcon, Check, X, RefreshCw, RotateCcw, ChevronUp, ChevronDown, ArrowUpDown, ChevronLeft, ChevronRight, Mail, Phone, ArrowLeft, Clock, Lock } from 'lucide-react';
import { User } from '../types';
import { API_BASE_URL } from '../config';
import { useToast } from '../contexts/ToastContext';
import { useSystemLock } from '../contexts/SystemLockContext';

const INITIAL_USERS: User[] = [];

const normalizeUser = (u: any): User => {
  if (!u) {
    return {
      id: `u_${Math.random().toString(36).slice(2, 7)}`,
      name: 'Unknown User',
      email: '',
      role: 'Territory Executive',
      depotName: 'Unassigned',
      circleName: 'Unassigned',
      headquarters: 'Unassigned',
      reportingManager: 'Unassigned',
      phoneNumber: '',
      isActive: true,
    };
  }

  const id = String(u.id || u.user_id || `u_${Math.random().toString(36).slice(2, 7)}`);
  const firstName = u.firstName || u.first_name || '';
  const lastName = u.lastName || u.last_name || '';
  const rawName = u.name || `${firstName} ${lastName}`.trim() || u.email || 'Unnamed User';
  const email = u.email || u.user_email || '';

  const role = u.role || u.role_name || 'Territory Executive';
  const depotName = u.depotName || u.depot_name || u.depot || 'Unassigned';
  const circleName = u.circleName || u.circle_name || u.circle || 'Unassigned';
  const headquarters = u.headquarters || u.headquarters_name || u.hq || 'Unassigned';
  const headquarters_ids = Array.isArray(u.headquarters_ids) ? u.headquarters_ids : [];
  const headquartersList = Array.isArray(u.headquarters_list) ? u.headquarters_list : [];
  const reportingManager = u.reportingManager || u.reporting_manager || u.manager || 'Unassigned';
  const phoneNumber = u.phoneNumber || u.phone_number || u.phone || '';
  const isActive = u.isActive ?? u.is_active ?? true;

  return {
    id,
    name: rawName,
    email,
    role,
    depotName,
    circleName,
    headquarters,
    headquarters_ids,
    headquartersList,
    reportingManager,
    phoneNumber,
    isActive,
  };
};

export default function HeadcountManagement() {
  const { isLocked, lockReason, isCooldownActive, formattedCooldown, formattedCooldownLong } = useSystemLock();
  const [users, setUsers] = useState<User[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [showUpload, setShowUpload] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  const [newUser, setNewUser] = useState({ 
    firstName: '', 
    lastName: '', 
    phoneNumber: '', 
    email: '', 
    role: 'ASE', 
    id: '', 
    headquarters: 'Unassigned', 
    headquarters_ids: [] as string[],
    depotName: 'Unassigned', 
    reportingManager: 'Unassigned', 
    isActive: true 
  });

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editRole, setEditRole] = useState<User['role']>('ASE');
  const [editReportingManager, setEditReportingManager] = useState("");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editHeadquartersIds, setEditHeadquartersIds] = useState<string[]>([]);
  const [headquartersOptions, setHeadquartersOptions] = useState<{ headquarters_id: string; name: string }[]>([]);

  type SortField = 'name' | 'phoneNumber' | 'email' | 'role' | 'reportingManager' | 'isActive';
  type SortDirection = 'asc' | 'desc';

  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [managerFilter, setManagerFilter] = useState<string>('all');

  const [sortField, setSortField] = useState<SortField>('name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  const [availableRoles, setAvailableRoles] = useState<{ role_id: string; role_name: string; description?: string }[]>([]);

  const handleToggleUserStatus = async (user: User) => {
    if (isLocked) {
      showToast('System is in read-only mode during data upload. Status change locked.', 'warning');
      return;
    }
    const newActiveState = !user.isActive;

    // Optimistic Update
    const previousState = user.isActive;
    setUsers((prev) => prev.map((u) => u.id === user.id ? { ...u, isActive: newActiveState } : u));
    
    if (!newActiveState) {
      showToast('User deactivated and active sessions revoked.', 'success');
    } else {
      showToast('User reactivated successfully.', 'success');
    }

    const updatedPayload = {
      isActive: newActiveState,
      is_active: newActiveState,
    };

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/users/${user.id}`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(updatedPayload)
      });
      if (!res.ok) {
        throw new Error('Update failed');
      }
    } catch (e) {
      console.error('Error toggling user status:', e);
      // Revert Optimistic Update
      setUsers((prev) => prev.map((u) => u.id === user.id ? { ...u, isActive: previousState } : u));
      showToast('Failed to update user status.', 'error');
    }
  };

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
      const res = await fetch(`${API_BASE_URL}/users/`, { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setUsers(data.map(normalizeUser));
        }
      }
    } catch (err) {
      console.error('Failed to fetch users from backend API:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchRoles = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
      const res = await fetch(`${API_BASE_URL}/users/roles`, { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setAvailableRoles(data);
        }
      }
    } catch (err) {
      console.error('Failed to fetch roles from backend API:', err);
    }
  };

  const fetchHeadquarters = async () => {
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
      const res = await fetch(`${API_BASE_URL}/master-data/headquarters`, { headers });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setHeadquartersOptions(data);
        }
      }
    } catch (err) {
      console.error('Failed to fetch headquarters from backend API:', err);
    }
  };

  useEffect(() => {
    fetchUsers();
    fetchRoles();
    fetchHeadquarters();
  }, []);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const resetFilters = () => {
    setSearchQuery('');
    setRoleFilter('all');
    setStatusFilter('all');
    setManagerFilter('all');
    setSortField('name');
    setSortDirection('asc');
  };

  const handleEditClick = (user: User) => {
    if (isLocked) {
      showToast('System is in read-only mode during data upload. Editing is locked.', 'warning');
      return;
    }
    setEditingId(user.id);
    setEditName(user.name || "");
    setEditPhone(user.phoneNumber || "");
    setEditEmail(user.email || "");
    setEditRole(user.role || 'Territory Executive');
    setEditReportingManager(user.reportingManager || "");
    setEditIsActive(user.isActive ?? true);
    const initialHqIds = (user.headquarters_ids && user.headquarters_ids.length > 0)
      ? user.headquarters_ids
      : (user.headquartersList ? user.headquartersList.map((h: any) => h.headquarters_id) : []);
    setEditHeadquartersIds(initialHqIds);
  };

  const validateUserForm = (firstName: string, email: string, phoneNumber: string, role: string) => {
    if (!firstName || !firstName.trim()) {
      showToast('First Name is mandatory.', 'error');
      return false;
    }
    if (!email || !email.trim()) {
      showToast('Email is mandatory.', 'error');
      return false;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email.trim())) {
      showToast('Please enter a valid email address.', 'error');
      return false;
    }
    if (!phoneNumber || !phoneNumber.trim()) {
      showToast('Phone Number is mandatory.', 'error');
      return false;
    }
    const cleanPhone = phoneNumber.replace(/\D/g, '');
    if (cleanPhone.length !== 10) {
      showToast('Phone Number must be exactly 10 digits.', 'error');
      return false;
    }
    if (!role || !role.trim()) {
      showToast('Role is mandatory.', 'error');
      return false;
    }
    return true;
  };

  const handleSave = async (userId: string) => {
    if (isLocked) {
      showToast('System is in read-only mode during data upload. Edits are locked.', 'warning');
      return;
    }
    if (!editName || !editName.trim()) {
      showToast('First Name / Name is mandatory.', 'error');
      return;
    }
    if (!editEmail || !editEmail.trim()) {
      showToast('Email is mandatory.', 'error');
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(editEmail.trim())) {
      showToast('Please enter a valid email address.', 'error');
      return;
    }
    if (!editPhone || !editPhone.trim()) {
      showToast('Phone Number is mandatory.', 'error');
      return;
    }
    const cleanPhone = editPhone.replace(/\D/g, '');
    if (cleanPhone.length !== 10) {
      showToast('Phone Number must be exactly 10 digits.', 'error');
      return;
    }
    if (!editRole || !editRole.trim()) {
      showToast('Role is mandatory.', 'error');
      return;
    }

    const updatedPayload = {
      name: editName.trim(),
      phone: cleanPhone,
      phoneNumber: cleanPhone,
      email: editEmail.trim(),
      role: editRole,
      reportingManager: editReportingManager ? editReportingManager.trim() : 'Unassigned',
      reporting_manager: editReportingManager ? editReportingManager.trim() : 'Unassigned',
      isActive: editIsActive,
      is_active: editIsActive,
      headquarters_ids: editHeadquartersIds,
    };

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/users/${userId}`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(updatedPayload)
      });
      if (res.ok) {
        const updatedUser = await res.json();
        setUsers((prev) => prev.map((u) => u.id === userId ? normalizeUser({ ...u, ...updatedUser }) : u));
        showToast('User record updated successfully.', 'success');
        setEditingId(null);
      } else {
        const errData = await res.json().catch(() => ({}));
        showToast(errData.detail || 'Failed to update user.', 'error');
      }
    } catch (err) {
      console.error('Error updating user on backend:', err);
      showToast('Network error while saving.', 'error');
    }
  };

  const handleCancel = () => {
    setEditingId(null);
  };

  const handleDelete = async (id: string) => {
    if (isLocked) {
      showToast('System is in read-only mode during data upload. Deletion is locked.', 'warning');
      return;
    }
    if (!confirm("Are you sure you want to delete this user record?")) return;
    try {
      const token = localStorage.getItem('token');
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
      const res = await fetch(`${API_BASE_URL}/users/${id}`, { method: 'DELETE', headers });
      if (res.ok) {
        setUsers(users.filter(u => u.id !== id));
        showToast('User record deleted & active sessions revoked.', 'success');
      } else {
        showToast('Failed to delete user.', 'error');
      }
    } catch (err) {
      console.error('Error deleting user on backend:', err);
      showToast('Network error while deleting.', 'error');
    }
  };

  const handleAdd = async () => {
    if (isLocked) {
      showToast('System is in read-only mode during data upload. Adding users is locked.', 'warning');
      return;
    }
    if (!validateUserForm(newUser.firstName, newUser.email, newUser.phoneNumber, newUser.role)) {
      return;
    }

    const cleanPhone = newUser.phoneNumber.replace(/\D/g, '');
    const fullName = `${newUser.firstName.trim()} ${newUser.lastName.trim()}`.trim();
    const userPayload = {
      ...newUser,
      first_name: newUser.firstName.trim(),
      last_name: newUser.lastName.trim(),
      name: fullName,
      phone: cleanPhone,
      phoneNumber: cleanPhone,
      email: newUser.email.trim(),
      role: newUser.role,
      circleName: 'Unassigned',
      reportingManager: newUser.reportingManager ? newUser.reportingManager.trim() : 'Unassigned',
      reporting_manager: newUser.reportingManager ? newUser.reportingManager.trim() : 'Unassigned',
      is_active: newUser.isActive,
      headquarters_ids: newUser.headquarters_ids || [],
    };

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/users/`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(userPayload)
      });
      if (res.ok) {
        const created = await res.json();
        setUsers([normalizeUser(created), ...users]);
        showToast('User created successfully.', 'success');
        setIsAdding(false);
        setNewUser({ firstName: '', lastName: '', phoneNumber: '', email: '', role: 'ASE', id: '', headquarters: 'Unassigned', headquarters_ids: [], depotName: 'Unassigned', reportingManager: 'Unassigned', isActive: true });
      } else {
        const errData = await res.json().catch(() => ({}));
        showToast(errData.detail || 'Failed to create user.', 'error');
      }
    } catch (err) {
      console.error('Error creating user on backend:', err);
      showToast('Network error while saving.', 'error');
    }
  };

  // Extract unique reporting managers & roles for filters
  const uniqueManagers = useMemo(() => {
    const managers = new Set<string>();
    users.forEach(u => {
      if (u.reportingManager && u.reportingManager !== 'Unassigned') {
        managers.add(u.reportingManager);
      }
    });
    return Array.from(managers).sort();
  }, [users]);

  const uniqueRoles = useMemo(() => {
    const roles = new Set<string>();
    if (availableRoles.length > 0) {
      availableRoles.forEach(r => roles.add(r.role_name));
    }
    users.forEach(u => {
      if (u.role) roles.add(u.role);
    });
    return Array.from(roles).sort();
  }, [users, availableRoles]);

  const filteredUsers = useMemo(() => {
    let result = users.filter(u => {
      if (!u) return false;
      // Always retain row currently being edited so editing controls never disappear mid-edit
      if (editingId !== null && String(u.id) === String(editingId)) {
        return true;
      }

      // Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matches =
          (u.name || '').toLowerCase().includes(q) ||
          (u.id || '').toLowerCase().includes(q) ||
          (u.role || '').toLowerCase().includes(q) ||
          (u.phoneNumber || '').toLowerCase().includes(q) ||
          (u.email || '').toLowerCase().includes(q) ||
          (u.reportingManager || '').toLowerCase().includes(q);
        if (!matches) return false;
      }

      // Role filter
      if (roleFilter !== 'all' && u.role !== roleFilter) return false;

      // Status filter
      if (statusFilter === 'active' && u.isActive !== true) return false;
      if (statusFilter === 'inactive' && u.isActive !== false) return false;

      // Manager filter
      if (managerFilter !== 'all' && u.reportingManager !== managerFilter) return false;

      return true;
    });

    // Sorting
    result.sort((a, b) => {
      let aVal: any = "";
      let bVal: any = "";

      if (sortField === 'isActive') {
        aVal = a.isActive ? 1 : 0;
        bVal = b.isActive ? 1 : 0;
      } else {
        aVal = a[sortField] ?? "";
        bVal = b[sortField] ?? "";
      }

      if (typeof aVal === "string") aVal = aVal.toLowerCase();
      if (typeof bVal === "string") bVal = bVal.toLowerCase();

      if (aVal < bVal) return sortDirection === "asc" ? -1 : 1;
      if (aVal > bVal) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });

    return result;
  }, [users, searchQuery, roleFilter, statusFilter, managerFilter, sortField, sortDirection, editingId]);

  const getRoleColor = (role: string) => {
    switch (role) {
      case 'TSM':
      case 'Area Sales Manager':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'ASE':
      case 'Territory Executive':
        return 'bg-[#004B87]/10 text-[#004B87] border-[#004B87]/30';
      case 'Regional Supervisor':
      case 'RS':
        return 'bg-indigo-50 text-indigo-700 border-indigo-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, roleFilter, statusFilter, managerFilter]);

  const totalPages = Math.ceil(filteredUsers.length / rowsPerPage) || 1;
  const paginatedUsers = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return filteredUsers.slice(start, start + rowsPerPage);
  }, [filteredUsers, currentPage, rowsPerPage]);

  return (
    <div className="w-full h-full min-h-0 flex flex-col space-y-2.5">
      {/* Read-Only Mode Warning Banner */}
      {isLocked && (
        <div className="bg-amber-50 border border-amber-300 text-amber-900 rounded-xl px-4 py-2.5 flex items-center justify-between gap-3 text-xs shrink-0 shadow-2xs">
          <div className="flex items-center gap-2.5">
            <span className="flex h-2.5 w-2.5 relative shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
            </span>
            <span>
              <strong className="font-bold text-amber-950">Read-Only Mode Active:</strong>{' '}
              {lockReason || 'Data upload in progress.'} User adjustments, role edits, reporting manager assignments, and bulk uploads are disabled.
            </span>
          </div>
          <span className="px-2 py-0.5 bg-amber-200/90 text-amber-950 font-extrabold text-[10px] uppercase rounded tracking-wider shrink-0">
            Read-Only
          </span>
        </div>
      )}

      {/* Integrated Control Toolbar */}
      <div className="bg-white py-2 px-3 rounded-xl border border-slate-200/80 shadow-2xs flex flex-wrap items-center gap-3 text-xs shrink-0">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input 
            type="text" 
            placeholder="Search by name, email, phone, role, or manager..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200/80 rounded-lg font-medium text-slate-900 focus:outline-none focus:border-[#0D3B8E] focus:bg-white transition-all text-xs placeholder:text-slate-400"
          />
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-slate-400 font-bold uppercase tracking-wider text-[9px]">Role:</span>
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="px-2.5 py-1 bg-slate-50 border border-slate-200/80 rounded-lg font-bold text-slate-700 text-xs focus:outline-none focus:border-[#0D3B8E]"
          >
            <option value="all">All Roles</option>
            {uniqueRoles.map(r => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-slate-400 font-bold uppercase tracking-wider text-[9px]">Status:</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
            className="px-2.5 py-1 bg-slate-50 border border-slate-200/80 rounded-lg font-bold text-slate-700 text-xs focus:outline-none focus:border-[#0D3B8E]"
          >
            <option value="all">All Statuses</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-slate-400 font-bold uppercase tracking-wider text-[9px]">Manager:</span>
          <select
            value={managerFilter}
            onChange={(e) => setManagerFilter(e.target.value)}
            className="px-2.5 py-1 bg-slate-50 border border-slate-200/80 rounded-lg font-bold text-slate-700 text-xs focus:outline-none focus:border-[#0D3B8E]"
          >
            <option value="all">All Managers</option>
            {uniqueManagers.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <button
          onClick={resetFilters}
          className="flex items-center gap-1 text-[11px] font-bold text-slate-400 hover:text-slate-700 transition-colors cursor-pointer mr-1"
          title="Reset Filters"
        >
          <RotateCcw className="w-3 h-3" /> Reset
        </button>

        <div className="h-4 w-px bg-slate-200 mx-0.5"></div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <button 
            disabled={isLocked || isCooldownActive}
            onClick={() => !isLocked && !isCooldownActive && setShowUpload(!showUpload)}
            title={
              isLocked 
                ? "Bulk upload is locked during active data ingestion" 
                : isCooldownActive 
                  ? `Bulk upload is paused for 30 minutes after an upload. Enabled in ${formattedCooldown}` 
                  : "Bulk Upload"
            }
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
              (isLocked || isCooldownActive)
                ? 'opacity-60 cursor-not-allowed bg-amber-50/60 text-amber-800 border border-amber-300' 
                : showUpload 
                  ? 'bg-slate-200 hover:bg-slate-300 text-slate-800 border border-slate-300 cursor-pointer' 
                  : 'bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 cursor-pointer'
            }`}
          >
            {showUpload ? (
              <>
                <ArrowLeft className="w-3.5 h-3.5 text-slate-700" />
                Back to User List
              </>
            ) : isCooldownActive ? (
              <>
                <Clock className="w-3.5 h-3.5 text-amber-600 animate-spin" style={{ animationDuration: '6s' }} />
                <span>Bulk Upload ({formattedCooldown})</span>
              </>
            ) : (
              <>
                <UploadCloud className="w-3.5 h-3.5 text-[#0D3B8E]" />
                Bulk Upload
              </>
            )}
          </button>
          <button 
            disabled={isLocked}
            onClick={() => !isLocked && setIsAdding(!isAdding)}
            title={isLocked ? "Adding users is locked during active data ingestion" : "Add User"}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all shadow-md shadow-[#0D3B8E]/15 ${
              isLocked 
                ? 'opacity-40 cursor-not-allowed bg-slate-400 text-white' 
                : 'bg-[#0D3B8E] hover:bg-[#0A2F73] text-white cursor-pointer'
            }`}
          >
            <UserPlus className="w-3.5 h-3.5" />
            Add User
          </button>
        </div>
      </div>

      {/* Bulk Upload Drawer */}
      {showUpload && (
        <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-sm transition-all">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-900">Bulk User Roster Upload</h3>
                {isCooldownActive && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                    <Clock size={10} /> Cooldown: {formattedCooldown} remaining
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-0.5">Upload an Excel (.xlsx, .xls, .xlsb) or CSV file containing user personnel data to automatically populate the database.</p>
            </div>
            <button 
              onClick={() => setShowUpload(false)}
              className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
              title="Close Panel"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <FileUpload
            title="Upload Personnel Roster File"
            instructions={[
              "Supported file formats: .xlsx, .xls, .xlsb, .csv",
              "Recognized column aliases: Name, First Name, Last Name, Email, Phone, Role, Reporting Manager, Depot, HQ",
              "Personnel records will be automatically created & updated in the database users table"
            ]}
            uploadEndpoint={`${API_BASE_URL}/users/upload-roster`}
            onUploadComplete={() => {
              showToast('User roster excel uploaded and database populated successfully!', 'success');
              fetchUsers();
            }}
          />
        </div>
      )}

      {/* Add User Form Drawer */}
      {isAdding && (
        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm mb-6">
          <h3 className="text-sm font-bold text-slate-900 mb-4">Add New Personnel Record</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                First Name <span className="text-red-500">*</span>
              </label>
              <input 
                type="text" 
                value={newUser.firstName}
                onChange={(e) => setNewUser({...newUser, firstName: e.target.value})}
                placeholder="First Name"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                Last Name <span className="text-slate-400 font-normal lowercase">(optional)</span>
              </label>
              <input 
                type="text" 
                value={newUser.lastName}
                onChange={(e) => setNewUser({...newUser, lastName: e.target.value})}
                placeholder="Last Name"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                Email Address <span className="text-red-500">*</span>
              </label>
              <input 
                type="email" 
                value={newUser.email}
                onChange={(e) => setNewUser({...newUser, email: e.target.value})}
                placeholder="email@rll.com"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                Phone Number (10 Digits) <span className="text-red-500">*</span>
              </label>
              <input 
                type="text" 
                maxLength={10}
                value={newUser.phoneNumber}
                onChange={(e) => setNewUser({...newUser, phoneNumber: e.target.value.replace(/\D/g, '').slice(0, 10)})}
                placeholder="9876543210"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                Assigned Role <span className="text-red-500">*</span>
              </label>
              <select 
                value={newUser.role}
                onChange={(e) => setNewUser({...newUser, role: e.target.value})}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              >
                {(availableRoles.length > 0 ? availableRoles.map(r => r.role_name) : ["ASE", "TSM", "Regional Supervisor", "Admin"]).map((rName) => (
                  <option key={rName} value={rName}>{rName}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                Reporting Manager <span className="text-slate-400 font-normal lowercase">(optional)</span>
              </label>
              <input 
                type="text" 
                value={newUser.reportingManager}
                onChange={(e) => setNewUser({...newUser, reportingManager: e.target.value})}
                placeholder="Manager Name"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div className="md:col-span-3">
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                Assigned Headquarters <span className="text-slate-400 font-normal lowercase">(multi-select)</span>
              </label>
              <div className="flex flex-wrap gap-1.5 p-2.5 bg-slate-50 border border-slate-200 rounded-xl min-h-[42px] max-h-36 overflow-y-auto">
                {headquartersOptions.length === 0 ? (
                  <span className="text-xs text-slate-400 italic">No headquarters available</span>
                ) : (
                  headquartersOptions.map((hq) => {
                    const isSelected = (newUser.headquarters_ids || []).includes(hq.headquarters_id);
                    return (
                      <button
                        key={hq.headquarters_id}
                        type="button"
                        onClick={() => {
                          const current = newUser.headquarters_ids || [];
                          const next = isSelected
                            ? current.filter((id) => id !== hq.headquarters_id)
                            : [...current, hq.headquarters_id];
                          setNewUser({ ...newUser, headquarters_ids: next });
                        }}
                        className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer flex items-center gap-1 ${
                          isSelected
                            ? 'bg-[#0D3B8E] text-white shadow-xs'
                            : 'bg-white text-slate-600 border border-slate-200 hover:border-slate-300'
                        }`}
                      >
                        {hq.name}
                        {isSelected && <Check className="w-3 h-3 ml-0.5" />}
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>
          <div className="flex gap-2 mt-4 justify-end">
            <button 
              onClick={() => setIsAdding(false)}
              className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-50 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button 
              onClick={handleAdd}
              className="px-5 py-2 bg-[#0D3B8E] text-white rounded-xl text-xs font-bold hover:bg-[#0A2F73] transition-colors cursor-pointer shadow-xs"
            >
              Save Record
            </button>
          </div>
        </div>
      )}

      {/* Table Card */}
      {!showUpload && (
        <div className="bg-white rounded-2xl shadow-2xs border border-slate-200/80 flex-1 min-h-0 overflow-hidden flex flex-col">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left border-collapse table-fixed min-w-[1020px]">
            <thead>
              <tr className="bg-slate-50/80 border-b border-slate-200/80 select-none">
                {/* S.No Column */}
                <th className="w-[4%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">
                  #
                </th>

                {/* Name */}
                <th 
                  onClick={() => handleSort('name')}
                  className="w-[16%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Name</span>
                    {sortField === 'name' ? (
                      sortDirection === 'asc' ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Phone Number */}
                <th 
                  onClick={() => handleSort('phoneNumber')}
                  className="w-[11%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Phone Number</span>
                    {sortField === 'phoneNumber' ? (
                      sortDirection === 'asc' ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Email */}
                <th 
                  onClick={() => handleSort('email')}
                  className="w-[16%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Email</span>
                    {sortField === 'email' ? (
                      sortDirection === 'asc' ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Role */}
                <th 
                  onClick={() => handleSort('role')}
                  className="w-[9%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Role</span>
                    {sortField === 'role' ? (
                      sortDirection === 'asc' ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Headquarters */}
                <th className="w-[18%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                  Headquarters
                </th>

                {/* Reporting Manager */}
                <th 
                  onClick={() => handleSort('reportingManager')}
                  className="w-[12%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Reporting Manager</span>
                    {sortField === 'reportingManager' ? (
                      sortDirection === 'asc' ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Status */}
                <th 
                  onClick={() => handleSort('isActive')}
                  className="w-[7%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Status</span>
                    {sortField === 'isActive' ? (
                      sortDirection === 'asc' ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Actions */}
                <th className="w-[7%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {paginatedUsers.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                    {loading ? (
                      <span className="inline-flex items-center gap-2 text-slate-600 font-semibold">
                        <RefreshCw className="w-4 h-4 animate-spin text-[#0D3B8E]" /> Loading personnel from database...
                      </span>
                    ) : searchQuery ? (
                      "No records found matching your search query."
                    ) : (
                      "No Data Found."
                    )}
                  </td>
                </tr>
              ) : (
                paginatedUsers.map((user, idx) => {
                  const serialNumber = (currentPage - 1) * rowsPerPage + idx + 1;

                  return (
                    <tr key={user.id} className="hover:bg-blue-50/20 transition-colors group">
                      {/* S.No */}
                      <td className="px-4 py-2.5 text-center text-xs font-bold text-slate-400">
                        {serialNumber}
                      </td>

                      {/* Name */}
                      <td className="px-4 py-2.5">
                        {editingId === user.id ? (
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
                          />
                        ) : (
                          <div className="flex items-center gap-2.5">
                            <div className="w-7 h-7 rounded-full bg-[#0D3B8E]/10 flex items-center justify-center text-[#0D3B8E] font-bold text-xs shrink-0">
                              {user.name.charAt(0)}
                            </div>
                            <p className="font-bold text-slate-900 text-xs truncate">{user.name}</p>
                          </div>
                        )}
                      </td>

                      {/* Phone Number */}
                      <td className="px-4 py-2.5">
                        {editingId === user.id ? (
                          <input
                            type="text"
                            value={editPhone}
                            onChange={(e) => setEditPhone(e.target.value)}
                            className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
                          />
                        ) : (
                          <div className="flex items-center gap-2 text-slate-600">
                            <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            <span className="text-xs font-bold truncate">{user.phoneNumber || 'N/A'}</span>
                          </div>
                        )}
                      </td>

                      {/* Email */}
                      <td className="px-4 py-2.5">
                        {editingId === user.id ? (
                          <input
                            type="email"
                            value={editEmail}
                            onChange={(e) => setEditEmail(e.target.value)}
                            className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
                          />
                        ) : (
                          <div className="flex items-center gap-2 text-slate-600">
                            <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            <span className="text-xs font-medium truncate">{user.email || 'N/A'}</span>
                          </div>
                        )}
                      </td>

                      {/* Role */}
                      <td className="px-4 py-2.5">
                        {editingId === user.id ? (
                          <select
                            value={editRole}
                            onChange={(e) => setEditRole(e.target.value as any)}
                            className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
                          >
                            {(availableRoles.length > 0 ? availableRoles.map(r => r.role_name) : ["ASE", "TSM", "Regional Supervisor", "Admin"]).map((rName) => (
                              <option key={rName} value={rName}>{rName}</option>
                            ))}
                          </select>
                        ) : (
                          <span className={`px-2.5 py-1 rounded border text-[10px] font-bold uppercase tracking-wider ${getRoleColor(user.role)}`}>
                            {user.role}
                          </span>
                        )}
                      </td>

                      {/* Headquarters */}
                      <td className="px-4 py-2.5">
                        {editingId === user.id ? (
                          <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto p-1 bg-white border border-slate-300 rounded">
                            {headquartersOptions.length === 0 ? (
                              <span className="text-[11px] text-slate-400 italic">No HQs</span>
                            ) : (
                              headquartersOptions.map((hq) => {
                                const isSelected = editHeadquartersIds.includes(hq.headquarters_id);
                                return (
                                  <button
                                    key={hq.headquarters_id}
                                    type="button"
                                    onClick={() => {
                                      setEditHeadquartersIds((prev) =>
                                        isSelected
                                          ? prev.filter((id) => id !== hq.headquarters_id)
                                          : [...prev, hq.headquarters_id]
                                      );
                                    }}
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold transition-all cursor-pointer ${
                                      isSelected
                                        ? 'bg-[#0D3B8E] text-white'
                                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                    }`}
                                  >
                                    {hq.name}
                                  </button>
                                );
                              })
                            )}
                          </div>
                        ) : (
                          <div className="flex flex-wrap gap-1 items-center max-w-[220px]">
                            {user.headquartersList && user.headquartersList.length > 0 ? (
                              user.headquartersList.map((hq) => (
                                <span
                                  key={hq.headquarters_id}
                                  className="px-2 py-0.5 rounded-md bg-blue-50 text-[#0D3B8E] border border-blue-200/60 text-[10px] font-bold truncate"
                                  title={hq.name}
                                >
                                  {hq.name}
                                </span>
                              ))
                            ) : user.headquarters && user.headquarters !== "Unassigned" ? (
                              user.headquarters.split(',').map((h, i) => (
                                <span
                                  key={i}
                                  className="px-2 py-0.5 rounded-md bg-blue-50 text-[#0D3B8E] border border-blue-200/60 text-[10px] font-bold truncate"
                                  title={h.trim()}
                                >
                                  {h.trim()}
                                </span>
                              ))
                            ) : (
                              <span className="text-slate-400 italic text-[11px]">Unassigned</span>
                            )}
                          </div>
                        )}
                      </td>

                      {/* Reporting Manager */}
                      <td className="px-4 py-2.5">
                        {editingId === user.id ? (
                          <input
                            type="text"
                            value={editReportingManager}
                            onChange={(e) => setEditReportingManager(e.target.value)}
                            className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
                          />
                        ) : (
                          <p className={`text-xs font-bold truncate ${!user.reportingManager || user.reportingManager === "Unassigned" ? "text-slate-400 italic" : "text-slate-700"}`}>
                            {user.reportingManager || "Unassigned"}
                          </p>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-4 py-2.5">
                        {editingId === user.id ? (
                          <button
                            type="button"
                            onClick={() => setEditIsActive(!editIsActive)}
                            className="flex items-center gap-2 cursor-pointer group select-none"
                            title={`Click to switch to ${editIsActive ? 'Inactive' : 'Active'}`}
                          >
                            <div
                              className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                                editIsActive ? 'bg-emerald-500' : 'bg-slate-300'
                              }`}
                            >
                              <span
                                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                                  editIsActive ? 'translate-x-4' : 'translate-x-0'
                                }`}
                              />
                            </div>
                            <span className={`text-xs font-extrabold ${editIsActive ? 'text-emerald-700' : 'text-slate-500'}`}>
                              {editIsActive ? 'Active' : 'Inactive'}
                            </span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={isLocked}
                            onClick={() => !isLocked && handleToggleUserStatus(user)}
                            className={`flex items-center gap-2 select-none ${isLocked ? 'cursor-not-allowed opacity-50' : 'cursor-pointer group'}`}
                            title={isLocked ? 'Status changes are locked during active data ingestion' : `Click to ${user.isActive ? 'deactivate user' : 'reactivate user'}`}
                          >
                            <div
                              className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                                user.isActive ? 'bg-emerald-500' : 'bg-slate-300'
                              }`}
                            >
                              <span
                                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                                  user.isActive ? 'translate-x-4' : 'translate-x-0'
                                }`}
                              />
                            </div>
                            <span className={`text-xs font-bold ${user.isActive ? 'text-emerald-700' : 'text-slate-500'}`}>
                              {user.isActive ? 'Active' : 'Inactive'}
                            </span>
                          </button>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-2.5 text-right">
                        {editingId === user.id ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              disabled={isLocked}
                              onClick={() => handleSave(user.id)}
                              className="p-1 bg-emerald-50 text-emerald-600 rounded hover:bg-emerald-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                              title="Save Changes"
                            >
                              <Check className="w-4 h-4" />
                            </button>
                            <button
                              onClick={handleCancel}
                              className="p-1 bg-slate-100 text-slate-600 rounded hover:bg-slate-200 transition-colors"
                              title="Cancel"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              disabled={isLocked}
                              onClick={() => !isLocked && handleEditClick(user)}
                              title={isLocked ? 'Editing is locked during active data ingestion' : 'Edit'}
                              className={`px-2.5 py-1 border rounded text-[10px] font-bold uppercase tracking-wider inline-flex items-center gap-1 transition-colors ${
                                isLocked 
                                  ? 'border-slate-200 text-slate-300 cursor-not-allowed opacity-50' 
                                  : 'border-slate-200 text-slate-600 hover:border-[#0D3B8E] hover:text-[#0D3B8E] cursor-pointer'
                              }`}
                            >
                              <Edit2 className="w-3 h-3" /> Edit
                            </button>
                            <button 
                              disabled={isLocked}
                              onClick={() => !isLocked && handleDelete(user.id)}
                              className={`p-1 rounded transition-colors inline-flex ${
                                isLocked 
                                  ? 'text-slate-200 cursor-not-allowed opacity-40' 
                                  : 'text-slate-400 hover:text-red-500 hover:bg-red-50 cursor-pointer'
                              }`}
                              title={isLocked ? 'Deletion is locked during active data ingestion' : 'Delete Record'}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          <div className="px-4 py-3 bg-slate-50/80 border-t border-slate-200/80 flex items-center justify-between text-xs select-none shrink-0">
            <div className="flex items-center gap-2 font-bold text-slate-500 text-[11px]">
              <span>SHOWING {filteredUsers.length === 0 ? 0 : (currentPage - 1) * rowsPerPage + 1} TO {Math.min(currentPage * rowsPerPage, filteredUsers.length)} OF {filteredUsers.length} USER RECORDS</span>
              <div className="flex items-center gap-1.5 ml-4">
                <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">ROWS:</span>
                <select
                  value={rowsPerPage}
                  onChange={(e) => { setRowsPerPage(Number(e.target.value)); setCurrentPage(1); }}
                  className="px-2.5 py-1 bg-white border border-slate-200/80 rounded-lg text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
                >
                  <option value={10}>10</option>
                  <option value={15}>15</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                className="p-1.5 border border-slate-200 bg-white rounded-lg disabled:opacity-40 text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 bg-white border border-slate-200/80 rounded-lg text-xs font-bold text-[#0D3B8E]">
                Page {currentPage} of {totalPages}
              </span>
              <button
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                className="p-1.5 border border-slate-200 bg-white rounded-lg disabled:opacity-40 text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
