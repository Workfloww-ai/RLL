import difflib
import re
from typing import Any, Dict, List, Optional

# Known domain/field aliases where Excel sheets use informal names or variant surnames
KNOWN_USER_ALIASES: Dict[str, str] = {
    "amit kumar": "amit singh",
    "suresh kumar": "suresh kumar teli",
    "hemant": "hemant kumar kashyap",
    "hemant kashyap": "hemant kumar kashyap",
    "kuldeep": "kuldeep suwalka",
    "kapil": "kapil suwalka",
    "rajendra": "rajendra jogi",
    "vishnu gupta": "vishnu kumar gupta",
    "vishnu kumar": "vishnu kumar gupta",
    "sharad": "sharad mishra",
    "vaibhav": "vaibhav soni",
    "puneet": "puneet bhardwaj",
    "vivek": "vivek hemani",
    "vikas": "vikas solanki",
    "khemchand": "khemchand verma",
    "dilraj": "dilraj singh",
    "narayan lal": "narayan lal yadav",
    "anand": "anand sharma",
    "jittendra yadav": "jitendra yadav",
    "jittendra": "jitendra",
}


def _collapse_repeats(s: str) -> str:
    """Collapses consecutive repeated characters (e.g. 'jittendra' -> 'jitendra', 'sannjay' -> 'sanjay')."""
    return re.sub(r"([a-z0-9])\1+", r"\1", s.lower())


