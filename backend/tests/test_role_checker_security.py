import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from backend.core.security import RoleChecker, normalize_role_name


class TestRoleCheckerSecurity:
    """Automated security regression tests for Item 3: RoleChecker privilege escalation elimination."""

    # 1. A regular user is denied access to an admin-only endpoint
    def test_01_regular_user_denied_admin_endpoint(self):
        admin_checker = RoleChecker(["admin", "super_admin"])
        regular_user = {
            "user_id": "u-reg",
            "email": "user@rll.in",
            "role_name": "viewer",
            "roles": ["viewer"]
        }
        with pytest.raises(HTTPException) as exc_info:
            admin_checker(current_user=regular_user)
        assert exc_info.value.status_code == 403
        assert "Permission denied" in exc_info.value.detail

    # 2. A regular user is NOT granted access merely because 'admin' appears in allowed_roles
    # (Testing the root cause bug: 'if "admin" in allowed')
    def test_02_admin_in_allowed_roles_does_not_grant_access_to_non_admin(self):
        admin_checker = RoleChecker(["admin"])
        # Attacker is a field sales TSM or viewer
        field_user = {
            "user_id": "u-tsm",
            "email": "tsm@rll.in",
            "role_name": "tsm",
            "roles": ["tsm"]
        }
        with pytest.raises(HTTPException) as exc_info:
            admin_checker(current_user=field_user)
        assert exc_info.value.status_code == 403
        assert "Permission denied" in exc_info.value.detail

    # 3. An admin is authorized on admin endpoints, but denied on operational-only endpoints
    def test_03_admin_strictly_enforces_route_allowed_roles(self):
        admin_user = {
            "user_id": "u-admin",
            "email": "admin@rll.in",
            "role_name": "admin",
            "roles": ["admin"]
        }
        # Endpoint explicitly allowing admin
        admin_checker = RoleChecker(["admin", "super_admin"])
        assert admin_checker(current_user=admin_user) == admin_user

        # Operational-only endpoint (developer only)
        dev_checker = RoleChecker(["developer"])
        with pytest.raises(HTTPException) as exc_info:
            dev_checker(current_user=admin_user)
        assert exc_info.value.status_code == 403

        # Operational-only endpoint (tsm/ase field only)
        field_only_checker = RoleChecker(["tsm", "ase"])
        with pytest.raises(HTTPException) as exc_info:
            field_only_checker(current_user=admin_user)
        assert exc_info.value.status_code == 403

    # 4. Super admin receives only privileges intended by route policy
    def test_04_super_admin_role_authorization(self):
        super_admin_user = {
            "user_id": "u-sa",
            "email": "superadmin@rll.in",
            "role_name": "super_admin",
            "roles": ["super_admin"]
        }
        sa_checker = RoleChecker(["super_admin"])
        assert sa_checker(current_user=super_admin_user) == super_admin_user

        # Route requiring developer role specifically
        dev_checker = RoleChecker(["developer"])
        with pytest.raises(HTTPException) as exc_info:
            dev_checker(current_user=super_admin_user)
        assert exc_info.value.status_code == 403

    # 5. Multiple assigned roles: user authorized when at least one matches
    def test_05_multi_role_user_authorized_on_any_matching_role(self):
        dual_user = {
            "user_id": "u-dual",
            "email": "dual@rll.in",
            "role_name": "tsm",
            "roles": ["tsm", "ase"]
        }
        # Checker requiring ASE
        ase_checker = RoleChecker(["ase"])
        assert ase_checker(current_user=dual_user) == dual_user

        # Checker requiring TSM
        tsm_checker = RoleChecker(["tsm"])
        assert tsm_checker(current_user=dual_user) == dual_user

        # Checker requiring Leader (neither tsm nor ase)
        leader_checker = RoleChecker(["leader"])
        with pytest.raises(HTTPException) as exc_info:
            leader_checker(current_user=dual_user)
        assert exc_info.value.status_code == 403

    # 6. User with no assigned roles is strictly denied
    @pytest.mark.parametrize("empty_roles", [[], ["unassigned"], None])
    def test_06_unassigned_or_empty_roles_denied(self, empty_roles):
        checker = RoleChecker(["admin", "tsm", "viewer"])
        user = {
            "user_id": "u-none",
            "email": "none@rll.in",
            "role_name": "unassigned",
            "roles": empty_roles
        }
        with pytest.raises(HTTPException) as exc_info:
            checker(current_user=user)
        assert exc_info.value.status_code == 403

    # 7. Unknown or malformed roles cannot obtain elevated permissions
    @pytest.mark.parametrize("bad_role", [
        "admin_impostor",
        "super_admin_bypass",
        "unknown_guest",
        "root",
        "system",
        "   ",
        "null",
    ])
    def test_07_unknown_or_malformed_roles_denied(self, bad_role):
        admin_checker = RoleChecker(["admin", "super_admin"])
        user = {
            "user_id": "u-bad",
            "email": "bad@rll.in",
            "role_name": bad_role,
            "roles": [bad_role]
        }
        with pytest.raises(HTTPException) as exc_info:
            admin_checker(current_user=user)
        assert exc_info.value.status_code == 403

    # 8. Inactive role assignments cannot grant permissions
    def test_08_inactive_role_filtered_out_and_denied(self):
        # When user_roles has is_active=False, get_current_user assigns 'unassigned' and roles=[]
        user = {
            "user_id": "u-inactive",
            "email": "inactive@rll.in",
            "role_name": "unassigned",
            "roles": []
        }
        admin_checker = RoleChecker(["admin", "super_admin"])
        with pytest.raises(HTTPException) as exc_info:
            admin_checker(current_user=user)
        assert exc_info.value.status_code == 403

    # 9. Role-name case and whitespace variations handled securely and consistently
    def test_09_role_name_normalization_consistency(self):
        # Test normalize_role_name helper directly
        assert normalize_role_name("Super Admin") == "super_admin"
        assert normalize_role_name("super admin") == "super_admin"
        assert normalize_role_name("SUPER_ADMIN") == "super_admin"
        assert normalize_role_name("superadmin") == "super_admin"
        assert normalize_role_name("  Team Leader  ") == "team_leader"
        assert normalize_role_name("TSM") == "tsm"
        assert normalize_role_name("ASE") == "ase"
        assert normalize_role_name("territory executive") == "territory_executive"
        assert normalize_role_name(None) == ""
        assert normalize_role_name("   ") == ""

        # Test RoleChecker with case/whitespace differences
        checker = RoleChecker(["Super Admin", "Team Leader"])
        user_with_underscores = {
            "user_id": "u-sa",
            "email": "sa@rll.in",
            "role_name": "super_admin",
            "roles": ["super_admin"]
        }
        assert checker(current_user=user_with_underscores) == user_with_underscores

        user_with_spaces = {
            "user_id": "u-tl",
            "email": "tl@rll.in",
            "role_name": "team leader",
            "roles": ["team leader"]
        }
        assert checker(current_user=user_with_spaces) == user_with_spaces

    # 10. Empty or malformed allowed_roles cannot accidentally authorize access
    @pytest.mark.parametrize("bad_allowed", [[], [""], ["   "], [None]])
    def test_10_empty_allowed_roles_fails_closed(self, bad_allowed):
        broken_checker = RoleChecker(bad_allowed)
        admin_user = {
            "user_id": "u-admin",
            "email": "admin@rll.in",
            "role_name": "admin",
            "roles": ["admin"]
        }
        with pytest.raises(HTTPException) as exc_info:
            broken_checker(current_user=admin_user)
        assert exc_info.value.status_code == 403
        assert "no authorized roles configured" in exc_info.value.detail

    # 11. Existing endpoints retain intended access rules
    def test_11_existing_endpoint_policies_retained(self):
        # Users management router policy: ["admin", "super_admin"]
        users_admin_only = RoleChecker(["admin", "super_admin"])

        admin_user = {"user_id": "1", "roles": ["admin"], "role_name": "admin"}
        sa_user = {"user_id": "2", "roles": ["super_admin"], "role_name": "super_admin"}
        tsm_user = {"user_id": "3", "roles": ["tsm"], "role_name": "tsm"}

        assert users_admin_only(current_user=admin_user) == admin_user
        assert users_admin_only(current_user=sa_user) == sa_user
        with pytest.raises(HTTPException):
            users_admin_only(current_user=tsm_user)

        # Mobile router policy: MOBILE_ACCESS_ROLES
        from backend.mobile.router import mobile_access_checker
        ase_user = {"user_id": "4", "roles": ["ase"], "role_name": "ase"}
        dev_user = {"user_id": "6", "roles": ["developer"], "role_name": "developer"}
        te_user = {"user_id": "7", "roles": ["territory_executive"], "role_name": "territory_executive"}
        viewer_user = {"user_id": "5", "roles": ["viewer"], "role_name": "viewer"}

        assert mobile_access_checker(current_user=tsm_user) == tsm_user
        assert mobile_access_checker(current_user=ase_user) == ase_user
        assert mobile_access_checker(current_user=admin_user) == admin_user
        assert mobile_access_checker(current_user=dev_user) == dev_user
        assert mobile_access_checker(current_user=sa_user) == sa_user
        assert mobile_access_checker(current_user=te_user) == te_user
        with pytest.raises(HTTPException):
            mobile_access_checker(current_user=viewer_user)
