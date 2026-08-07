import React, { useState, useEffect } from 'react';
import FileUpload from '../components/FileUpload';
import { UserPlus, Search, Trash2, Edit2, UploadCloud, User as UserIcon, Check, X, RefreshCw, Mail, Phone, Shield } from 'lucide-react';
import { User } from '../types';

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

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/v1/users/');
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

  useEffect(() => {
    fetchUsers();
  }, []);

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
      const res = await fetch(`http://localhost:8000/api/v1/users/${userId}`, {
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
      await fetch(`http://localhost:8000/api/v1/users/${id}`, { method: 'DELETE' });
    } catch (err) {
      console.error('Error deleting user on backend:', err);
    }
    setUsers(users.filter(u => u.id !== id));
  };

  const handleAdd = async () => {
    if ((newUser.firstName || newUser.email) && (newUser.id || newUser.firstName)) {
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
        const res = await fetch('http://localhost:8000/api/v1/users/', {
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
      setNewUser({ firstName: '', lastName: '', phoneNumber: '', email: '', role: 'Territory Executive', id: '', headquarters: 'Unassigned', depotName: 'Unassigned', reportingManager: 'Unassigned', isActive: true });
    }
  };

  const query = (searchQuery || '').toLowerCase().trim();
  const filteredUsers = users.filter(user => {
    if (!user) return false;
    const name = (user.name || '').toLowerCase();
    const id = (user.id || '').toLowerCase();
    const role = (user.role || '').toLowerCase();
    const phone = (user.phoneNumber || '').toLowerCase();
    const email = (user.email || '').toLowerCase();
    const manager = (user.reportingManager || '').toLowerCase();

    return name.includes(query) ||
           id.includes(query) ||
           role.includes(query) ||
           phone.includes(query) ||
           email.includes(query) ||
           manager.includes(query);
  });

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

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="mb-6 flex justify-between items-end shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">User Management</h1>
          <p className="text-slate-500 mt-1 text-sm font-medium">Manage employees, onboard new joiners, phone numbers, emails, and reporting managers.</p>
        </div>
        <div className="flex gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-3.5 h-3.5" />
            <input 
              type="text" 
              placeholder="Search by name, number, email..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-4 py-2 bg-white border border-slate-200 rounded text-xs font-bold text-slate-600 focus:outline-none focus:ring-2 focus:ring-[#004B87] w-72" 
            />
          </div>
          <button 
            onClick={() => setShowUpload(!showUpload)}
            className="flex items-center gap-2 px-3 py-1.5 border border-slate-200 text-xs font-bold text-slate-600 rounded bg-white hover:bg-slate-50"
          >
            <UploadCloud className="w-3.5 h-3.5" /> Bulk Upload
          </button>
          <button 
            onClick={() => setIsAdding(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-[#004B87] text-white text-xs font-bold rounded shadow-sm hover:bg-blue-800 transition-colors"
          >
            <UserPlus className="w-3.5 h-3.5" /> Add Employee
          </button>
        </div>
      </div>

      {showUpload && (
        <div className="mb-6 shrink-0">
          <FileUpload 
            title="Upload Headcount Roster"
            uploadEndpoint="http://localhost:8000/api/v1/users/upload-roster"
            onUploadComplete={() => fetchUsers()}
            instructions={[
              "Ensure the file contains: Full Name, Phone Number, Email, Role, Reporting Manager.",
              "Records are automatically mapped across users and reporting manager structures.",
              "Use the main view to manage individual records after upload."
            ]}
          />
        </div>
      )}

      {isAdding && (
        <div className="mb-6 bg-white p-4 rounded-xl shadow-sm border border-[#004B87]/40 ring-2 ring-[#004B87]/10 flex flex-col gap-4 shrink-0">
          <h3 className="font-bold text-slate-800 text-sm">Add New Employee</h3>
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-[140px] space-y-1">
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">First Name</label>
              <input 
                type="text" 
                value={newUser.firstName}
                onChange={(e) => setNewUser({...newUser, firstName: e.target.value})}
                placeholder="e.g. Manoj"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs font-bold text-slate-700 focus:outline-none focus:border-[#004B87]"
              />
            </div>
            <div className="flex-1 min-w-[140px] space-y-1">
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Last Name</label>
              <input 
                type="text" 
                value={newUser.lastName}
                onChange={(e) => setNewUser({...newUser, lastName: e.target.value})}
                placeholder="e.g. Tiwari"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs font-bold text-slate-700 focus:outline-none focus:border-[#004B87]"
              />
            </div>
            <div className="flex-1 min-w-[140px] space-y-1">
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Phone Number</label>
              <input 
                type="text" 
                value={newUser.phoneNumber}
                onChange={(e) => setNewUser({...newUser, phoneNumber: e.target.value})}
                placeholder="e.g. +91 9876543210"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs font-bold text-slate-700 focus:outline-none focus:border-[#004B87]"
              />
            </div>
            <div className="flex-1 min-w-[180px] space-y-1">
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Email</label>
              <input 
                type="email" 
                value={newUser.email}
                onChange={(e) => setNewUser({...newUser, email: e.target.value})}
                placeholder="e.g. manoj.tiwari@rll.com"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs font-bold text-slate-700 focus:outline-none focus:border-[#004B87]"
              />
            </div>
            <div className="flex-1 min-w-[160px] space-y-1">
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Role</label>
              <select 
                value={newUser.role}
                onChange={(e) => setNewUser({...newUser, role: e.target.value as any})}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs font-bold text-slate-700 focus:outline-none focus:border-[#004B87]"
              >
                <option value="ASE">ASE</option>
                <option value="TSM">TSM</option>
                <option value="Regional Supervisor">Regional Supervisor</option>
              </select>
            </div>
            <div className="flex-1 min-w-[160px] space-y-1">
              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Reporting Manager</label>
              <input 
                type="text" 
                value={newUser.reportingManager}
                onChange={(e) => setNewUser({...newUser, reportingManager: e.target.value})}
                placeholder="Manager Name"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs font-bold text-slate-700 focus:outline-none focus:border-[#004B87]"
              />
            </div>
            <div className="flex gap-2">
              <button 
                onClick={handleAdd}
                className="px-4 py-2 bg-[#004B87] text-white rounded text-xs font-bold hover:bg-blue-800 transition-colors"
              >
                Save
              </button>
              <button 
                onClick={() => setIsAdding(false)}
                className="px-4 py-2 border border-slate-200 text-slate-600 rounded text-xs font-bold hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 flex-1 overflow-hidden flex flex-col">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Name</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Phone Number</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Email</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Role</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Reporting Manager</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Status</th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                    {loading ? (
                      <span className="inline-flex items-center gap-2 text-slate-600 font-semibold">
                        <RefreshCw className="w-4 h-4 animate-spin text-[#004B87]" /> Loading personnel from database...
                      </span>
                    ) : searchQuery ? (
                      "No records found matching your search query."
                    ) : (
                      "No Data Found."
                    )}
                  </td>
                </tr>
              ) : (
                filteredUsers.map(user => (
                  <tr key={user.id} className="hover:bg-slate-50/50 transition-colors group">
                    {/* Name */}
                    <td className="px-6 py-4">
                      {editingId === user.id ? (
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                        />
                      ) : (
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-[#004B87]/10 flex items-center justify-center text-[#004B87] font-bold text-xs">
                            {user.name.charAt(0)}
                          </div>
                          <div>
                            <p className="font-bold text-slate-800 text-sm">{user.name}</p>
                          </div>
                        </div>
                      )}
                    </td>

                    {/* Phone Number */}
                    <td className="px-6 py-4">
                      {editingId === user.id ? (
                        <input
                          type="text"
                          value={editPhone}
                          onChange={(e) => setEditPhone(e.target.value)}
                          className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                        />
                      ) : (
                        <div className="flex items-center gap-2 text-slate-600">
                          <Phone className="w-3.5 h-3.5 text-slate-400" />
                          <span className="text-xs font-bold">{user.phoneNumber || 'N/A'}</span>
                        </div>
                      )}
                    </td>

                    {/* Email */}
                    <td className="px-6 py-4">
                      {editingId === user.id ? (
                        <input
                          type="email"
                          value={editEmail}
                          onChange={(e) => setEditEmail(e.target.value)}
                          className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                        />
                      ) : (
                        <div className="flex items-center gap-2 text-slate-600">
                          <Mail className="w-3.5 h-3.5 text-slate-400" />
                          <span className="text-xs font-semibold">{user.email || 'N/A'}</span>
                        </div>
                      )}
                    </td>

                    {/* Role */}
                    <td className="px-6 py-4">
                      {editingId === user.id ? (
                        <select
                          value={editRole}
                          onChange={(e) => setEditRole(e.target.value as any)}
                          className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                        >
                          <option value="ASE">ASE</option>
                          <option value="TSM">TSM</option>
                          <option value="Regional Supervisor">Regional Supervisor</option>
                        </select>
                      ) : (
                        <span className={`px-2.5 py-1 rounded border text-[10px] font-bold uppercase tracking-wider ${getRoleColor(user.role)}`}>
                          {user.role}
                        </span>
                      )}
                    </td>

                    {/* Reporting Manager */}
                    <td className="px-6 py-4">
                      {editingId === user.id ? (
                        <input
                          type="text"
                          value={editReportingManager}
                          onChange={(e) => setEditReportingManager(e.target.value)}
                          className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                        />
                      ) : (
                        <p className={`text-xs font-bold ${!user.reportingManager || user.reportingManager === "Unassigned" ? "text-slate-400 italic" : "text-slate-700"}`}>
                          {user.reportingManager || "Unassigned"}
                        </p>
                      )}
                    </td>

                    {/* Status */}
                    <td className="px-6 py-4">
                      {editingId === user.id ? (
                        <select
                          value={editIsActive ? "active" : "inactive"}
                          onChange={(e) => setEditIsActive(e.target.value === "active")}
                          className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
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
                    <td className="px-6 py-4 text-right">
                      {editingId === user.id ? (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleSave(user.id)}
                            className="p-1.5 bg-emerald-50 text-emerald-600 rounded hover:bg-emerald-100 transition-colors"
                            title="Save Changes"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            onClick={handleCancel}
                            className="p-1.5 bg-slate-100 text-slate-600 rounded hover:bg-slate-200 transition-colors"
                            title="Cancel"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleEditClick(user)}
                            className="px-3 py-1.5 border border-slate-200 rounded text-[10px] font-bold text-slate-600 hover:border-[#004B87] hover:text-[#004B87] transition-colors uppercase tracking-widest inline-flex items-center gap-1"
                          >
                            <Edit2 className="w-3 h-3" /> Edit
                          </button>
                          <button 
                            onClick={() => handleDelete(user.id)}
                            className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors inline-flex"
                            title="Delete Record"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="mt-auto p-4 bg-slate-50 border-t border-slate-200 text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center justify-between">
          <span>Showing {filteredUsers.length} total employees</span>
        </div>
      </div>
    </div>
  );
}
