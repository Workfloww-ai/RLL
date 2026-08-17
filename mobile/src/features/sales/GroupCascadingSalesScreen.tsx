import React, { useState, useEffect, useMemo } from 'react';
import { GroupCascading, LicenseeCascading, BrandSaleCascading } from '../../types';
import { fetchCascadingGroups, fetchGroupLicensees, fetchLicenseeBrandSales } from '../../lib/api';
import { formatNumber } from '../../lib/utils';
import {
  Search,
  ChevronRight,
  MapPin,
  Users,
  Wine,
  X,
  ArrowLeft,
  ArrowUpDown,
  ChevronLeft,
} from 'lucide-react';
import { motion } from 'motion/react';

interface GroupCascadingSalesScreenProps {
  dateFrom: string;
  dateTo: string;
  period: string;
}

type SortOption = 'alpha-asc' | 'alpha-desc' | 'cases-desc' | 'cases-asc';

export const GroupCascadingSalesScreen: React.FC<GroupCascadingSalesScreenProps> = ({
  dateFrom,
  dateTo,
  period,
}) => {
  // Navigation State
  const [selectedGroup, setSelectedGroup] = useState<GroupCascading | null>(null);
  const [selectedLicensee, setSelectedLicensee] = useState<LicenseeCascading | null>(null);

  // Data State
  const [groups, setGroups] = useState<GroupCascading[]>([]);
  const [licensees, setLicensees] = useState<LicenseeCascading[]>([]);
  const [brandSales, setBrandSales] = useState<BrandSaleCascading[]>([]);

  // Filtering & Pagination State
  const [loading, setLoading] = useState<boolean>(false);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [activeDepotFilter, setActiveDepotFilter] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOption>('alpha-asc'); // Default: Alphabetical (A-Z)
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [itemsPerPage, setItemsPerPage] = useState<number>(15);

  // 1. Fetch Groups when date filter changes
  useEffect(() => {
    loadGroups();
  }, [dateFrom, dateTo, period]);

  const loadGroups = async () => {
    setLoading(true);
    try {
      const data = await fetchCascadingGroups(dateFrom, dateTo, period);
      setGroups(data || []);
    } catch (err) {
      console.error('Error loading cascading groups:', err);
    } finally {
      setLoading(false);
    }
  };

  // 2. Fetch Licensees when selectedGroup or activeDepotFilter changes
  useEffect(() => {
    if (selectedGroup) {
      loadLicensees(selectedGroup.group_id, activeDepotFilter);
    }
  }, [selectedGroup, activeDepotFilter, dateFrom, dateTo, period]);

  const loadLicensees = async (groupId: string, depotName: string | null) => {
    setLoading(true);
    try {
      const data = await fetchGroupLicensees(groupId, dateFrom, dateTo, period, depotName || undefined);
      setLicensees(data || []);
    } catch (err) {
      console.error('Error loading group licensees:', err);
    } finally {
      setLoading(false);
    }
  };

  // 3. Fetch Brand Sales when selectedLicensee or activeDepotFilter changes
  useEffect(() => {
    if (selectedLicensee) {
      loadBrandSales(selectedLicensee.licensee_id, activeDepotFilter);
    }
  }, [selectedLicensee, activeDepotFilter, dateFrom, dateTo, period]);

  const loadBrandSales = async (licenseeId: string, depotName: string | null) => {
    setLoading(true);
    try {
      const data = await fetchLicenseeBrandSales(licenseeId, dateFrom, dateTo, period, depotName || undefined);
      setBrandSales(data || []);
    } catch (err) {
      console.error('Error loading brand sales:', err);
    } finally {
      setLoading(false);
    }
  };

  // Reset page to 1 whenever filters or selection change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, sortOrder, selectedGroup, selectedLicensee, activeDepotFilter, itemsPerPage]);

  const handleGroupSelect = (group: GroupCascading) => {
    setSelectedGroup(group);
    setSelectedLicensee(null);
    setBrandSales([]);
    setSearchTerm('');
  };

  const handleLicenseeSelect = (licensee: LicenseeCascading) => {
    setSelectedLicensee(licensee);
    setSearchTerm('');
  };

  const handleBack = () => {
    if (selectedLicensee) {
      setSelectedLicensee(null);
      setSearchTerm('');
    } else if (selectedGroup) {
      setSelectedGroup(null);
      setActiveDepotFilter(null);
      setSearchTerm('');
    }
  };

  const handleDepotClick = (e: React.MouseEvent, depotName: string) => {
    e.stopPropagation();
    setActiveDepotFilter(prev => (prev === depotName ? null : depotName));
  };

  // Sorted and Filtered Groups (Default: Alphabetical A-Z)
  const sortedGroups = useMemo(() => {
    const list = groups.filter(g =>
      g.group_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      g.linked_depots.some(d => d.toLowerCase().includes(searchTerm.toLowerCase()))
    );
    return list.sort((a, b) => {
      if (sortOrder === 'alpha-asc') return a.group_name.localeCompare(b.group_name);
      if (sortOrder === 'alpha-desc') return b.group_name.localeCompare(a.group_name);
      if (sortOrder === 'cases-desc') return b.total_cases - a.total_cases;
      if (sortOrder === 'cases-asc') return a.total_cases - b.total_cases;
      return a.group_name.localeCompare(b.group_name);
    });
  }, [groups, searchTerm, sortOrder]);

  // Sorted and Filtered Licensees (Default: Alphabetical A-Z)
  const sortedLicensees = useMemo(() => {
    const list = licensees.filter(l =>
      l.licensee_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      l.trade.toLowerCase().includes(searchTerm.toLowerCase())
    );
    return list.sort((a, b) => {
      if (sortOrder === 'alpha-asc') return a.licensee_name.localeCompare(b.licensee_name);
      if (sortOrder === 'alpha-desc') return b.licensee_name.localeCompare(a.licensee_name);
      if (sortOrder === 'cases-desc') return b.total_cases - a.total_cases;
      if (sortOrder === 'cases-asc') return a.total_cases - b.total_cases;
      return a.licensee_name.localeCompare(b.licensee_name);
    });
  }, [licensees, searchTerm, sortOrder]);

  // Sorted and Filtered Brands (Default: Alphabetical A-Z)
  const sortedBrands = useMemo(() => {
    const list = brandSales.filter(b =>
      b.brand_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      b.company_name.toLowerCase().includes(searchTerm.toLowerCase())
    );
    return list.sort((a, b) => {
      if (sortOrder === 'alpha-asc') return a.brand_name.localeCompare(b.brand_name);
      if (sortOrder === 'alpha-desc') return b.brand_name.localeCompare(a.brand_name);
      if (sortOrder === 'cases-desc') return b.total_cases - a.total_cases;
      if (sortOrder === 'cases-asc') return a.total_cases - b.total_cases;
      return a.brand_name.localeCompare(b.brand_name);
    });
  }, [brandSales, searchTerm, sortOrder]);

  // Current active view list for pagination
  const currentFullList = !selectedGroup
    ? sortedGroups
    : !selectedLicensee
      ? sortedLicensees
      : sortedBrands;

  const totalItems = currentFullList.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / itemsPerPage));
  const validCurrentPage = Math.min(currentPage, totalPages);

  const paginatedList = useMemo(() => {
    const start = (validCurrentPage - 1) * itemsPerPage;
    return currentFullList.slice(start, start + itemsPerPage);
  }, [currentFullList, validCurrentPage, itemsPerPage]);

  const totalCasesSum = brandSales.reduce((acc, b) => acc + (b.total_cases || 0), 0);
  const totalBottlesSum = brandSales.reduce((acc, b) => acc + (b.total_bottles || 0), 0);

  return (
    <div className="space-y-3">
      {/* Top Navigation Bar with Back Button & Breadcrumbs (Only rendered during drill-down or filter) */}
      {(selectedGroup || selectedLicensee || activeDepotFilter) && (
        <div className="bg-white p-3 rounded-2xl border border-slate-200 shadow-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {(selectedGroup || selectedLicensee) && (
              <button
                onClick={handleBack}
                id="groups-back-btn"
                type="button"
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-100 hover:bg-[#0F2042] hover:text-white text-[#0F2042] text-xs font-bold transition-all shrink-0"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back</span>
              </button>
            )}

            {/* Breadcrumb path */}
            <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500 truncate">
              {selectedGroup && (
                <>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-700 shrink-0" />
                  <span className="font-bold text-slate-800 truncate">{selectedGroup.group_name}</span>
                </>
              )}
              {selectedLicensee && (
                <>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-700 shrink-0" />
                  <span className="font-bold text-[#0F2042] truncate">{selectedLicensee.licensee_name}</span>
                </>
              )}
            </div>
          </div>

          {/* Active Depot Filter Chip Clear Button */}
          {activeDepotFilter && (
            <button
              onClick={() => setActiveDepotFilter(null)}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 text-[10px] font-bold shrink-0"
            >
              <span>Depot: {activeDepotFilter}</span>
              <X className="w-3 h-3 text-sky-500 hover:text-sky-800" />
            </button>
          )}
        </div>
      )}

      {/* Controls Bar: Search + Sorting Dropdown + Items Per Page */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder={
                !selectedGroup
                  ? "Search group..."
                  : !selectedLicensee
                    ? "Search licensee..."
                    : "Search brand..."
              }
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              id="groups-search-input"
              className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-8 py-1.5 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#0F2042] transition-all"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Sort Selector (Default: A-Z Alphabetical) */}
          <div className="relative flex items-center shrink-0">
            <ArrowUpDown className="w-3 h-3 text-slate-500 absolute left-2.5 pointer-events-none" />
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as SortOption)}
              className="bg-white border border-slate-200 rounded-xl pl-7 pr-2 py-1.5 text-[11px] font-bold text-[#0F2042] focus:outline-none focus:border-[#0F2042]"
            >
              <option value="alpha-asc">A-Z (Name)</option>
              <option value="alpha-desc">Z-A (Name)</option>
              <option value="cases-desc">Highest Cases</option>
              <option value="cases-asc">Lowest Cases</option>
            </select>
          </div>
        </div>

        {/* Total Count & Page Size Selector */}
        <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium px-1">
          <span>
            Showing {totalItems === 0 ? 0 : (validCurrentPage - 1) * itemsPerPage + 1}-
            {Math.min(validCurrentPage * itemsPerPage, totalItems)} of {totalItems} item(s)
          </span>

          <div className="flex items-center gap-1">
            <span>Per page:</span>
            <select
              value={itemsPerPage}
              onChange={(e) => setItemsPerPage(Number(e.target.value))}
              className="bg-white border border-slate-200 rounded-lg px-1.5 py-0.5 text-[11px] font-bold text-slate-700 focus:outline-none"
            >
              <option value={10}>10</option>
              <option value={15}>15</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
          </div>
        </div>
      </div>

      {/* Loading Indicator */}
      {loading && (
        <div className="text-center py-6 text-xs text-slate-400 font-medium">
          Loading group sales data...
        </div>
      )}

      {!loading && (
        <>
          {/* STEP 1: GROUPS DIRECTORY LIST */}
          {!selectedGroup && (
            <div className="space-y-2">
              {paginatedList.length === 0 ? (
                <div className="text-center py-8 bg-white rounded-2xl border border-slate-200 p-4">
                  <p className="text-xs font-bold text-slate-700">No groups found</p>
                </div>
              ) : (
                (paginatedList as GroupCascading[]).map((group, idx) => (
                  <motion.div
                    key={group.group_id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.15, delay: idx * 0.02 }}
                    onClick={() => handleGroupSelect(group)}
                    id={`group-card-${group.group_id}`}
                    className="p-3.5 rounded-2xl bg-white border border-slate-200/80 hover:border-[#0F2042]/40 transition-all cursor-pointer group space-y-2.5 shadow-xs"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <h4 className="text-xs sm:text-sm font-bold text-slate-900 group-hover:text-[#0F2042] transition-colors truncate">
                          {group.group_name}
                        </h4>
                        <p className="text-[10px] text-slate-400 font-medium flex items-center gap-1 mt-0.5">
                          <Users className="w-3 h-3 text-[#0F2042]" />
                          {group.total_licensees} Licensee(s)
                        </p>
                      </div>

                      <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-[#0F2042] group-hover:translate-x-0.5 transition-all shrink-0" />
                    </div>

                    {/* Metrics 2 Columns */}
                    <div className="grid grid-cols-2 gap-2 bg-slate-50 p-2.5 rounded-xl border border-slate-100 text-center">
                      <div>
                        <span className="text-[9px] font-semibold text-slate-400 uppercase block">CASES</span>
                        <span className="text-xs font-bold text-[#0F2042]">{formatNumber(group.total_cases)}</span>
                      </div>
                      <div>
                        <span className="text-[9px] font-semibold text-slate-400 uppercase block">BOTTLES</span>
                        <span className="text-xs font-bold text-slate-800">{formatNumber(group.total_bottles)}</span>
                      </div>
                    </div>
                  </motion.div>
                ))
              )}
            </div>
          )}

          {/* STEP 2: LICENSEES LIST UNDER SELECTED GROUP */}
          {selectedGroup && !selectedLicensee && (
            <div className="space-y-2.5">
              {/* Highlighted Group Summary Card (Compact Layout) */}
              <div className="px-3 py-2 bg-gradient-to-r from-[#0F2042] to-[#1E3A8A] rounded-xl text-white shadow-xs">
                <div className="flex items-center justify-between gap-2.5">
                  {/* Name & Tag on left */}
                  <div className="min-w-0 flex-1">
                    <span className="text-[8px] font-bold text-slate-300 uppercase tracking-wider block leading-none mb-0.5">GROUP SELECTED</span>
                    <h3 className="text-xs font-bold text-white leading-snug break-words">{selectedGroup.group_name}</h3>
                  </div>

                  {/* Parallel Stat Badges on right */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    <div className="bg-white/10 px-2 py-1 rounded-lg border border-white/10 text-center min-w-[56px]">
                      <span className="text-[7.5px] font-semibold text-slate-300 uppercase block leading-none mb-0.5">CASES</span>
                      <span className="text-xs font-bold text-amber-300 leading-none">{formatNumber(selectedGroup.total_cases)}</span>
                    </div>
                    <div className="bg-white/10 px-2 py-1 rounded-lg border border-white/10 text-center min-w-[56px]">
                      <span className="text-[7.5px] font-semibold text-slate-300 uppercase block leading-none mb-0.5">BOTTLES</span>
                      <span className="text-xs font-bold text-emerald-300 leading-none">{formatNumber(selectedGroup.total_bottles)}</span>
                    </div>
                  </div>
                </div>
              </div>

              {paginatedList.length === 0 ? (
                <div className="text-center py-8 bg-white rounded-2xl border border-slate-200 p-4">
                  <p className="text-xs font-bold text-slate-700">No licensees found for this group</p>
                </div>
              ) : (
                (paginatedList as LicenseeCascading[]).map((lic, idx) => (
                  <motion.div
                    key={lic.licensee_id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.15, delay: idx * 0.02 }}
                    onClick={() => handleLicenseeSelect(lic)}
                    id={`licensee-card-${lic.licensee_id}`}
                    className="p-3.5 rounded-2xl bg-white border border-slate-200/80 hover:border-[#0F2042]/40 transition-all cursor-pointer group space-y-2.5 shadow-xs"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <h4 className="text-xs sm:text-sm font-bold text-slate-900 group-hover:text-[#0F2042] transition-colors truncate">
                          {lic.licensee_name}
                        </h4>
                        <span className="inline-block mt-0.5 px-2 py-0.5 rounded text-[9px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
                          Trade: {lic.trade}
                        </span>
                      </div>

                      <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-[#0F2042] group-hover:translate-x-0.5 transition-all shrink-0" />
                    </div>

                    {/* Metrics 2 Columns */}
                    <div className="grid grid-cols-2 gap-2 bg-slate-50 p-2.5 rounded-xl border border-slate-100 text-center">
                      <div>
                        <span className="text-[9px] font-semibold text-slate-400 uppercase block">CASES</span>
                        <span className="text-xs font-bold text-[#0F2042]">{formatNumber(lic.total_cases)}</span>
                      </div>
                      <div>
                        <span className="text-[9px] font-semibold text-slate-400 uppercase block">BOTTLES</span>
                        <span className="text-xs font-bold text-slate-800">{formatNumber(lic.total_bottles)}</span>
                      </div>
                    </div>

                    {/* Licensee Depot Pills */}
                    {lic.licensee_depots && lic.licensee_depots.length > 0 && (
                      <div className="pt-1.5 border-t border-slate-100 flex flex-wrap gap-1">
                        {lic.licensee_depots.map((depot, dIdx) => {
                          const isActive = activeDepotFilter === depot;
                          return (
                            <button
                              key={dIdx}
                              onClick={(e) => handleDepotClick(e, depot)}
                              className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md font-semibold border transition-all ${isActive
                                ? 'bg-[#0F2042] text-white border-[#0F2042]'
                                : 'bg-sky-50 text-sky-800 border-sky-200/80 hover:bg-sky-100'
                                }`}
                            >
                              <MapPin className="w-2.5 h-2.5 text-sky-600" />
                              <span>{depot}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </motion.div>
                ))
              )}
            </div>
          )}

          {/* STEP 3: BRAND WISE SALES BREAKDOWN */}
          {selectedLicensee && (
            <div className="space-y-2.5">
              {/* Licensee Summary Card (Compact Layout) */}
              <div className="px-3 py-2 bg-gradient-to-r from-[#0F2042] to-[#1E3A8A] rounded-xl text-white shadow-xs">
                <div className="flex items-center justify-between gap-2.5">
                  {/* Name & Tag on left */}
                  <div className="min-w-0 flex-1">
                    <span className="text-[8px] font-bold text-slate-300 uppercase tracking-wider block leading-none mb-0.5">LICENSEE SELECTED</span>
                    <h3 className="text-xs font-bold text-white leading-snug break-words">{selectedLicensee.licensee_name}</h3>
                  </div>

                  {/* Parallel Stat Badges on right */}
                  <div className="flex items-center gap-1.5 shrink-0">
                    <div className="bg-white/10 px-2 py-1 rounded-lg border border-white/10 text-center min-w-[56px]">
                      <span className="text-[7.5px] font-semibold text-slate-300 uppercase block leading-none mb-0.5">CASES</span>
                      <span className="text-xs font-bold text-amber-300 leading-none">{formatNumber(totalCasesSum)}</span>
                    </div>
                    <div className="bg-white/10 px-2 py-1 rounded-lg border border-white/10 text-center min-w-[56px]">
                      <span className="text-[7.5px] font-semibold text-slate-300 uppercase block leading-none mb-0.5">BOTTLES</span>
                      <span className="text-xs font-bold text-emerald-300 leading-none">{formatNumber(totalBottlesSum)}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Brand List */}
              {paginatedList.length === 0 ? (
                <div className="text-center py-8 bg-white rounded-2xl border border-slate-200 p-4">
                  <p className="text-xs font-bold text-slate-700">No brand sales found for this licensee</p>
                </div>
              ) : (
                (paginatedList as BrandSaleCascading[]).map((brand, idx) => (
                  <motion.div
                    key={brand.brand_id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.15, delay: idx * 0.02 }}
                    className="p-3.5 rounded-2xl bg-white border border-slate-200/80 hover:border-slate-300 transition-all space-y-2 shadow-xs"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <h4 className="text-xs sm:text-sm font-bold text-slate-900 flex items-center gap-1.5">
                          <Wine className="w-3.5 h-3.5 text-[#0F2042] shrink-0" />
                          <span className="truncate">{brand.brand_name}</span>
                        </h4>
                        <span className="inline-block mt-0.5 px-2 py-0.5 rounded text-[9px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                          {brand.company_name}
                        </span>
                      </div>
                    </div>

                    {/* Metrics 2 Columns */}
                    <div className="grid grid-cols-2 gap-2 bg-slate-50 p-2.5 rounded-xl border border-slate-100 text-center">
                      <div>
                        <span className="text-[9px] font-semibold text-slate-400 uppercase block">CASES</span>
                        <span className="text-xs font-bold text-[#0F2042]">{formatNumber(brand.total_cases)}</span>
                      </div>
                      <div>
                        <span className="text-[9px] font-semibold text-slate-400 uppercase block">BOTTLES</span>
                        <span className="text-xs font-bold text-slate-800">{formatNumber(brand.total_bottles)}</span>
                      </div>
                    </div>

                    {/* Sales Depots Pills */}
                    {brand.sales_depots && brand.sales_depots.length > 0 && (
                      <div className="pt-1 border-t border-slate-100 flex flex-wrap gap-1">
                        {brand.sales_depots.map((depot, dIdx) => (
                          <span key={dIdx} className="text-[9px] px-1.5 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200 font-medium">
                            📍 {depot}
                          </span>
                        ))}
                      </div>
                    )}
                  </motion.div>
                ))
              )}
            </div>
          )}

          {/* Pagination Controls Bar */}
          {totalItems > 0 && (
            <div className="flex items-center justify-between bg-white p-3 rounded-2xl border border-slate-200 shadow-xs text-xs">
              <button
                disabled={validCurrentPage <= 1}
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-[#0F2042] hover:text-white text-[#0F2042] font-bold disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Prev</span>
              </button>

              <span className="font-bold text-[#0F2042]">
                Page {validCurrentPage} of {totalPages}
              </span>

              <button
                disabled={validCurrentPage >= totalPages}
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                className="flex items-center gap-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-[#0F2042] hover:text-white text-[#0F2042] font-bold disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                <span>Next</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};
