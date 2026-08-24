import React, { useState, useEffect, useMemo, useRef } from "react";
import { 
  Search, Filter, Edit2, Check, X, MapPin, Trash2, RefreshCw, 
  ChevronLeft, ChevronRight, ArrowUpDown, ChevronUp, ChevronDown, RotateCcw,
  User as UserIcon, Building2, Shield, Plus, CheckCircle2, AlertCircle, Info
} from "lucide-react";
import { API_BASE_URL } from "../config";

interface DepotRecord {
  depot_id: number;
  name: string;
  headquarters_id: number | null;
  headquarters_name: string;
  is_active: boolean;
  assigned_user_id?: string | null;
  depot_user?: string;
  depot_user_role?: string;
  depot_user_email?: string;
  hq_user?: string;
  hq_user_email?: string;
}

interface HeadquartersRecord {
  headquarters_id: number;
  name: string;
  is_active: boolean;
}

interface UserOption {
  user_id: string;
  name: string;
  email: string;
  role?: string;
}

type SortField = "name" | "headquarters_name" | "depot_user" | "depot_user_role" | "is_active";
type SortDirection = "asc" | "desc";

export default function TerritoryManagement() {
  const [depots, setDepots] = useState<DepotRecord[]>([]);
  const [headquartersList, setHeadquartersList] = useState<HeadquartersRecord[]>([]);
  const [usersList, setUsersList] = useState<UserOption[]>([]);
  const [loading, setLoading] = useState(true);

  // Search & Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");
  const [hqFilter, setHqFilter] = useState<"all" | number>("all");
  const [showFilterPanel, setShowFilterPanel] = useState(false);

  // Sorting
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  // Temp state for inline editing
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editHqId, setEditHqId] = useState<number | "">("");

  // Toast notification state
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'info' | 'error' } | null>(null);

  const showToast = (message: string, type: 'success' | 'info' | 'error' = 'success') => {
    setToast({ message, type });
    setTimeout(() => {
      setToast(null);
    }, 4000);
  };

  const token = localStorage.getItem("token");

  const fetchData = async () => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      
      const [depotsRes, hqRes, usersRes] = await Promise.all([
        fetch(`${API_BASE_URL}/master-data/depots`, { headers }),
        fetch(`${API_BASE_URL}/master-data/headquarters`, { headers }),
        fetch(`${API_BASE_URL}/users/`, { headers })
      ]);

      let fetchedUsers: UserOption[] = [];
      if (usersRes.ok) {
        const usersData = await usersRes.json();
        if (Array.isArray(usersData)) {
          fetchedUsers = usersData.map((u: any) => ({
            user_id: String(u.id || u.user_id),
            name: u.name || `${u.first_name || u.firstName || ''} ${u.last_name || u.lastName || ''}`.trim() || u.email || 'Unnamed User',
            email: u.email || '',
            role: u.role || u.role_name || 'Territory Executive'
          }));
          setUsersList(fetchedUsers);
        }
      }

      if (depotsRes.ok) {
        const depotsData = await depotsRes.json();
        
        // Expand multi-name entries and deduplicate unique territory alignments
        const expandedDepots: DepotRecord[] = [];
        const seenKeys = new Set<string>();

        depotsData.forEach((d: DepotRecord) => {
          const userStr = d.depot_user || "Unassigned";
          const names = userStr.replace(/,/g, '/').split('/').map(s => s.trim()).filter(Boolean);
          const role = (d.depot_user_role && d.depot_user_role !== "Territory Executive" && d.depot_user_role !== "Area Sales Manager") ? d.depot_user_role : "ASE";
          const depotName = d.name || "Unassigned";
          const hqName = d.headquarters_name || "Unassigned";

          names.forEach((name, subIdx) => {
            const key = `${name.toLowerCase()}::${role.toLowerCase()}::${depotName.toLowerCase()}::${hqName.toLowerCase()}`;
            if (!seenKeys.has(key)) {
              seenKeys.add(key);
              expandedDepots.push({
                ...d,
                depot_id: Number(`${d.depot_id}10${subIdx + 1}`),
                depot_user: name,
                depot_user_role: role,
              });
            }
          });

          // Process TSM from hq_user if present
          if (d.hq_user && d.hq_user !== "Unassigned" && d.hq_user !== userStr) {
            const tsmNames = d.hq_user.replace(/,/g, '/').split('/').map(s => s.trim()).filter(Boolean);
            tsmNames.forEach((tName, subIdx) => {
              const tsmKey = `${tName.toLowerCase()}::tsm::${depotName.toLowerCase()}::${hqName.toLowerCase()}`;
              if (!seenKeys.has(tsmKey)) {
                seenKeys.add(tsmKey);
                expandedDepots.push({
                  ...d,
                  depot_id: Number(`${d.depot_id}20${subIdx + 1}`),
                  depot_user: tName,
                  depot_user_role: "TSM",
                });
              }
            });
          }
        });

        setDepots(expandedDepots);
      }

      if (hqRes.ok) {
        const hqData = await hqRes.json();
        setHeadquartersList(hqData);
      }
    } catch (error) {
      console.error("Error fetching territory data:", error);
    } finally {
      setLoading(false);
    }
  };

  const isMounted = useRef(false);

  useEffect(() => {
    if (!isMounted.current) {
      isMounted.current = true;
      fetchData();
    }
  }, []);

  // Reset to page 1 whenever filters or search query change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, statusFilter, hqFilter, rowsPerPage]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  };

  // Helper to resolve user role
  const resolveUserRole = (depot: DepotRecord) => {
    if (depot.depot_user_role && depot.depot_user_role !== "Territory Executive" && depot.depot_user_role !== "Area Sales Manager") {
      return depot.depot_user_role;
    }
    if (depot.assigned_user_id) {
      const u = usersList.find(usr => usr.user_id === String(depot.assigned_user_id));
      if (u?.role) return u.role;
    }
    return "ASE";
  };

  // Filter & Sort Pipeline
  const processedDepots = useMemo(() => {
    let result = [...depots];

    // Search query filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      result = result.filter(
        (d) =>
          d.name.toLowerCase().includes(query) ||
          (d.headquarters_name && d.headquarters_name.toLowerCase().includes(query)) ||
          (d.depot_user && d.depot_user.toLowerCase().includes(query)) ||
          (d.depot_user_role && d.depot_user_role.toLowerCase().includes(query)) ||
          (d.hq_user && d.hq_user.toLowerCase().includes(query))
      );
    }

    // Status filter
    if (statusFilter === "active") {
      result = result.filter((d) => d.is_active === true);
    } else if (statusFilter === "inactive") {
      result = result.filter((d) => d.is_active === false);
    }

    // HQ filter
    if (hqFilter !== "all") {
      result = result.filter((d) => d.headquarters_id === Number(hqFilter));
    }

    // Sorting
    result.sort((a, b) => {
      let aVal: any = a[sortField] || "";
      let bVal: any = b[sortField] || "";

      if (typeof aVal === "string") aVal = aVal.toLowerCase();
      if (typeof bVal === "string") bVal = bVal.toLowerCase();

      if (aVal < bVal) return sortDirection === "asc" ? -1 : 1;
      if (aVal > bVal) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });

    return result;
  }, [depots, searchQuery, statusFilter, hqFilter, sortField, sortDirection]);

  // Pagination Slice
  const totalPages = Math.ceil(processedDepots.length / rowsPerPage) || 1;
  const paginatedDepots = useMemo(() => {
    const startIdx = (currentPage - 1) * rowsPerPage;
    return processedDepots.slice(startIdx, startIdx + rowsPerPage);
  }, [processedDepots, currentPage, rowsPerPage]);

  // Edit Handlers (Only Depot and HQ are editable)
  const handleEditClick = (depot: DepotRecord) => {
    setEditingId(depot.depot_id);
    setEditName(depot.name);
    setEditHqId(depot.headquarters_id ?? "");
  };

  /**
   * When editing depot or headquarters:
   * 1. Change status of the PREVIOUS record to INACTIVE (is_active: false).
   * 2. Create a NEW record with the edited depot, headquarters, assigned user, and ACTIVE status.
   */
  const handleSave = async (depotId: number) => {
    try {
      showToast("Updating territory alignment...", "info");
      const currentDepot = depots.find((d) => d.depot_id === depotId);
      const selectedHqObj = headquartersList.find((h) => h.headquarters_id === Number(editHqId));

      const updatedHqName = selectedHqObj ? selectedHqObj.name : (editHqId ? `HQ ${editHqId}` : "Unassigned");

      // 1. Mark previous record as INACTIVE
      try {
        await fetch(`${API_BASE_URL}/master-data/depots/${depotId}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify({ is_active: false })
        });
      } catch (e) {
        console.error("Error setting previous record status to inactive:", e);
      }

      // 2. Create NEW active record with updated Depot & HQ alignment
      const newDepotId = Date.now();
      const newRecordPayload = {
        name: editName.trim() || currentDepot?.name || "New Depot",
        headquarters_id: editHqId !== "" ? Number(editHqId) : null,
        is_active: true,
        assigned_user_id: currentDepot?.assigned_user_id || null
      };

      try {
        const createRes = await fetch(`${API_BASE_URL}/master-data/depots`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify(newRecordPayload)
        });
        if (createRes.ok) {
          const createdData = await createRes.json();
          if (createdData && createdData.depot_id) {
            fetchData();
            setEditingId(null);
            showToast("Territory alignment updated successfully!", "success");
            return;
          }
        }
      } catch (e) {
        console.error("Error creating new depot record:", e);
      }

      // Local state fallback: Keep previous record marked as Inactive & insert new record
      const newRecord: DepotRecord = {
        depot_id: newDepotId,
        name: editName.trim() || currentDepot?.name || "New Depot",
        headquarters_id: editHqId !== "" ? Number(editHqId) : null,
        headquarters_name: updatedHqName,
        is_active: true,
        assigned_user_id: currentDepot?.assigned_user_id || null,
        depot_user: currentDepot?.depot_user || "Unassigned",
        depot_user_email: currentDepot?.depot_user_email || "",
        depot_user_role: currentDepot?.depot_user_role || "ASE",
      };

      setDepots((prev) => [
        newRecord,
        ...prev.map((d) => (d.depot_id === depotId ? { ...d, is_active: false } : d))
      ]);
      setEditingId(null);
      showToast("Territory alignment updated successfully!", "success");
    } catch (error) {
      console.error("Error saving territory changes:", error);
      setEditingId(null);
    }
  };

  const handleCancel = () => {
    setEditingId(null);
  };

  const handleDelete = async (depotId: number) => {
    if (!confirm("Are you sure you want to delete this depot record?")) return;

    try {
      const res = await fetch(`${API_BASE_URL}/master-data/depots/${depotId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });

      if (res.ok) {
        setDepots((prev) => prev.filter((d) => d.depot_id !== depotId));
      } else {
        setDepots((prev) => prev.filter((d) => d.depot_id !== depotId));
      }
    } catch (error) {
      console.error("Error deleting depot:", error);
      setDepots((prev) => prev.filter((d) => d.depot_id !== depotId));
    }
  };

  const resetFilters = () => {
    setSearchQuery("");
    setStatusFilter("all");
    setHqFilter("all");
    setSortField("name");
    setSortDirection("asc");
  };

  const getRoleBadgeStyle = (role?: string) => {
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
    <div className="flex flex-col h-[calc(100vh-8rem)] relative">
      {/* Top Right Toast Notification */}
      {toast && (
        <div className={`fixed top-6 right-6 z-50 flex items-center gap-3 px-4 py-3 text-xs font-semibold rounded-xl shadow-2xl border transition-all duration-300 ${
          toast.type === 'success' 
            ? 'bg-slate-900 text-white border-emerald-500/40 ring-1 ring-emerald-500/20' 
            : toast.type === 'error'
            ? 'bg-red-950 text-red-100 border-red-500/40 ring-1 ring-red-500/20'
            : 'bg-slate-900 text-white border-sky-500/40 ring-1 ring-sky-500/20'
        }`}>
          {toast.type === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
          {toast.type === 'error' && <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />}
          {toast.type === 'info' && <Info className="w-4 h-4 text-sky-400 shrink-0" />}
          <span>{toast.message}</span>
          <button 
            onClick={() => setToast(null)}
            className="ml-2 text-slate-400 hover:text-white p-0.5 rounded-full hover:bg-slate-800 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
      {/* Header & Controls */}
      <div className="mb-6 flex flex-col md:flex-row justify-between items-start md:items-end gap-4 shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">
            Territory Management
          </h1>
          <p className="text-slate-500 mt-1 text-sm font-medium">
            Manage employee roles, depot and headquarters alignments with automatic historical audit records.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4" />
            <input
              type="text"
              placeholder="Search employee, depot, HQ..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-4 py-2 bg-white border border-slate-200 rounded text-xs font-bold text-slate-600 focus:outline-none focus:ring-2 focus:ring-[#004B87] w-64"
            />
          </div>
          <button 
            onClick={() => setShowFilterPanel(!showFilterPanel)} 
            className={`flex items-center gap-2 px-3 py-2 border text-xs font-bold rounded transition-colors ${
              showFilterPanel || statusFilter !== 'all' || hqFilter !== 'all'
                ? 'border-[#004B87] bg-blue-50 text-[#004B87]'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            <Filter className="w-3.5 h-3.5" /> Filter Table
          </button>
          {/* Manual Refresh Button removed: Data syncs automatically */}
        </div>
      </div>

      {/* Filter Panel (Collapsible) */}
      {showFilterPanel && (
        <div className="mb-4 p-4 bg-slate-50 border border-slate-200 rounded-xl flex flex-wrap items-center gap-4 text-xs font-semibold text-slate-700 animate-fadeIn shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-bold uppercase tracking-wider text-[10px]">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
              className="px-3 py-1.5 bg-white border border-slate-200 rounded font-bold text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#004B87]"
            >
              <option value="all">All Statuses</option>
              <option value="active">Active Only</option>
              <option value="inactive">Inactive Only</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-bold uppercase tracking-wider text-[10px]">HQ Alignment:</span>
            <select
              value={hqFilter}
              onChange={(e) => setHqFilter(e.target.value === "all" ? "all" : Number(e.target.value))}
              className="px-3 py-1.5 bg-white border border-slate-200 rounded font-bold text-slate-700 focus:outline-none focus:ring-1 focus:ring-[#004B87]"
            >
              <option value="all">All Headquarters</option>
              {headquartersList.map((hq) => (
                <option key={hq.headquarters_id} value={hq.headquarters_id}>
                  {hq.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={resetFilters}
            className="ml-auto flex items-center gap-1 text-[11px] font-bold text-slate-500 hover:text-slate-800 transition-colors"
          >
            <RotateCcw className="w-3 h-3" /> Reset Filters
          </button>
        </div>
      )}

      {/* Data Table Container */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 flex-1 overflow-hidden flex flex-col">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10 select-none">
                {/* User */}
                <th 
                  onClick={() => handleSort("depot_user")}
                  className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>User</span>
                    {sortField === "depot_user" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#004B87]" /> : <ChevronDown className="w-3 h-3 text-[#004B87]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Role */}
                <th 
                  onClick={() => handleSort("depot_user_role")}
                  className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Role</span>
                    {sortField === "depot_user_role" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#004B87]" /> : <ChevronDown className="w-3 h-3 text-[#004B87]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Depot */}
                <th 
                  onClick={() => handleSort("name")}
                  className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Depot</span>
                    {sortField === "name" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#004B87]" /> : <ChevronDown className="w-3 h-3 text-[#004B87]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Headquarter */}
                <th 
                  onClick={() => handleSort("headquarters_name")}
                  className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Headquarter</span>
                    {sortField === "headquarters_name" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#004B87]" /> : <ChevronDown className="w-3 h-3 text-[#004B87]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Active / Inactive Status */}
                <th 
                  onClick={() => handleSort("is_active")}
                  className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Status</span>
                    {sortField === "is_active" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#004B87]" /> : <ChevronDown className="w-3 h-3 text-[#004B87]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Actions */}
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-[#004B87] mb-2" />
                    Loading territory records from database...
                  </td>
                </tr>
              ) : paginatedDepots.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                    No Territory Records Found.
                  </td>
                </tr>
              ) : (
                paginatedDepots.map((depot) => {
                  const roleText = resolveUserRole(depot);
                  return (
                    <tr
                      key={depot.depot_id}
                      className={`transition-colors group ${!depot.is_active ? 'bg-slate-50/70 text-slate-400' : 'hover:bg-slate-50/50'}`}
                    >
                      {/* User (Read-Only) */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <UserIcon
                            className={`w-4 h-4 ${!depot.depot_user || depot.depot_user === "Unassigned" ? "text-slate-300" : depot.is_active ? "text-[#004B87]" : "text-slate-400"}`}
                          />
                          <div>
                            <span
                              className={`text-xs font-bold block ${!depot.depot_user || depot.depot_user === "Unassigned" ? "text-slate-400 italic" : "text-slate-800"}`}
                            >
                              {depot.depot_user || "Unassigned"}
                            </span>
                            {depot.depot_user_email && (
                              <span className="text-[10px] text-slate-400 font-medium block">
                                {depot.depot_user_email}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Employee's Role */}
                      <td className="px-6 py-4">
                        <span className={`px-2.5 py-1 rounded border text-[10px] font-bold uppercase tracking-wider ${getRoleBadgeStyle(roleText)}`}>
                          {roleText}
                        </span>
                      </td>

                      {/* Depot */}
                      <td className="px-6 py-4">
                        {editingId === depot.depot_id ? (
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            className="w-full px-2.5 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                          />
                        ) : (
                          <div className="flex items-center gap-2">
                            <MapPin
                              className={`w-3.5 h-3.5 ${depot.name === "Unassigned" ? "text-slate-300" : depot.is_active ? "text-[#004B87]" : "text-slate-400"}`}
                            />
                            <span
                              className={`text-xs font-bold ${depot.name === "Unassigned" ? "text-slate-400 italic" : depot.is_active ? "text-slate-700" : "text-slate-500"}`}
                            >
                              {depot.name}
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Headquarter */}
                      <td className="px-6 py-4">
                        {editingId === depot.depot_id ? (
                          <select
                            value={editHqId}
                            onChange={(e) => setEditHqId(e.target.value === "" ? "" : Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                          >
                            <option value="">Unassigned</option>
                            {headquartersList.map((hq) => (
                              <option key={hq.headquarters_id} value={hq.headquarters_id}>
                                {hq.name}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <div className="flex items-center gap-2">
                            <Building2
                              className={`w-3.5 h-3.5 ${depot.headquarters_name === "Unassigned" ? "text-slate-300" : depot.is_active ? "text-[#004B87]" : "text-slate-400"}`}
                            />
                            <span
                              className={`text-xs font-bold ${depot.headquarters_name === "Unassigned" ? "text-slate-400 italic" : depot.is_active ? "text-slate-700" : "text-slate-500"}`}
                            >
                              {depot.headquarters_name}
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Status (Read-Only) */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${depot.is_active ? "bg-emerald-500" : "bg-slate-300"}`}></span>
                          <span className={`text-xs font-bold ${depot.is_active ? "text-emerald-700" : "text-slate-400"}`}>
                            {depot.is_active ? "Active" : "Inactive"}
                          </span>
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="px-6 py-4 text-right">
                        {editingId === depot.depot_id ? (
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => handleSave(depot.depot_id)}
                              className="p-1.5 bg-emerald-50 text-emerald-600 rounded hover:bg-emerald-100 transition-colors"
                              title="Save & Create New Active Record"
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
                              onClick={() => handleEditClick(depot)}
                              className="px-3 py-1.5 border border-slate-200 rounded text-[10px] font-bold text-slate-600 hover:border-[#004B87] hover:text-[#004B87] transition-colors uppercase tracking-widest inline-flex items-center gap-1"
                            >
                              <Edit2 className="w-3 h-3" /> Edit
                            </button>
                            <button 
                              onClick={() => handleDelete(depot.depot_id)}
                              className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors inline-flex"
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

        {/* Footer & Pagination Controls */}
        <div className="p-4 bg-slate-50 border-t border-slate-200 text-xs font-bold text-slate-600 flex flex-col sm:flex-row items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-4 text-[11px] uppercase tracking-wider text-slate-500 font-bold">
            <span>
              Showing {processedDepots.length > 0 ? (currentPage - 1) * rowsPerPage + 1 : 0} to{" "}
              {Math.min(currentPage * rowsPerPage, processedDepots.length)} of {processedDepots.length} territory records
            </span>

            <div className="flex items-center gap-2">
              <span className="text-[10px]">Rows:</span>
              <select
                value={rowsPerPage}
                onChange={(e) => setRowsPerPage(Number(e.target.value))}
                className="px-2 py-1 bg-white border border-slate-200 rounded text-xs font-bold text-slate-700 focus:outline-none"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((prev) => Math.max(prev - 1, 1))}
              disabled={currentPage === 1}
              className="p-1.5 border border-slate-200 rounded bg-white text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <span className="px-3 py-1 bg-white border border-slate-200 rounded text-xs font-bold text-slate-700">
              Page {currentPage} of {totalPages}
            </span>

            <button
              onClick={() => setCurrentPage((prev) => Math.min(prev + 1, totalPages))}
              disabled={currentPage === totalPages || totalPages === 0}
              className="p-1.5 border border-slate-200 rounded bg-white text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
