import React, { useState, useEffect, useMemo } from 'react';
import FileUpload from '../components/FileUpload';
import { UserPlus, Search, Trash2, Edit2, UploadCloud, User as UserIcon, Check, X, RefreshCw, Mail, Phone, Shield, RotateCcw, ChevronUp, ChevronDown, ArrowUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { User } from '../types';
import { API_BASE_URL } from '../config';

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
    reportingManager,
    phoneNumber,
    isActive,
  };
};

export default function HeadcountManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [showUpload, setShowUpload] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [loading, setLoading] = useState(false);

  const [newUser, setNewUser] = useState({ 
    firstName: '', 
    lastName: '', 
    phoneNumber: '', 
    email: '', 
    role: 'ASE', 
    id: '', 
    headquarters: 'Unassigned', 
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

  type SortField = 'name' | 'phoneNumber' | 'email' | 'role' | 'reportingManager' | 'isActive';
  type SortDirection = 'asc' | 'desc';

  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [managerFilter, setManagerFilter] = useState<string>('all');

  const [sortField, setSortField] = useState<SortField>('name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  const [availableRoles, setAvailableRoles] = useState<{ role_id: string; role_name: string; description?: string }[]>([]);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/users/`);
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
      const res = await fetch(`${API_BASE_URL}/users/roles`);
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

  useEffect(() => {
    fetchUsers();
    fetchRoles();
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
    setEditingId(user.id);
    setEditName(user.name || "");
    setEditPhone(user.phoneNumber || "");
    setEditEmail(user.email || "");
    setEditRole(user.role || 'Territory Executive');
    setEditReportingManager(user.reportingManager || "");
    setEditIsActive(user.isActive ?? true);
  };

  const handleSave = async (userId: string) => {
    const updatedPayload = {
      name: editName,
      phone: editPhone,
      phoneNumber: editPhone,
      email: editEmail,
      role: editRole,
      reportingManager: editReportingManager,
      reporting_manager: editReportingManager,
      isActive: editIsActive,
      is_active: editIsActive,
    };

    try {
      const res = await fetch(`${API_BASE_URL}/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedPayload)
      });
      if (res.ok) {
        const updatedUser = await res.json();
        setUsers((prev) => prev.map((u) => u.id === userId ? normalizeUser({ ...u, ...updatedUser }) : u));
      } else {
        setUsers((prev) => prev.map((u) => u.id === userId ? normalizeUser({ ...u, ...updatedPayload }) : u));
      }
    } catch (err) {
      console.error('Error updating user on backend:', err);
      setUsers((prev) => prev.map((u) => u.id === userId ? normalizeUser({ ...u, ...updatedPayload }) : u));
    }
    setEditingId(null);
  };

  const handleCancel = () => {
    setEditingId(null);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this user record?")) return;
    try {
      await fetch(`${API_BASE_URL}/users/${id}`, { method: 'DELETE' });
    } catch (err) {
      console.error('Error deleting user on backend:', err);
    }
    setUsers(users.filter(u => u.id !== id));
  };

  const handleAdd = async () => {
    if (newUser.firstName.trim() || newUser.email.trim() || newUser.phoneNumber.trim()) {
      const fullName = `${newUser.firstName} ${newUser.lastName}`.trim();
      const userPayload = {
        ...newUser,
        first_name: newUser.firstName,
        last_name: newUser.lastName,
        name: fullName,
        phone: newUser.phoneNumber,
        phoneNumber: newUser.phoneNumber,
        email: newUser.email,
        circleName: 'Unassigned',
        reportingManager: newUser.reportingManager || 'Unassigned',
        reporting_manager: newUser.reportingManager || 'Unassigned',
        is_active: newUser.isActive
      };

      try {
        const res = await fetch(`${API_BASE_URL}/users/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(userPayload)
        });
        if (res.ok) {
          const created = await res.json();
          setUsers([normalizeUser(created), ...users]);
        } else {
          setUsers([normalizeUser(userPayload), ...users]);
        }
      } catch (err) {
        console.error('Error creating user on backend:', err);
        setUsers([normalizeUser(userPayload), ...users]);
      }

      setIsAdding(false);
      setNewUser({ firstName: '', lastName: '', phoneNumber: '', email: '', role: 'ASE', id: '', headquarters: 'Unassigned', depotName: 'Unassigned', reportingManager: 'Unassigned', isActive: true });
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
            onClick={() => setShowUpload(!showUpload)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 rounded-lg text-xs font-bold transition-colors cursor-pointer"
          >
            <UploadCloud className="w-3.5 h-3.5 text-[#0D3B8E]" />
            Bulk Upload
          </button>
          <button 
            onClick={() => setIsAdding(!isAdding)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0D3B8E] hover:bg-[#0A2F73] text-white rounded-lg text-xs font-bold transition-all shadow-md shadow-[#0D3B8E]/15 cursor-pointer"
          >
            <UserPlus className="w-3.5 h-3.5" />
            Add User
          </button>
        </div>
      </div>

      {/* Add User Form Drawer */}
      {isAdding && (
        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-sm mb-6">
          <h3 className="text-sm font-bold text-slate-900 mb-4">Add New Personnel Record</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">First Name</label>
              <input 
                type="text" 
                value={newUser.firstName}
                onChange={(e) => setNewUser({...newUser, firstName: e.target.value})}
                placeholder="First Name"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Last Name</label>
              <input 
                type="text" 
                value={newUser.lastName}
                onChange={(e) => setNewUser({...newUser, lastName: e.target.value})}
                placeholder="Last Name"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Email Address</label>
              <input 
                type="email" 
                value={newUser.email}
                onChange={(e) => setNewUser({...newUser, email: e.target.value})}
                placeholder="email@rll.com"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Phone Number</label>
              <input 
                type="text" 
                value={newUser.phoneNumber}
                onChange={(e) => setNewUser({...newUser, phoneNumber: e.target.value})}
                placeholder="+91 9876543210"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Assigned Role</label>
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
              <label className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Reporting Manager</label>
              <input 
                type="text" 
                value={newUser.reportingManager}
                onChange={(e) => setNewUser({...newUser, reportingManager: e.target.value})}
                placeholder="Manager Name"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 focus:outline-none focus:border-[#0D3B8E]"
              />
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
      <div className="bg-white rounded-2xl shadow-2xs border border-slate-200/80 flex-1 min-h-0 overflow-hidden flex flex-col">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left border-collapse table-fixed min-w-[800px]">
            <thead>
              <tr className="bg-slate-50/80 border-b border-slate-200/80 select-none">
                {/* S.No Column */}
                <th className="w-[6%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">
                  #
                </th>

                {/* Name */}
                <th 
                  onClick={() => handleSort('name')}
                  className="w-[20%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
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
                  className="w-[15%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
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
                  className="w-[22%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
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
                  className="w-[13%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
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

                {/* Reporting Manager */}
                <th 
                  onClick={() => handleSort('reportingManager')}
                  className="w-[16%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
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
                  className="w-[10%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
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
                <th className="w-[10%] px-4 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {paginatedUsers.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
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
                          <select
                            value={editIsActive ? "active" : "inactive"}
                            onChange={(e) => setEditIsActive(e.target.value === "active")}
                            className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
                          >
                            <option value="active">Active</option>
                            <option value="inactive">Inactive</option>
                          </select>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <span className={`w-2 h-2 rounded-full ${user.isActive ? 'bg-emerald-500' : 'bg-slate-300'}`}></span>
                            <span className={`text-xs font-bold ${user.isActive ? 'text-emerald-700' : 'text-slate-500'}`}>
                              {user.isActive ? 'Active' : 'Inactive'}
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-2.5 text-right">
                        {editingId === user.id ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => handleSave(user.id)}
                              className="p-1 bg-emerald-50 text-emerald-600 rounded hover:bg-emerald-100 transition-colors"
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
                              onClick={() => handleEditClick(user)}
                              className="px-2.5 py-1 border border-slate-200 rounded text-[10px] font-bold text-slate-600 hover:border-[#0D3B8E] hover:text-[#0D3B8E] transition-colors uppercase tracking-wider inline-flex items-center gap-1 cursor-pointer"
                            >
                              <Edit2 className="w-3 h-3" /> Edit
                            </button>
                            <button 
                              onClick={() => handleDelete(user.id)}
                              className="p-1 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors inline-flex cursor-pointer"
                              title="Delete Record"
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

        {/* Full Pagination Footer */}
        <div className="p-4 bg-slate-50/80 border-t border-slate-200/80 text-xs font-semibold text-slate-600 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
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
    </div>
  );
}
