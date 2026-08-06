import logging
from typing import List, Optional, Set
from backend.db.client import get_supabase

logger = logging.getLogger(__name__)

class AnalyticsScopeService:
    """
    Centralized service to resolve allowed depot IDs for an authenticated user
    based on Top Management, TSM, and ASE role hierarchies.
    """

    def resolve_allowed_depot_ids(self, user: dict) -> Optional[Set[int]]:
        """
        Returns:
            - None: User has Top Management scope (access to ALL depots).
            - Set[int]: Specific list of allowed depot IDs for TSM or ASE.
        """
        role_name = (user.get("role_name") or user.get("role") or "").lower()
        user_id = user.get("user_id")

        # Top Management / Admin can see ALL data
        if role_name in {"admin", "top_management", "management", "super_admin"}:
            return None

        client = get_supabase()
        if not client or not user_id:
            # Fallback for dev mode / mock user: check if depot_id set directly on user dict
            user_depot = user.get("depot_id")
            return {user_depot} if user_depot else None

        try:
            # 1. Check if user is a TSM (retrieve mapped ASEs from ase_tsm_mapping)
            tsm_mapping_res = (
                client.table("ase_tsm_mapping")
                .select("ase_user_id")
                .eq("tsm_user_id", user_id)
                .execute()
            )
            
            ase_user_ids = [
                row["ase_user_id"] 
                for row in (tsm_mapping_res.data or []) 
                if row.get("ase_user_id")
            ]

            # If user is a TSM, include self + mapped ASE IDs
            target_user_ids = set(ase_user_ids)
            target_user_ids.add(user_id)

            # 2. Fetch assigned depot IDs for all target user IDs from user_depot
            user_depot_res = (
                client.table("user_depot")
                .select("depot_id")
                .in_("user_id", list(target_user_ids))
                .execute()
            )

            allowed_depots = {
                row["depot_id"] 
                for row in (user_depot_res.data or []) 
                if row.get("depot_id") is not None
            }

            return allowed_depots

        except Exception as e:
            logger.error(f"Error resolving analytics scope for user {user_id}: {e}")
            user_depot = user.get("depot_id")
            return {user_depot} if user_depot else set()

analytics_scope_service = AnalyticsScopeService()
