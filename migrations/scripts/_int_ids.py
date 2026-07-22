"""Shared int->str ID conversion helpers for the IS-4 normalization migrations (m5-m10).

Each migration declares, per collection, which fields hold Discord snowflake IDs and in
what shape (scalar, array of IDs, or array of subdocuments with an ID subfield). The
helpers here build the aggregation-pipeline updates so every document converts atomically
and idempotently: already-string values are untouched, ``None`` stays ``None``, and the
match query only selects documents that still carry an int-typed value, so a half-run
followed by a re-run is safe.

Not used for compound-``_id`` conversions (``_id`` is immutable) - see
``m7_updates_stats_guild_id_to_str`` for the copy-and-replace pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

_INT_TYPES = ["int", "long"]


def _conv_expr(path: str) -> Dict[str, Any]:
    """Expression: convert ``$<path>`` to string when it is int/long, else pass through."""
    return {
        "$cond": [
            {"$in": [{"$type": f"${path}"}, _INT_TYPES]},
            {"$toString": f"${path}"},
            f"${path}",
        ]
    }


def _elem_conv_expr(var: str) -> Dict[str, Any]:
    """Same conversion for a ``$$var`` bound inside a ``$map``."""
    return {
        "$cond": [
            {"$in": [{"$type": f"$${var}"}, _INT_TYPES]},
            {"$toString": f"$${var}"},
            f"$${var}",
        ]
    }


@dataclass(frozen=True)
class FieldSpec:
    """One ID-bearing field: ``kind`` is 'scalar', 'id_array', or 'subdoc_array'.

    ``subfield`` applies only to 'subdoc_array' (e.g. field='permissions',
    subfield='id' converts ``permissions[].id``).
    """
    field: str
    kind: str = "scalar"
    subfield: str = ""

    def match(self) -> Dict[str, Any]:
        """Query fragment matching docs where this field still holds int data."""
        if self.kind == "scalar":
            return {self.field: {"$type": _INT_TYPES}}
        if self.kind == "id_array":
            return {self.field: {"$elemMatch": {"$type": _INT_TYPES}}}
        if self.kind == "subdoc_array":
            return {self.field: {"$elemMatch": {self.subfield: {"$type": _INT_TYPES}}}}
        raise ValueError(f"Unknown FieldSpec kind: {self.kind}")

    def set_expr(self) -> Dict[str, Any]:
        """The ``$set`` expression converting this field (guarded, idempotent)."""
        if self.kind == "scalar":
            return _conv_expr(self.field)
        if self.kind == "id_array":
            return {
                "$cond": [
                    {"$isArray": f"${self.field}"},
                    {"$map": {"input": f"${self.field}", "as": "v",
                              "in": _elem_conv_expr("v")}},
                    f"${self.field}",
                ]
            }
        if self.kind == "subdoc_array":
            return {
                "$cond": [
                    {"$isArray": f"${self.field}"},
                    {"$map": {"input": f"${self.field}", "as": "d",
                              "in": {"$mergeObjects": [
                                  "$$d",
                                  {self.subfield: {
                                      "$cond": [
                                          {"$in": [{"$type": f"$$d.{self.subfield}"}, _INT_TYPES]},
                                          {"$toString": f"$$d.{self.subfield}"},
                                          f"$$d.{self.subfield}",
                                      ]
                                  }},
                              ]}}},
                    f"${self.field}",
                ]
            }
        raise ValueError(f"Unknown FieldSpec kind: {self.kind}")


def convert_collection(db, coll_name: str, specs: List[FieldSpec], apply: bool) -> int:
    """Dry-run report or apply the conversion for one collection. Returns docs needing it."""
    coll = db[coll_name]
    match = {"$or": [s.match() for s in specs]}
    total = coll.count_documents({})
    pending = coll.count_documents(match)
    fields = ", ".join(s.field + (f"[].{s.subfield}" if s.subfield else
                                  ("[]" if s.kind == "id_array" else ""))
                       for s in specs)
    print(f"{db.name}.{coll_name}: {total} doc(s); {pending} carry int IDs ({fields}).")
    if pending == 0:
        return 0
    if not apply:
        for d in coll.find(match).limit(3):
            print(f"  would convert _id={d.get('_id')}")
        return pending
    result = coll.update_many(match, [{"$set": {s.field: s.set_expr() for s in specs}}])
    remaining = coll.count_documents(match)
    print(f"  APPLIED: matched={result.matched_count} modified={result.modified_count}; "
          f"remaining int docs = {remaining} (should be 0).")
    return pending
