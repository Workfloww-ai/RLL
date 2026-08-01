import React, { useState } from "react";
import { Users, Search, Filter, Edit2, Check, X, MapPin, Trash2 } from "lucide-react";
import { User, Territory } from "../types";

const INITIAL_TERRITORIES: Territory[] = [
  {
    id: "t1",
    name: "Jaipur (District)",
    level: "District",
    capacity: 3,
    assignedUsers: [],
  },
  {
    id: "t2",
    name: "Jodhpur Depot",
    level: "Depot",
    capacity: 2,
    assignedUsers: [],
  },
  {
    id: "t3",
    name: "Udaipur Regional Office",
    level: "District Office",
    capacity: 4,
    assignedUsers: [],
  },
  {
    id: "t4",
    name: "Ajmer Depot",
    level: "Depot",
    capacity: 1,
    assignedUsers: [],
  },
];

const INITIAL_USERS: User[] = [
  {
    id: "t1",
    name: "Dummy User 1",
    role: "Area Sales Manager",
    depotName: "Mansarovar",
    circleName: "Jaipur City",
    headquarters: "Jaipur North",
    reportingManager: "Unassigned",
    isActive: true,
  },
  {
    id: "t2",
    name: "Dummy User 2",
    role: "Territory Executive",
    depotName: "Pal Road",
    circleName: "Jodhpur Rural",
    headquarters: "Jodhpur West",
    reportingManager: "Unassigned",
    isActive: false,
  },
  {
    id: "t3",
    name: "Dummy User 3",
    role: "Regional Supervisor",
    depotName: "Pratapnagar",
    circleName: "Udaipur East",
    headquarters: "Udaipur Central",
    reportingManager: "Unassigned",
    isActive: true,
  },
];

export default function TerritoryManagement() {
  const [users, setUsers] = useState<User[]>(INITIAL_USERS);
  const [searchQuery, setSearchQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  // Temp state for editing
  const [editDepot, setEditDepot] = useState("");
  const [editHeadquarters, setEditHeadquarters] = useState("");
  const [editIsActive, setEditIsActive] = useState(true);

  const handleEditClick = (user: User) => {
    setEditingId(user.id);
    setEditDepot(user.depotName);
    setEditHeadquarters(user.headquarters);
    setEditIsActive(user.isActive ?? true);
  };

  const handleSave = (userId: string) => {
    setUsers((prev) =>
      prev.map((u) =>
        u.id === userId
          ? {
              ...u,
              depotName: editDepot,
              headquarters: editHeadquarters,
              isActive: editIsActive,
            }
          : u,
      ),
    );
    setEditingId(null);
  };

  const handleCancel = () => {
    setEditingId(null);
  };

  const handleDelete = (userId: string) => {
    setUsers((prev) => prev.filter((u) => u.id !== userId));
  };

  const filteredUsers = users.filter(
    (user) =>
      user.depotName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      user.headquarters.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="mb-6 flex justify-between items-end shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">
            Territory Management
          </h1>
          <p className="text-slate-500 mt-1 text-sm font-medium">
            Instantly edit alignments and locations across the organization.
          </p>
        </div>
        <div className="flex gap-3">
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
          <button className="flex items-center gap-2 px-3 py-1.5 border border-slate-200 text-xs font-bold text-slate-600 rounded bg-white hover:bg-slate-50">
            <Filter className="w-3 h-3" /> Filter Table
          </button>
          <button className="px-3 py-1.5 bg-[#004B87] text-white text-xs font-bold rounded shadow-sm hover:bg-blue-800 transition-colors">
            Export Data
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 flex-1 overflow-hidden flex flex-col">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                  Depot
                </th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                  HQ
                </th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                  Status
                </th>
                <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredUsers.length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    className="px-6 py-12 text-center text-sm font-medium text-slate-500"
                  >
                    No records found matching your search.
                  </td>
                </tr>
              ) : (
                filteredUsers.map((user) => (
                  <tr
                    key={user.id}
                    className="hover:bg-slate-50/50 transition-colors group"
                  >
                    <td className="px-6 py-4">
                      {editingId === user.id ? (
                        <input
                          type="text"
                          value={editDepot}
                          onChange={(e) => setEditDepot(e.target.value)}
                          className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                        />
                      ) : (
                        <div className="flex items-center gap-2">
                          <MapPin
                            className={`w-3.5 h-3.5 ${user.depotName === "Unassigned" ? "text-slate-300" : "text-[#004B87]"}`}
                          />
                          <span
                            className={`text-xs font-bold ${user.depotName === "Unassigned" ? "text-slate-400 italic" : "text-slate-700"}`}
                          >
                            {user.depotName}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {editingId === user.id ? (
                        <input
                          type="text"
                          value={editHeadquarters}
                          onChange={(e) => setEditHeadquarters(e.target.value)}
                          className="w-full px-2 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 rounded focus:outline-none focus:border-[#004B87]"
                        />
                      ) : (
                        <div className="flex items-center gap-2">
                          <MapPin
                            className={`w-3.5 h-3.5 ${user.headquarters === "Unassigned" ? "text-slate-300" : "text-[#004B87]"}`}
                          />
                          <span
                            className={`text-xs font-bold ${user.headquarters === "Unassigned" ? "text-slate-400 italic" : "text-slate-700"}`}
                          >
                            {user.headquarters}
                          </span>
                        </div>
                      )}
                    </td>
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
                          <span className={`w-2 h-2 rounded-full ${user.isActive ? "bg-emerald-500" : "bg-slate-300"}`}></span>
                          <span className={`text-xs font-bold ${user.isActive ? "text-emerald-700" : "text-slate-500"}`}>
                            {user.isActive ? "Active" : "Inactive"}
                          </span>
                        </div>
                      )}
                    </td>

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
          <span>Showing {filteredUsers.length} territory records</span>
          <div className="flex gap-4">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>{" "}
              Active
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-slate-300"></span>{" "}
              Unassigned
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
