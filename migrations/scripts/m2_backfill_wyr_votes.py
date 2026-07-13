"""M2 - move per-user WYR votes out of the question document.

The WYR refactor moved per-user votes from ``Daily.WYR`` documents
(``guilds.{gid}.votes.{user_id}``) into the new ``Daily.WYR_Votes`` collection,
so the question document no longer grows unbounded. This one-time migration
backfills the existing votes into ``WYR_Votes`` and removes the embedded maps.

Without it, users who voted before the refactor would lose their "your pick"
highlight and would double-count if they re-vote (the new code, finding no vote
in ``WYR_Votes``, treats a re-vote as brand new).

The bounded ``guilds.{gid}.vote_counts`` aggregates are left in place - the new
code still reads them.

Idempotent and non-destructive: once a question's ``votes`` maps are removed it
is skipped, and the per-user backfill is insert-only (keyed on
(question_id, guild_id, user_id)), so re-runs never duplicate and a vote already
recorded by the live code is never overwritten. Safe to run before or after the
new code is deployed.

    python -m migrations.scripts.m2_backfill_wyr_votes           # dry run
    python -m migrations.scripts.m2_backfill_wyr_votes --apply
"""

from __future__ import annotations

from datetime import datetime, timezone

from migrations.scripts._common import connect, parse_args


def main() -> int:
    args = parse_args(__doc__)
    client = connect()
    questions = client["Daily"]["WYR"]
    votes = client["Daily"]["WYR_Votes"]
    now = datetime.now(timezone.utc)

    q_total = 0
    q_changed = 0
    v_total = 0
    for doc in questions.find({}):
        q_total += 1
        guilds = doc.get("guilds") or {}

        to_upsert = []          # (guild_id, user_id, option)
        unset_ops: dict = {}
        for gid, gdata in guilds.items():
            if not isinstance(gdata, dict):
                continue
            vote_map = gdata.get("votes")
            if not vote_map:
                continue
            for uid, option in vote_map.items():
                to_upsert.append((str(gid), str(uid), option))
            unset_ops[f"guilds.{gid}.votes"] = ""

        if not to_upsert:
            continue

        q_changed += 1
        v_total += len(to_upsert)
        qid = doc["_id"]

        if args.apply:
            for gid, uid, option in to_upsert:
                votes.update_one(
                    {"question_id": qid, "guild_id": gid, "user_id": uid},
                    {
                        # Insert-only: never overwrite a row already in WYR_Votes
                        # (e.g. a vote cast after the new code went live). We only
                        # backfill rows that don't exist yet, so M2 is safe to run
                        # before or after the new code is deployed.
                        "$setOnInsert": {
                            "question_id": qid, "guild_id": gid, "user_id": uid,
                            "option": option, "created_at": now, "updated_at": now,
                        },
                    },
                    upsert=True,
                )
            questions.update_one({"_id": qid}, {"$unset": unset_ops})
            print(f"  question {qid}: backfilled {len(to_upsert)} vote(s), "
                  f"cleared {len(unset_ops)} embedded map(s)")
        else:
            print(f"  question {qid}: would backfill {len(to_upsert)} vote(s), "
                  f"clear {len(unset_ops)} embedded map(s)")

    verb = "Backfilled" if args.apply else "Would backfill"
    print(f"{verb} {v_total} vote(s) across {q_changed} of {q_total} question(s).")
    if not args.apply and q_changed:
        print("Dry run only - re-run with --apply to write changes.")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