class UserNameMatcher:
    """
    Robust, bidirectional user name matching utility.

    Handles discrepancies where middle names are present or absent in either
    the database `public.users` table or input data (Excel / CSV sheets / API payloads).

    Features:
    - Prioritizes active users over inactive users.
    - Symmetrically matches First Name + Last Name (ignoring middle names or initials).
    - Resolves known field aliases (e.g. "Amit Kumar" -> "Amit Singh").
    - Normalizes punctuation, excessive whitespace, casing, and alphanumeric forms.
    - Resolves multi-person strings (e.g. "Hemant / Vaibhav" -> primary person).
    - Fallback matching on email prefix and first name.
    """

    def __init__(self, users: List[Dict[str, Any]], custom_aliases: Optional[Dict[str, str]] = None):
        # Sort active users first so active accounts have priority
        sorted_users = sorted(users, key=lambda x: 0 if x.get("is_active", True) else 1)

        self.users_by_id: Dict[str, Dict[str, Any]] = {}
        self.exact_map: Dict[str, str] = {}
        self.clean_map: Dict[str, str] = {}
        self.first_last_map: Dict[str, str] = {}
        self.clean_fl_map: Dict[str, str] = {}
        self.email_prefix_map: Dict[str, str] = {}
        self.first_only_map: Dict[str, str] = {}
        self.collapsed_map: Dict[str, str] = {}
        self.full_name_by_id: Dict[str, str] = {}
        self.alias_map: Dict[str, str] = dict(KNOWN_USER_ALIASES)
        if custom_aliases:
            self.alias_map.update({k.lower().strip(): v.lower().strip() for k, v in custom_aliases.items()})

        for u in sorted_users:
            raw_uid = u.get("user_id") or u.get("id")
            if not raw_uid:
                continue
            uid = str(raw_uid).strip()
            self.users_by_id[uid] = u

            fn = (u.get("first_name") or "").strip()
            ln = (u.get("last_name") or "").strip()
            full_name = f"{fn} {ln}".strip()
            if not full_name:
                continue

            self.full_name_by_id[uid] = full_name
            full_norm = re.sub(r"\s+", " ", full_name).lower()
            clean_str = re.sub(r"[^a-z0-9]", "", full_norm)

            email = str(u.get("email") or "").strip().lower()
            prefix = email.split("@")[0].strip() if "@" in email else ""
            clean_prefix = re.sub(r"[^a-z0-9]", "", prefix)

            tokens = [w for w in re.sub(r"[^a-z0-9\s]", "", full_norm).split() if w]

            # 1. Full normalized name
            if full_norm not in self.exact_map:
                self.exact_map[full_norm] = uid

            # 2. Alphanumeric full name
            if clean_str and clean_str not in self.clean_map:
                self.clean_map[clean_str] = uid

            # 3. First + Last name tokens (bridges missing or extra middle names)
            if len(tokens) >= 2:
                fl = f"{tokens[0]} {tokens[-1]}"
                fl_clean = f"{tokens[0]}{tokens[-1]}"
                if fl not in self.first_last_map:
                    self.first_last_map[fl] = uid
                if fl_clean not in self.clean_fl_map:
                    self.clean_fl_map[fl_clean] = uid

                # Also index short name if last_name had multiple parts
                if len(tokens) > 2:
                    fl_mid = f"{tokens[0]} {tokens[1]} {tokens[-1]}"
                    if fl_mid not in self.exact_map:
                        self.exact_map[fl_mid] = uid

            # 4. Email prefix
            if prefix and prefix not in self.email_prefix_map:
                self.email_prefix_map[prefix] = uid
            if clean_prefix and clean_prefix not in self.clean_map:
                self.clean_map[clean_prefix] = uid

            # 5. First name only
            if tokens and tokens[0] not in self.first_only_map:
                self.first_only_map[tokens[0]] = uid

            # 6. Collapsed repeated characters (e.g. "jittendra" -> "jitendra")
            col_full = _collapse_repeats(clean_str)
            if col_full and col_full not in self.collapsed_map:
                self.collapsed_map[col_full] = uid

            if len(tokens) >= 2:
                col_fl = _collapse_repeats(f"{tokens[0]}{tokens[-1]}")
                if col_fl and col_fl not in self.collapsed_map:
                    self.collapsed_map[col_fl] = uid

    def resolve(self, name_str: Optional[str]) -> Optional[str]:
        """
        Resolves a raw name string to a user UUID.
        Returns None if input is empty or unassigned.
        """
        if not name_str:
            return None

        raw = str(name_str).strip()
        if not raw or raw.lower() in ("unassigned", "none", "null", "nan", "", "-"):
            return None

        # Clean excess spaces and lowercase
        norm = re.sub(r"\s+", " ", raw).lower()

        # Step 0: Check known domain aliases first
        if norm in self.alias_map:
            target_alias = self.alias_map[norm]
            if target_alias in self.exact_map:
                return self.exact_map[target_alias]
            if target_alias in self.clean_map:
                return self.clean_map[target_alias]

        # Step 1: Direct exact match
        if norm in self.exact_map:
            return self.exact_map[norm]

        # Step 2: Handle slash or comma separated multiple names (e.g. "Hemant / Vaibhav")
        first_p = norm.replace(",", "/").split("/")[0].strip()
        if first_p in self.alias_map:
            target_alias = self.alias_map[first_p]
            if target_alias in self.exact_map:
                return self.exact_map[target_alias]
            if target_alias in self.clean_map:
                return self.clean_map[target_alias]

        if first_p in self.exact_map:
            return self.exact_map[first_p]

        # Step 3: Alphanumeric full string match
        clean_norm = re.sub(r"[^a-z0-9]", "", first_p)
        if clean_norm in self.clean_map:
            return self.clean_map[clean_norm]

        # Step 4: First Name + Last Name matching (middle name omission / addition)
        tokens = [w for w in re.sub(r"[^a-z0-9\s]", "", first_p).split() if w]
        if len(tokens) >= 2:
            fl = f"{tokens[0]} {tokens[-1]}"
            if fl in self.alias_map:
                target_alias = self.alias_map[fl]
                if target_alias in self.exact_map:
                    return self.exact_map[target_alias]

            if fl in self.first_last_map:
                return self.first_last_map[fl]
            if fl in self.exact_map:
                return self.exact_map[fl]

            fl_clean = f"{tokens[0]}{tokens[-1]}"
            if fl_clean in self.clean_fl_map:
                return self.clean_fl_map[fl_clean]
            if fl_clean in self.clean_map:
                return self.clean_map[fl_clean]

            # If input has 4+ words (e.g. "Hemant Kumar Singh Kashyap")
            if len(tokens) > 3:
                fl_mid = f"{tokens[0]} {tokens[1]} {tokens[-1]}"
                if fl_mid in self.exact_map:
                    return self.exact_map[fl_mid]

        # Step 5: Email prefix match
        if clean_norm in self.email_prefix_map:
            return self.email_prefix_map[clean_norm]

        # Step 6: First word only fallback (strictly for single word inputs or when unambiguous)
        if len(tokens) == 1 and tokens[0] in self.first_only_map:
            return self.first_only_map[tokens[0]]

        # Step 7: Collapsed repeated characters match (auto-heals typos like 'Jittendra' -> 'Jitendra')
        col_norm = _collapse_repeats(clean_norm)
        if col_norm in self.collapsed_map:
            return self.collapsed_map[col_norm]

        if len(tokens) >= 2:
            col_fl = _collapse_repeats(f"{tokens[0]}{tokens[-1]}")
            if col_fl in self.collapsed_map:
                return self.collapsed_map[col_fl]

        # Step 8: High-confidence fuzzy string matching (SequenceMatcher >= 0.88 with len diff <= 2)
        best_uid = None
        best_score = 0.0
        for cand_clean, cand_uid in self.clean_map.items():
            if abs(len(cand_clean) - len(clean_norm)) <= 2:
                sim = difflib.SequenceMatcher(None, clean_norm, cand_clean).ratio()
                if sim > best_score:
                    best_score = sim
                    best_uid = cand_uid

        if best_score >= 0.88 and best_uid:
            return best_uid

        return None

