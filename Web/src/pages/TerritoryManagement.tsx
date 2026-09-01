import React, { useState, useEffect, useMemo, useRef } from "react";
import { API_BASE_URL } from "../lib/api";
import { 
  Search, Filter, Edit2, Check, X, MapPin, Trash2, RefreshCw, 
  ChevronLeft, ChevronRight, ArrowUpDown, ChevronUp, ChevronDown, RotateCcw,
  User as UserIcon, Building2, Shield, Plus, CheckCircle2, AlertCircle, Info
} from "lucide-react";

interface DepotRecord {
  depot_id: string | number;
  real_depot_id?: string | number;
  name: string;
  headquarters_id: string | number | null;
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
  headquarters_id: string | number;
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
  const [masterDepotsList, setMasterDepotsList] = useState<{ depot_id: string | number; name: string; headquarters_id?: string | number | null }[]>([]);
  const [loading, setLoading] = useState(true);

  // Search & Filters (Always Visible)
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");
  const [hqFilter, setHqFilter] = useState<"all" | string | number>("all");
  const [depotFilter, setDepotFilter] = useState<string>("all");

  // Sorting
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  // Temp state for inline editing
  const [editingId, setEditingId] = useState<string | number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDepotId, setEditDepotId] = useState<string | number | "">("");
  const [editHqId, setEditHqId] = useState<string | number | "">("");
  const [editUserId, setEditUserId] = useState<string>("");
  const [editIsActive, setEditIsActive] = useState<boolean>(true);

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

        // Extract master list of unique depots for editing dropdown & filtering
        const uniqueDepotMap = new Map<string, { depot_id: string | number; name: string; headquarters_id?: string | number | null }>();
        depotsData.forEach((d: any) => {
          if (d.name && d.name !== "Unassigned") {
            const key = String(d.name).trim().toLowerCase();
            if (!uniqueDepotMap.has(key)) {
              uniqueDepotMap.set(key, {
                depot_id: d.depot_id,
                name: d.name,
                headquarters_id: d.headquarters_id || null
              });
            }
          }
        });
        setMasterDepotsList(Array.from(uniqueDepotMap.values()).sort((a, b) => a.name.localeCompare(b.name)));

        // Expand multi-name entries and deduplicate unique territory alignments
        const expandedDepots: DepotRecord[] = [];
        const seenKeys = new Set<string>();

        depotsData.forEach((d: DepotRecord, recordIdx: number) => {
          const userStr = d.depot_user || "Unassigned";
          const names = userStr.replace(/,/g, '/').split('/').map(s => s.trim()).filter(Boolean);
          const role = (d.depot_user_role && d.depot_user_role !== "Territory Executive" && d.depot_user_role !== "Area Sales Manager") ? d.depot_user_role : "ASE";
          const depotName = d.name || "Unassigned";
          const hqName = d.headquarters_name || "Unassigned";
          const baseDepotId = d.depot_id;

          if (names.length === 0) {
            const key = `unassigned::${role.toLowerCase()}::${depotName.toLowerCase()}::${hqName.toLowerCase()}::${recordIdx}`;
            seenKeys.add(key);
            expandedDepots.push({
              ...d,
              depot_id: `${baseDepotId}_rec${recordIdx}`,
              real_depot_id: baseDepotId,
              depot_user: "Unassigned",
              depot_user_role: role,
            });
          } else {
            names.forEach((name, subIdx) => {
              const key = `${name.toLowerCase()}::${role.toLowerCase()}::${depotName.toLowerCase()}::${hqName.toLowerCase()}`;
              if (!seenKeys.has(key)) {
                seenKeys.add(key);
                expandedDepots.push({
                  ...d,
                  depot_id: `${baseDepotId}_rec${recordIdx}_${subIdx}`,
                  real_depot_id: baseDepotId,
                  depot_user: name,
                  depot_user_role: role,
                });
              }
            });
          }

          // Process TSM from hq_user if present
          if (d.hq_user && d.hq_user !== "Unassigned" && d.hq_user !== userStr) {
            const tsmNames = d.hq_user.replace(/,/g, '/').split('/').map(s => s.trim()).filter(Boolean);
            tsmNames.forEach((tName, subIdx) => {
              const tsmKey = `${tName.toLowerCase()}::tsm::${depotName.toLowerCase()}::${hqName.toLowerCase()}`;
              if (!seenKeys.has(tsmKey)) {
                seenKeys.add(tsmKey);
                expandedDepots.push({
                  ...d,
                  depot_id: `${baseDepotId}_tsm_rec${recordIdx}_${subIdx}`,
                  real_depot_id: baseDepotId,
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
  }, [searchQuery, statusFilter, hqFilter, depotFilter, rowsPerPage]);

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
      const u = usersList.find(usr => String(usr.user_id) === String(depot.assigned_user_id));
      if (u?.role) return u.role;
    }
    return "ASE";
  };

  // Filter & Sort Pipeline
  const processedDepots = useMemo(() => {
    let result = depots.filter((d) => {
      // Always retain row currently being edited so editing controls never disappear mid-edit
      if (editingId !== null && String(d.depot_id) === String(editingId)) {
        return true;
      }

      // Search query filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const matches =
          (d.name || "").toLowerCase().includes(query) ||
          (d.headquarters_name && d.headquarters_name.toLowerCase().includes(query)) ||
          (d.depot_user && d.depot_user.toLowerCase().includes(query)) ||
          (d.depot_user_role && d.depot_user_role.toLowerCase().includes(query)) ||
          (d.hq_user && d.hq_user.toLowerCase().includes(query));
        if (!matches) return false;
      }

      // Status filter
      if (statusFilter === "active" && d.is_active !== true) return false;
      if (statusFilter === "inactive" && d.is_active !== false) return false;

      // HQ filter
      if (hqFilter !== "all" && String(d.headquarters_id) !== String(hqFilter)) return false;

      // Depot filter
      if (depotFilter !== "all") {
        const matchesDepot = d.name === depotFilter || String(d.depot_id) === String(depotFilter) || String(d.real_depot_id) === String(depotFilter);
        if (!matchesDepot) return false;
      }

      return true;
    });

    // Sorting
    result.sort((a, b) => {
      let aVal: any = "";
      let bVal: any = "";

      if (sortField === "depot_user_role") {
        aVal = resolveUserRole(a);
        bVal = resolveUserRole(b);
      } else if (sortField === "depot_user") {
        aVal = a.depot_user || "Unassigned";
        bVal = b.depot_user || "Unassigned";
      } else if (sortField === "is_active") {
        aVal = a.is_active ? 1 : 0;
        bVal = b.is_active ? 1 : 0;
      } else {
        aVal = a[sortField] || "";
        bVal = b[sortField] || "";
      }

      if (typeof aVal === "string") aVal = aVal.toLowerCase();
      if (typeof bVal === "string") bVal = bVal.toLowerCase();

      if (aVal < bVal) return sortDirection === "asc" ? -1 : 1;
      if (aVal > bVal) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });

    return result;
  }, [depots, searchQuery, statusFilter, hqFilter, depotFilter, sortField, sortDirection, editingId, usersList]);

  // Pagination Slice
  const totalPages = Math.ceil(processedDepots.length / rowsPerPage) || 1;
  const paginatedDepots = useMemo(() => {
    const startIdx = (currentPage - 1) * rowsPerPage;
    return processedDepots.slice(startIdx, startIdx + rowsPerPage);
  }, [processedDepots, currentPage, rowsPerPage]);

  // Inline Edit Handlers
  const handleEditClick = (depot: DepotRecord) => {
    setEditingId(depot.depot_id);
    setEditName(depot.name || "");
    setEditDepotId(depot.real_depot_id ? String(depot.real_depot_id) : String(depot.depot_id));
    setEditHqId(depot.headquarters_id ?? "");
    setEditUserId(depot.assigned_user_id ? String(depot.assigned_user_id) : "");
    setEditIsActive(depot.is_active ?? true);
  };

  const handleSave = async (depot: DepotRecord) => {
    try {
      showToast("Updating territory alignment...", "info");
      const targetDepotId = editDepotId || depot.real_depot_id || depot.depot_id;
      const selectedHqObj = headquartersList.find((h) => String(h.headquarters_id) === String(editHqId));
      const selectedUserObj = usersList.find((u) => String(u.user_id) === String(editUserId));

      const payload: any = {
        name: editName.trim() || depot.name,
        headquarters_id: editHqId !== "" ? editHqId : null,
        is_active: editIsActive,
        assigned_user_id: editUserId && editUserId !== "Unassigned" ? editUserId : null
      };

      const res = await fetch(`${API_BASE_URL}/master-data/depots/${targetDepotId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        showToast("Territory alignment updated successfully!", "success");
        await fetchData();
        setEditingId(null);
      } else {
        // Fallback local update
        setDepots((prev) =>
          prev.map((d) => {
            if (d.depot_id === depot.depot_id) {
              return {
                ...d,
                name: editName.trim() || d.name,
                headquarters_id: editHqId !== "" ? editHqId : null,
                headquarters_name: selectedHqObj ? selectedHqObj.name : "Unassigned",
                is_active: editIsActive,
                assigned_user_id: editUserId || null,
                depot_user: selectedUserObj ? selectedUserObj.name : "Unassigned",
                depot_user_email: selectedUserObj ? selectedUserObj.email : "",
                depot_user_role: selectedUserObj ? (selectedUserObj.role || "ASE") : "ASE"
              };
            }
            return d;
          })
        );
        setEditingId(null);
        showToast("Territory alignment updated!", "success");
      }
    } catch (error) {
      console.error("Error saving territory changes:", error);
      showToast("Failed to save territory changes", "error");
      setEditingId(null);
    }
  };

  const handleCancel = () => {
    setEditingId(null);
  };

  const handleDelete = async (depotId: string | number) => {
    if (!confirm("Are you sure you want to delete this depot record?")) return;

    try {
      const res = await fetch(`${API_BASE_URL}/master-data/depots/${depotId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });

      if (res.ok) {
        setDepots((prev) => prev.filter((d) => d.depot_id !== depotId && d.real_depot_id !== depotId));
        showToast("Territory record deleted", "info");
      } else {
        setDepots((prev) => prev.filter((d) => d.depot_id !== depotId));
        showToast("Territory record deleted", "info");
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
    setDepotFilter("all");
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
    <div className="flex flex-col h-full min-h-0 relative">
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
      {/* Integrated Control Toolbar */}
      <div className="py-2 px-3 bg-white border border-slate-200/80 rounded-xl flex flex-wrap items-center gap-3 text-xs font-semibold text-slate-700 shrink-0 shadow-2xs">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-3.5 h-3.5" />
          <input
            type="text"
            placeholder="Search employee, depot, HQ..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200/80 rounded-lg text-xs font-medium text-slate-900 focus:outline-none focus:border-[#0D3B8E] focus:bg-white transition-all placeholder:text-slate-400"
          />
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
          <span className="text-slate-400 font-bold uppercase tracking-wider text-[9px]">HQ Alignment:</span>
          <select
            value={hqFilter}
            onChange={(e) => setHqFilter(e.target.value === "all" ? "all" : e.target.value)}
            className="px-2.5 py-1 bg-slate-50 border border-slate-200/80 rounded-lg font-bold text-slate-700 text-xs focus:outline-none focus:border-[#0D3B8E]"
          >
            <option value="all">All Headquarters</option>
            {headquartersList.map((hq) => (
              <option key={hq.headquarters_id} value={hq.headquarters_id}>
                {hq.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-slate-400 font-bold uppercase tracking-wider text-[9px]">Depot Alignment:</span>
          <select
            value={depotFilter}
            onChange={(e) => setDepotFilter(e.target.value)}
            className="px-2.5 py-1 bg-slate-50 border border-slate-200/80 rounded-lg font-bold text-slate-700 text-xs focus:outline-none focus:border-[#0D3B8E]"
          >
            <option value="all">All Depots</option>
            {masterDepotsList.map((d) => (
              <option key={d.depot_id} value={d.name}>
                {d.name}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={resetFilters}
          className="ml-auto flex items-center gap-1 text-[11px] font-bold text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
          title="Reset Filters"
        >
          <RotateCcw className="w-3 h-3" /> Reset
        </button>
      </div>


      {/* Data Table Container */}
      <div className="bg-white rounded-xl shadow-2xs border border-slate-200/80 flex-1 min-h-0 overflow-hidden flex flex-col">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left border-collapse table-fixed min-w-[750px]">
            <thead>
              <tr className="bg-slate-50/80 border-b border-slate-200/80 sticky top-0 z-10 select-none">
                {/* S.No Column */}
                <th className="w-[6%] px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-center">
                  #
                </th>

                {/* User */}
                <th 
                  onClick={() => handleSort("depot_user")}
                  className="w-[22%] px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>User</span>
                    {sortField === "depot_user" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Role */}
                <th 
                  onClick={() => handleSort("depot_user_role")}
                  className="w-[12%] px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Role</span>
                    {sortField === "depot_user_role" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Depot */}
                <th 
                  onClick={() => handleSort("name")}
                  className="w-[24%] px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Depot</span>
                    {sortField === "name" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Headquarter */}
                <th 
                  onClick={() => handleSort("headquarters_name")}
                  className="w-[20%] px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Headquarter</span>
                    {sortField === "headquarters_name" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Active / Inactive Status */}
                <th 
                  onClick={() => handleSort("is_active")}
                  className="w-[10%] px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Status</span>
                    {sortField === "is_active" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#0D3B8E]" /> : <ChevronDown className="w-3 h-3 text-[#0D3B8E]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>

                {/* Actions */}
                <th className="w-[10%] px-3 py-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto text-[#0D3B8E] mb-2" />
                    Loading territory records from database...
                  </td>
                </tr>
              ) : paginatedDepots.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                    No Territory Records Found.
                  </td>
                </tr>
              ) : (
                paginatedDepots.map((depot, idx) => {
                  const serialNumber = (currentPage - 1) * rowsPerPage + idx + 1;
                  const roleText = resolveUserRole(depot);
                  const isEditing = editingId === depot.depot_id;
                  const selectedUser = usersList.find(u => String(u.user_id) === String(editUserId));
                  const displayRole = isEditing ? (selectedUser?.role || roleText) : roleText;

                  return (
                    <tr
                      key={depot.depot_id}
                      className={`transition-colors group ${!depot.is_active ? 'bg-slate-50/70 text-slate-400' : 'hover:bg-blue-50/20'}`}
                    >
                      {/* S.No Cell */}
                      <td className="px-4 py-2.5 text-center text-xs font-bold text-slate-400">
                        {serialNumber}
                      </td>

                      {/* User Column */}
                      <td className="px-4 py-2.5">
                        {isEditing ? (
                          <select
                            value={editUserId}
                            onChange={(e) => setEditUserId(e.target.value)}
                            className="w-full px-2.5 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                          >
                            <option value="">Unassigned</option>
                            {usersList.map((u) => (
                              <option key={u.user_id} value={u.user_id}>
                                {u.name} ({u.role || 'ASE'})
                              </option>
                            ))}
                          </select>
                        ) : (
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
                        )}
                      </td>

                      {/* Employee's Role */}
                      <td className="px-4 py-2.5">
                        <span className={`px-2.5 py-1 rounded border text-[10px] font-bold uppercase tracking-wider ${getRoleBadgeStyle(displayRole)}`}>
                          {displayRole}
                        </span>
                      </td>

                      {/* Depot */}
                      <td className="px-4 py-2.5">
                        {isEditing ? (
                          <select
                            value={editDepotId || editName}
                            onChange={(e) => {
                              const val = e.target.value;
                              setEditDepotId(val);
                              const match = masterDepotsList.find(d => String(d.depot_id) === val || d.name === val);
                              if (match) {
                                setEditName(match.name);
                                if (match.headquarters_id && (!editHqId || editHqId === "")) {
                                  setEditHqId(match.headquarters_id);
                                }
                              } else {
                                setEditName(val);
                              }
                            }}
                            className="w-full px-2.5 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
                          >
                            <option value="">Unassigned</option>
                            {masterDepotsList.map((d) => (
                              <option key={d.depot_id} value={d.depot_id}>
                                {d.name}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <div className="flex items-center gap-2">
                            <MapPin
                              className={`w-3.5 h-3.5 ${depot.name === "Unassigned" ? "text-slate-300" : depot.is_active ? "text-[#0D3B8E]" : "text-slate-400"}`}
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
                      <td className="px-4 py-2.5">
                        {isEditing ? (
                          <select
                            value={editHqId}
                            onChange={(e) => setEditHqId(e.target.value === "" ? "" : e.target.value)}
                            className="w-full px-2.5 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
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
                              className={`w-3.5 h-3.5 ${depot.headquarters_name === "Unassigned" ? "text-slate-300" : depot.is_active ? "text-[#0D3B8E]" : "text-slate-400"}`}
                            />
                            <span
                              className={`text-xs font-bold ${depot.headquarters_name === "Unassigned" ? "text-slate-400 italic" : depot.is_active ? "text-slate-700" : "text-slate-500"}`}
                            >
                              {depot.headquarters_name}
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-4 py-2.5">
                        {isEditing ? (
                          <select
                            value={editIsActive ? "active" : "inactive"}
                            onChange={(e) => setEditIsActive(e.target.value === "active")}
                            className="w-full px-2.5 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#0D3B8E]"
                          >
                            <option value="active">Active</option>
                            <option value="inactive">Inactive</option>
                          </select>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <span className={`w-2 h-2 rounded-full ${depot.is_active ? "bg-emerald-500" : "bg-slate-300"}`}></span>
                            <span className={`text-xs font-bold ${depot.is_active ? "text-emerald-700" : "text-slate-400"}`}>
                              {depot.is_active ? "Active" : "Inactive"}
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-2.5 text-right">
                        {isEditing ? (
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => handleSave(depot)}
                              className="p-1.5 bg-emerald-50 text-emerald-600 rounded hover:bg-emerald-100 transition-colors"
                              title="Save Territory Changes"
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
