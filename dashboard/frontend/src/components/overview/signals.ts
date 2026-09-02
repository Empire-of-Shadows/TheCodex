import type { GuildOverview, UserActivity } from "../../api/types";
import type { Signal } from "../../_engine/components/overview/SignalStrip";
import { formatCount } from "../../_engine/format";

/*
 * The command-row numbers.
 *
 * These used to live on the dashboard home, which was the only page drawing a
 * signal strip. Splitting one server's view out to its own page gave them two
 * callers - the home strip reads the member's activity across every server,
 * the per-guild overview reads that server's - so they moved here rather than
 * being written twice and drifting apart.
 */

/** The server-wide numbers an admin gets over their own server's overview. */
export function adminSignals(overview: GuildOverview): Signal[] {
  const signals: Signal[] = [];
  const members = overview.members;
  const wyr = overview.wyr;
  const trackers = overview.trackers;

  // null means "never snapshotted", which has to read differently from a real 0.
  signals.push({
    key: "members",
    value: members && members.total !== null ? formatCount(members.total) : "-",
    label: members && members.total !== null ? "Members" : "Members · not counted yet",
  });

  signals.push({
    key: "active",
    value: wyr ? formatCount(wyr.voters_30d) : "-",
    label: "Voted · 30 days",
  });

  const wearing = trackers?.tag.wearing ?? null;
  signals.push({
    key: "tag",
    value: wearing === null ? "-" : formatCount(wearing),
    label:
      !trackers || !trackers.tag.enabled
        ? "Wearing the tag · off"
        : wearing === null
          ? "Wearing the tag · not known"
          : "Wearing the tag",
  });

  signals.push({
    key: "boost",
    value: trackers ? formatCount(trackers.boost.count) : "-",
    label:
      trackers && trackers.boost.tier !== null
        ? `Boosting · level ${trackers.boost.tier}`
        : "Boosting",
  });

  return signals;
}

/** The member's own numbers, for whatever scope the activity payload covers. */
export function memberSignals(activity: UserActivity): Signal[] {
  return [
    { key: "votes", value: formatCount(activity.wyr.total_votes), label: "Votes cast" },
    { key: "streak", value: formatCount(activity.wyr.streak_days), label: "Day streak" },
    {
      key: "suggestions",
      value: formatCount(activity.suggestions.submitted),
      label: "Suggestions sent",
    },
  ];
}
