import type { UserActivity } from "../../api/types";
import AreaChart from "../charts/AreaChart";
import { Rule, Stat, Tile } from "./Tile";
import {
  formatCount,
  formatDate,
  formatDayCount,
  formatDayLabel,
  formatShortDate,
  statusColour,
} from "./format";

/**
 * The member home.
 *
 * Deliberately smaller than the admin view: one member of a small server does
 * not generate much, and the page should not pretend otherwise.
 */
export default function MemberOverview({ activity }: { activity: UserActivity }) {
  return (
    <div className="ov-grid">
      <YourVoting activity={activity} />
      <TagAndBoost activity={activity} />
      <YourSuggestions activity={activity} />
      <YourQuestions activity={activity} />
    </div>
  );
}

/* ── Your voting ───────────────────────────────────────────────────── */

function YourVoting({ activity }: { activity: UserActivity }) {
  const wyr = activity.wyr;
  const points = wyr.trend.map((point) => ({
    label: formatDayLabel(point.date),
    value: point.votes,
  }));

  return (
    <Tile
      span={8}
      title="Your voting"
      live
      chips={
        wyr.streak_days > 0 ? (
          <span className="ov-chip ov-chip--live">
            {wyr.streak_days} day streak
          </span>
        ) : (
          <span className="ov-chip">No streak right now</span>
        )
      }
    >
      <div className="ov-statrow">
        <Stat value={formatCount(wyr.total_votes)} label="Votes cast" />
        <Stat value={wyr.days_voted_30d} sub="/30" label="Days voted" />
        <Stat
          value={wyr.first_vote ? formatShortDate(wyr.first_vote) : "-"}
          label="First vote"
        />
      </div>
      <AreaChart
        points={points}
        ariaLabel="Your votes on the daily question for each of the last 30 days"
        unit="votes"
        emptyLabel="Vote on a few daily questions and your trend shows up here."
      />
    </Tile>
  );
}

/* ── Tag and boost ─────────────────────────────────────────────────── */

function TagAndBoost({ activity }: { activity: UserActivity }) {
  const tags = activity.tag_tracker;
  const boost = activity.boost;

  return (
    <Tile span={4} title="Server tag">
      {tags.length === 0 ? (
        <p className="ov-muted">No server here is tracking a tag.</p>
      ) : (
        tags.map((tag) => (
          <div key={tag.guild_id}>
            <div className="status-badges">
              <span className="tag-display">{tag.server_tag}</span>
              {tag.has_role === true && <span className="ov-chip ov-chip--good">Worn</span>}
              {tag.has_role === false && <span className="ov-chip">Not worn</span>}
              {tag.has_role === null && <span className="ov-chip">Not known</span>}
            </div>
            <p className="ov-muted">{tag.guild_name}</p>
          </div>
        ))
      )}

      <Rule />

      <span className="ov-card__title">Your boost</span>
      {boost.is_boosting ? (
        boost.boosts.map((entry) => (
          <p className="ov-body" key={entry.guild_id}>
            {entry.guild_name} · boosting since {formatDate(entry.boost_start)}
            {entry.duration_days !== null ? ` · ${formatDayCount(entry.duration_days)}` : ""}
          </p>
        ))
      ) : (
        <p className="ov-muted">You are not boosting any server right now.</p>
      )}
    </Tile>
  );
}

/* ── Your suggestions ──────────────────────────────────────────────── */

function YourSuggestions({ activity }: { activity: UserActivity }) {
  const suggestions = activity.suggestions;

  return (
    <Tile span={6} title="Your suggestions">
      <div className="ov-statrow">
        <Stat small value={formatCount(suggestions.submitted)} label="Sent in" />
        <Stat small value={formatCount(suggestions.votes_cast)} label="Votes you cast" />
      </div>
      {suggestions.items.length === 0 ? (
        <p className="ov-muted">
          You have not sent a suggestion in yet. Use the suggest command in Discord.
        </p>
      ) : (
        <div className="ov-queue">
          {suggestions.items.map((item) => (
            <div className="ov-qrow" key={item.suggestion_id}>
              <span
                className="ov-qrow__dot"
                style={{ background: statusColour(item.status) }}
              />
              <span className="ov-qrow__txt">{item.text || "Suggestion"}</span>
              <span className="ov-qrow__meta">
                {item.status} · {item.votes} up
              </span>
            </div>
          ))}
        </div>
      )}
    </Tile>
  );
}

/* ── Questions you sent in ─────────────────────────────────────────── */

function YourQuestions({ activity }: { activity: UserActivity }) {
  const submissions = activity.submissions;
  const latest = submissions.latest_posted;

  return (
    <Tile span={6} title="Questions you sent in">
      <div className="ov-statrow">
        <Stat small value={formatCount(submissions.sent)} label="Sent" />
        <Stat small value={formatCount(submissions.posted)} label="Posted" />
        <Stat small value={formatCount(submissions.waiting)} label="Waiting" />
        <Stat small value={formatCount(submissions.declined)} label="Not used" />
      </div>
      {submissions.sent === 0 ? (
        <p className="ov-muted">
          You have not sent a question in yet. Servers with submissions turned on take them from
          Discord.
        </p>
      ) : latest && latest.question_id !== null ? (
        <p className="ov-body">
          Your question Q{latest.question_id} went out
          {latest.posted_at ? ` on ${formatShortDate(latest.posted_at)}` : ""}
          {latest.votes !== null ? ` and got ${latest.votes} votes` : ""}.
        </p>
      ) : (
        <p className="ov-muted">None of your questions have been posted yet.</p>
      )}
    </Tile>
  );
}
