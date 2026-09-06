import React, { useState, useEffect } from 'react';
import { Shield, Plus, Trash2, CheckCircle, XCircle } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { useToast } from '../contexts/ToastContext';

interface Role {
  role_id: string;
  role_name: string;
  description: string;
  is_active: boolean;
}

export default function RoleManagement() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newRoleName, setNewRoleName] = useState('');
  const [newRoleDesc, setNewRoleDesc] = useState('');
  const { showToast } = useToast();

  useEffect(() => {
    fetchRoles();
  }, []);

  const fetchRoles = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/users/roles`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (res.ok) {
        const data = await res.json();
        setRoles(data);
      }
    } catch (e) {
      console.error('Error fetching roles:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleActive = async (role: Role) => {
    // Optimistic Update
    const previousStatus = role.is_active;
    setRoles(roles.map(r => r.role_id === role.role_id ? { ...r, is_active: !r.is_active } : r));
    
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/users/roles/${role.role_id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ is_active: !previousStatus }),
      });
      if (res.ok) {
        showToast('Role status updated successfully.', 'success');
      } else {
        throw new Error('Failed to update role status');
      }
    } catch (e) {
      console.error('Error updating role:', e);
      // Revert on failure
      setRoles(roles.map(r => r.role_id === role.role_id ? { ...r, is_active: previousStatus } : r));
      showToast('Failed to update role status.', 'error');
    }
  };

  const handleDelete = async (roleId: string) => {
    if (!confirm('Are you sure you want to delete this role?')) return;
    
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/users/roles/${roleId}`, {
        method: 'DELETE',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (res.ok) {
        setRoles(roles.filter(r => r.role_id !== roleId));
        showToast('Role deleted successfully.', 'success');
      } else {
        throw new Error('Failed to delete role');
      }
    } catch (e) {
      console.error('Error deleting role:', e);
      showToast('Failed to delete role.', 'error');
    }
  };

  const handleCreateRole = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE_URL}/users/roles`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          role_name: newRoleName,
          description: newRoleDesc,
          is_active: true
        })
      });

      if (res.ok) {
        const newRole = await res.json();
        setRoles([...roles, newRole]);
        setShowAddModal(false);
        setNewRoleName('');
        setNewRoleDesc('');
        showToast('Role created successfully.', 'success');
      } else {
        const errData = await res.json().catch(() => ({}));
        showToast(errData.detail || 'Failed to create role.', 'error');
      }
    } catch (e) {
      console.error('Error creating role:', e);
      showToast('Network error creating role.', 'error');
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <div className="flex items-center justify-between bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 bg-[#0D3B8E]/10 text-[#0D3B8E] rounded-xl flex items-center justify-center font-bold">
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">Role Management</h2>
            <p className="text-xs text-slate-500">
              Manage system roles, permissions, and active status.
            </p>
          </div>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="bg-[#0D3B8E] hover:bg-blue-800 text-white px-4 py-2 rounded-lg font-medium flex items-center gap-2 transition-colors text-sm shadow-sm"
        >
          <Plus className="h-4 w-4" />
          Add Role
        </button>
      </div>

      <div className="bg-white rounded-2xl shadow-xs border border-slate-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading roles...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse table-fixed">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200/80">
                  <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest w-1/4">Role Name</th>
                  <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest w-1/2">Description</th>
                  <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest w-24 text-center">Status</th>
                  <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest w-24 text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {roles.map((role) => (
                  <tr key={role.role_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-bold text-slate-700 text-sm">{role.role_name}</div>
                    </td>
                    <td className="px-6 py-4 text-xs font-semibold text-slate-500">
                      {role.description}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button
                        type="button"
                        onClick={() => handleToggleActive(role)}
                        className="flex items-center justify-center w-full focus:outline-none"
                      >
                        <div
                          className={`relative inline-flex h-6 w-12 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                            role.is_active ? 'bg-emerald-500' : 'bg-slate-300'
                          }`}
                        >
                          <span
                            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                              role.is_active ? 'translate-x-6' : 'translate-x-0'
                            }`}
                          />
                        </div>
                      </button>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button
                        onClick={() => handleDelete(role.role_id)}
                        className="p-2 text-slate-400 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50 inline-flex items-center justify-center"
                        title="Delete Role"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {roles.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-6 py-8 text-center text-slate-500 text-sm">
                      No roles found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center">
              <h3 className="text-lg font-bold text-slate-900">Add New Role</h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <XCircle className="h-6 w-6" />
              </button>
            </div>
            
            <form onSubmit={handleCreateRole} className="p-6">
              
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Role Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={newRoleName}
                    onChange={(e) => setNewRoleName(e.target.value)}
                    className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0D3B8E] focus:border-[#0D3B8E] bg-white text-slate-900 text-sm font-semibold"
                    placeholder="e.g., Super Admin"
                  />
                </div>
                
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={newRoleDesc}
                    onChange={(e) => setNewRoleDesc(e.target.value)}
                    className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-[#0D3B8E] focus:border-[#0D3B8E] bg-white text-slate-900 text-sm font-semibold"
                    placeholder="Brief description of the role's permissions"
                    rows={3}
                  />
                </div>
              </div>
              
              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-slate-700 hover:bg-slate-100 rounded-lg font-semibold transition-colors text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-[#0D3B8E] hover:bg-blue-800 text-white rounded-lg font-semibold transition-colors text-sm shadow-sm"
                >
                  Create Role
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
