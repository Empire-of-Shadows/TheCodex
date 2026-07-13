"""M1 - normalize Settings.GuildConfig to the current nested schema.

Background: the config code was collapsed to read only the current (nested)
schema and no longer migrates older documents on read or strips legacy fields
on save. With real data, any document still in an older shape would be read as
all-defaults. This one-time migration brings every document to the clean current
shape so the new code is correct.

For each guild config document it:
  - converts any Gen1/Gen2 layout (flat fields / `channels` map) to the current
    nested sections, using the exact pre-collapse conversion (see
    ``_guildconfig_v2``);
  - coerces ``roles.admin_role_ids`` / ``roles.mod_role_ids`` to ints;
  - removes the curated set of legacy fields, and the legacy ``roles.admin`` /
    ``roles.moderator`` sub-keys (via the full-``roles`` rewrite).

It only ever rewrites the structured sections and unsets known-legacy keys, so
any miscellaneous flat settings stored via ``set_setting`` are left untouched.

Idempotent: documents already in the clean current shape are skipped.

    python -m migrations.scripts.m1_normalize_guild_config           # dry run
    python -m migrations.scripts.m1_normalize_guild_config --apply
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args
from migrations.scripts._guildconfig_v2 import GuildConfig, _LEGACY_FIELDS

# The structured sections written back on migration (everything to_dict emits
# except guild_id / created_at / updated_at, which are preserved as-is).
_STRUCTURED_SECTIONS = (
    "roles", "server", "wyr", "new_members", "announcement", "tag_tracker",
    "drops", "suggestions", "boost", "guide", "embed",
    "setup_complete", "color_tiers_seeded",
)


def _int_ids(values):
    out = []
    for v in values or []:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def _needs_migration(doc: dict) -> bool:
    if any(k in doc for k in _LEGACY_FIELDS):
        return True
    roles = doc.get("roles") or {}
    if "admin" in roles or "moderator" in roles:
        return True
    for key in ("admin_role_ids", "mod_role_ids"):
        if any(isinstance(x, str) for x in (roles.get(key) or [])):
            return True
    wyr = doc.get("wyr")
    if not isinstance(wyr, dict) or "channel_id" not in wyr:
        return True  # not in the current nested shape
    return False


def main() -> int:
    args = parse_args(__doc__)
    client = connect()
    coll = client["Settings"]["GuildConfig"]

    docs = list(coll.find({}))
    print(f"Scanning {len(docs)} guild config document(s)...")
    changed = 0
    for doc in docs:
        if not _needs_migration(doc):
            continue

        clean = GuildConfig.from_dict(doc).to_dict()
        clean["roles"]["admin_role_ids"] = _int_ids(clean["roles"].get("admin_role_ids"))
        clean["roles"]["mod_role_ids"] = _int_ids(clean["roles"].get("mod_role_ids"))

        set_ops = {k: clean[k] for k in _STRUCTURED_SECTIONS}
        unset_ops = {f: "" for f in _LEGACY_FIELDS if f in doc}

        update: dict = {"$set": set_ops}
        if unset_ops:
            update["$unset"] = unset_ops

        gid = doc.get("guild_id")
        if args.apply:
            coll.update_one({"_id": doc["_id"]}, update)
            print(f"  migrated guild {gid}")
        else:
            print(f"  would migrate guild {gid}: unset={sorted(unset_ops)}")
        changed += 1

    verb = "Migrated" if args.apply else "Would migrate"
    print(f"{verb} {changed} of {len(docs)} document(s).")
    if not args.apply and changed:
        print("Dry run only - re-run with --apply to write changes.")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
