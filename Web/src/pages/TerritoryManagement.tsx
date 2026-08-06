import React, { useState, useEffect, useMemo } from "react";
import { 
  Search, Filter, Edit2, Check, X, MapPin, Trash2, RefreshCw, 
  ChevronLeft, ChevronRight, ArrowUpDown, ChevronUp, ChevronDown, RotateCcw
} from "lucide-react";

interface DepotRecord {
  depot_id: number;
  name: string;
  headquarters_id: number | null;
  headquarters_name: string;
  is_active: boolean;
}

interface HeadquartersRecord {
  headquarters_id: number;
  name: string;
  is_active: boolean;
}

type SortField = "name" | "headquarters_name" | "is_active";
type SortDirection = "asc" | "desc";

export default function TerritoryManagement() {
  const [depots, setDepots] = useState<DepotRecord[]>([]);
  const [headquartersList, setHeadquartersList] = useState<HeadquartersRecord[]>([]);
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
  const [editIsActive, setEditIsActive] = useState(true);

  const token = localStorage.getItem("token");

  const fetchData = async () => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      
      const [depotsRes, hqRes] = await Promise.all([
        fetch("http://localhost:8000/api/v1/master-data/depots", { headers }),
        fetch("http://localhost:8000/api/v1/master-data/headquarters", { headers })
      ]);

      if (depotsRes.ok) {
        const depotsData = await depotsRes.json();
        setDepots(depotsData);
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

  useEffect(() => {
    fetchData();
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

  // Filter & Sort Pipeline
  const processedDepots = useMemo(() => {
    let result = [...depots];

    // Search query filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      result = result.filter(
        (d) =>
          d.name.toLowerCase().includes(query) ||
          (d.headquarters_name && d.headquarters_name.toLowerCase().includes(query))
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
      let aVal: any = a[sortField];
      let bVal: any = b[sortField];

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

  // Edit Handlers
  const handleEditClick = (depot: DepotRecord) => {
    setEditingId(depot.depot_id);
    setEditName(depot.name);
    setEditHqId(depot.headquarters_id ?? "");
    setEditIsActive(depot.is_active);
  };

  const handleSave = async (depotId: number) => {
    try {
      const payload = {
        name: editName.trim(),
        headquarters_id: editHqId !== "" ? Number(editHqId) : null,
        is_active: editIsActive
      };

      const res = await fetch(`http://localhost:8000/api/v1/master-data/depots/${depotId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const selectedHq = headquartersList.find((h) => h.headquarters_id === Number(editHqId));
        const hqName = selectedHq ? selectedHq.name : "Unassigned";

        setDepots((prev) =>
          prev.map((d) =>
            d.depot_id === depotId
              ? {
                  ...d,
                  name: editName.trim(),
                  headquarters_id: editHqId !== "" ? Number(editHqId) : null,
                  headquarters_name: hqName,
                  is_active: editIsActive
                }
              : d
          )
        );
        setEditingId(null);
      } else {
        alert("Failed to update depot in Supabase.");
      }
    } catch (error) {
      console.error("Error updating depot:", error);
      alert("Error connecting to server.");
    }
  };

  const handleCancel = () => {
    setEditingId(null);
  };

  const handleDelete = async (depotId: number) => {
    if (!confirm("Are you sure you want to delete this depot from Supabase?")) return;

    try {
      const res = await fetch(`http://localhost:8000/api/v1/master-data/depots/${depotId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });

      if (res.ok) {
        setDepots((prev) => prev.filter((d) => d.depot_id !== depotId));
      } else {
        alert("Failed to delete depot from Supabase.");
      }
    } catch (error) {
      console.error("Error deleting depot:", error);
    }
  };

  const resetFilters = () => {
    setSearchQuery("");
    setStatusFilter("all");
    setHqFilter("all");
    setSortField("name");
    setSortDirection("asc");
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Header & Controls */}
      <div className="mb-6 flex flex-col md:flex-row justify-between items-start md:items-end gap-4 shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">
            Territory Management
          </h1>
          <p className="text-slate-500 mt-1 text-sm font-medium">
            Instantly edit alignments and locations across the organization.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4" />
            <input
              type="text"
              placeholder="Search location..."
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
          <button 
            onClick={fetchData} 
            className="flex items-center gap-2 px-3 py-2 border border-slate-200 text-xs font-bold text-slate-600 rounded bg-white hover:bg-slate-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
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
                <th 
                  onClick={() => handleSort("headquarters_name")}
                  className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest cursor-pointer hover:text-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-1.5">
                    <span>HQ</span>
                    {sortField === "headquarters_name" ? (
                      sortDirection === "asc" ? <ChevronUp className="w-3 h-3 text-[#004B87]" /> : <ChevronDown className="w-3 h-3 text-[#004B87]" />
                    ) : (
                      <ArrowUpDown className="w-3 h-3 text-slate-300" />
                    )}
                  </div>
                </th>
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
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-[#004B87] mb-2" />
                    Loading territory records from database...
                  </td>
                </tr>
              ) : paginatedDepots.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                    No Territory Records Found.
                  </td>
                </tr>
              ) : (
                paginatedDepots.map((depot) => (
                  <tr
                    key={depot.depot_id}
                    className="hover:bg-slate-50/50 transition-colors group"
                  >
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
                            className={`w-3.5 h-3.5 ${depot.name === "Unassigned" ? "text-slate-300" : "text-[#004B87]"}`}
                          />
                          <span
                            className={`text-xs font-bold ${depot.name === "Unassigned" ? "text-slate-400 italic" : "text-slate-700"}`}
                          >
                            {depot.name}
                          </span>
                        </div>
                      )}
                    </td>
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
                          <MapPin
                            className={`w-3.5 h-3.5 ${depot.headquarters_name === "Unassigned" ? "text-slate-300" : "text-[#004B87]"}`}
                          />
                          <span
                            className={`text-xs font-bold ${depot.headquarters_name === "Unassigned" ? "text-slate-400 italic" : "text-slate-700"}`}
                          >
                            {depot.headquarters_name}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {editingId === depot.depot_id ? (
                        <select
                          value={editIsActive ? "active" : "inactive"}
                          onChange={(e) => setEditIsActive(e.target.value === "active")}
                          className="w-full px-2.5 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                        >
                          <option value="active">Active</option>
                          <option value="inactive">Inactive</option>
                        </select>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${depot.is_active ? "bg-emerald-500" : "bg-slate-300"}`}></span>
                          <span className={`text-xs font-bold ${depot.is_active ? "text-emerald-700" : "text-slate-500"}`}>
                            {depot.is_active ? "Active" : "Inactive"}
                          </span>
                        </div>
                      )}
                    </td>

                    <td className="px-6 py-4 text-right">
                      {editingId === depot.depot_id ? (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleSave(depot.depot_id)}
                            className="p-1.5 bg-emerald-50 text-emerald-600 rounded hover:bg-emerald-100 transition-colors"
                            title="Save Changes to Supabase"
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
                            title="Delete Record from Supabase"
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
