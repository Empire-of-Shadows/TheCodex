import { Link } from "react-router-dom";
import type {
  ContentDoc,
  ContentOverview,
  DropsOverview,
  GuildOverview,
  MembersOverview,
  SuggestionsOverview,
  WyrOverview,
} from "../../api/types";
import AreaChart from "../../_engine/components/charts/AreaChart";
import BarChart, { type BarChartSeries } from "../../_engine/components/charts/BarChart";
import FeatureStrip, { featureCounts } from "../../_engine/components/overview/FeatureStrip";
import {
  KeyValue,
  Rule,
  SectionUnavailable,
  Stat,
  Tile,
} from "../../_engine/components/overview/Tile";
import {
  discordLink,
  formatAge,
  formatClock,
  formatCount,
  formatDateTime,
  formatDayLabel,
  formatMonthLabel,
  formatRelative,
  formatRunway,
  formatShortDate,
} from "../../_engine/format";
import { formatQuestionKind, orderedStatuses, statusColour } from "./format";

/** The admin home. Every section of the payload can be null on its own. */
export default function AdminOverview({ overview }: { overview: GuildOverview }) {
  const guildId = overview.guild_id;
  return (
    <div className="ov-grid">
      <IsItWorking overview={overview} />
      <TodaysQuestion guildId={guildId} wyr={overview.wyr} />
      <WaitingOnYou guildId={guildId} suggestions={overview.suggestions} wyr={overview.wyr} />
      <ServerContent guildId={guildId} content={overview.content} />
      <QuestionHealth guildId={guildId} wyr={overview.wyr} />
      <Suggestions suggestions={overview.suggestions} />
      <NewMembers guildId={guildId} members={overview.members} />
      <Drops guildId={guildId} drops={overview.drops} />
    </div>
  );
}

/* ── Is it working ─────────────────────────────────────────────────── */

function IsItWorking({ overview }: { overview: GuildOverview }) {
  const guildId = overview.guild_id;
  const counts = featureCounts(overview.features);
  return (
    <Tile
      span={12}
      title="Is it working"
      chips={
        <>
          {counts.on > 0 && <span className="ov-chip ov-chip--good">{counts.on} running</span>}
          {counts.needsSetup > 0 && (
            <span className="ov-chip ov-chip--warn">{counts.needsSetup} need setting up</span>
          )}
          {counts.off > 0 && <span className="ov-chip">{counts.off} off</span>}
        </>
      }
      action={
        <>
          <Link className="ov-link" to={`/settings/${guildId}`}>
            Change settings
          </Link>
          <Link className="ov-link" to={`/settings/${guildId}/audit-log`}>
            Change history
          </Link>
        </>
      }
    >
      <FeatureStrip guildId={guildId} features={overview.features} />
    </Tile>
  );
}

/* ── Today's question ──────────────────────────────────────────────── */

function TodaysQuestion({ guildId, wyr }: { guildId: string; wyr: WyrOverview | null }) {
  if (!wyr) {
    return (
      <Tile span={7} title="Today's question">
        <SectionUnavailable what="The daily question" />
      </Tile>
    );
  }

  if (!wyr.enabled) {
    return (
      <Tile
        span={7}
        title="Today's question"
        chips={<span className="ov-chip">Off</span>}
        action={
          <Link className="ov-link" to={`/settings/${guildId}?s=wyr`}>
            Turn it on
          </Link>
        }
      >
        <p className="ov-body">
          Daily questions are switched off, so nothing is being posted in this server.
        </p>
      </Tile>
    );
  }

  const today = wyr.today;
  if (!today) {
    return (
      <Tile
        span={7}
        title="Today's question"
        chips={<span className="ov-chip ov-chip--warn">Nothing posted yet</span>}
        action={
          <Link className="ov-link" to={`/settings/${guildId}?s=wyr`}>
            Posting schedule
          </Link>
        }
      >
        <p className="ov-body">No question has gone out today.</p>
        <p className="ov-muted">
          {wyr.next_post_at ? `Next post ${formatDateTime(wyr.next_post_at)}.` : "No next post scheduled."}
        </p>
      </Tile>
    );
  }

  // Both halves or no link: a message jump needs the channel and the message.
  // Discord opens the thread from the post when one exists, so this is right
  // whether or not thread creation succeeded.
  const postLink =
    today.channel_id && today.message_id
      ? `${discordLink(guildId, today.channel_id)}/${today.message_id}`
      : null;

  return (
    <Tile
      span={7}
      title="Today's question"
      live
      chips={
        today.posted_at ? (
          <span className="ov-chip ov-chip--live">Posted {formatClock(today.posted_at)}</span>
        ) : null
      }
      action={
        postLink ? (
          <a className="ov-link" href={postLink} target="_blank" rel="noopener noreferrer">
            View the post
          </a>
        ) : null
      }
    >
      <p className="ov-quote">{today.text || "This question has no text on record."}</p>
      <div className="ov-statrow">
        <Stat small value={formatCount(today.votes)} label="Votes" />
        <Stat small value={formatCount(today.voters)} label="People voting" />
        {today.question_id !== null && (
          <Stat small value={`Q${today.question_id}`} label="Question" />
        )}
        <Stat small value={formatQuestionKind(today.format)} label="Format" />
      </div>
      <Rule />
      <p className="ov-muted">
        {wyr.next_post_at ? `Next post ${formatDateTime(wyr.next_post_at)}.` : "No next post scheduled."}
      </p>
    </Tile>
  );
}

/* ── Waiting on you ────────────────────────────────────────────────── */

function WaitingOnYou({
  guildId,
  suggestions,
  wyr,
}: {
  guildId: string;
  suggestions: SuggestionsOverview | null;
  wyr: WyrOverview | null;
}) {
  const pending = suggestions?.pending ?? [];
  const reviews = wyr?.submissions_pending ?? 0;
  const waiting = pending.length + reviews;
  const shown = pending.slice(0, 5);

  return (
    <Tile
      span={5}
      title="Waiting on you"
      chips={
        waiting > 0 ? (
          <span className="ov-chip ov-chip--warn">{waiting} waiting</span>
        ) : (
          <span className="ov-chip ov-chip--good">Nothing waiting</span>
        )
      }
    >
      {suggestions === null && wyr === null ? (
        <SectionUnavailable what="Your queue" />
      ) : waiting === 0 ? (
        <p className="ov-muted">
          New suggestions and member questions appear here as they come in.
        </p>
      ) : (
        <div className="ov-queue">
          {shown.map((item) => (
            <a
              key={item.suggestion_id}
              className="ov-qrow"
              /* Land on the actual post when we can. A Discord message URL
                 needs the channel too, and only the guild's configured
                 suggestions channel supplies it - fall back to the server. */
              href={
                suggestions?.channel_id && item.message_id
                  ? `${discordLink(guildId, suggestions.channel_id)}/${item.message_id}`
                  : discordLink(guildId)
              }
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="ov-qrow__dot" style={{ background: statusColour("Pending") }} />
              <span className="ov-qrow__txt">{item.text || "Suggestion"}</span>
              <span className="ov-qrow__meta">
                {item.votes} up · {formatAge(item.created_at)}
              </span>
            </a>
          ))}
          {pending.length > shown.length && (
            <p className="ov-muted">and {pending.length - shown.length} more waiting</p>
          )}
          {reviews > 0 && (
            <a
              className="ov-qrow"
              href={discordLink(guildId)}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="ov-qrow__dot" style={{ background: "var(--text-accent)" }} />
              <span className="ov-qrow__txt">
                {reviews} member question{reviews === 1 ? "" : "s"} awaiting review
              </span>
              <span className="ov-qrow__meta">review</span>
            </a>
          )}
        </div>
      )}
      <Rule />
      <p className="ov-muted">
        This list is read-only. Approving and rejecting happen on the post in Discord, so two
        people cannot answer the same item twice.
      </p>
    </Tile>
  );
}

/* ── Server content ────────────────────────────────────────────────── */

function EditedLine({ doc, missing }: { doc: ContentDoc; missing: string }) {
  if (!doc.exists) return <p className="ov-muted">{missing}</p>;
  if (!doc.updated_at) return <p className="ov-muted">No edit recorded</p>;
  return (
    <p className="ov-muted">
      Edited {formatRelative(doc.updated_at)}
      {doc.updated_by ? ` by ${doc.updated_by}` : ""}
    </p>
  );
}

function ServerContent({ guildId, content }: { guildId: string; content: ContentOverview | null }) {
  if (!content) {
    return (
      <Tile span={7} title="Your server's own content">
        <SectionUnavailable what="Your guide, board and greeting" />
      </Tile>
    );
  }

  return (
    <Tile
      span={7}
      title="Your server's own content"
      action={
        <Link className="ov-link" to={`/builder/${guildId}`}>
          Open the builder
        </Link>
      }
    >
      <div className="ov-cols ov-cols--3">
        <div>
          <Stat small value={formatCount(content.guide.count)} label="Guide pages" />
          <EditedLine doc={content.guide} missing="No guide written yet" />
        </div>
        <div>
          <Stat small value={formatCount(content.board.count)} label="Board responses" />
          {content.board.posted_at ? (
            <p className="ov-muted">Posted {formatShortDate(content.board.posted_at)}</p>
          ) : (
            <EditedLine doc={content.board} missing="No board built yet" />
          )}
        </div>
        <div>
          <Stat small value={content.greeting.exists ? "Set" : "Not set"} label="Greeting message" />
          <EditedLine doc={content.greeting} missing="No greeting written yet" />
        </div>
      </div>
      <Rule />
      <p className="ov-body">
        This is the part of your server that outlives whoever wrote it. Anyone with access can
        edit these later, so a moderator leaving does not take the rules with them.
      </p>
      <div className="admin-actions">
        <Link className="btn btn-secondary" to={`/builder/${guildId}`}>
          Edit guide
        </Link>
        <Link className="btn btn-secondary" to={`/builder/${guildId}?mode=board`}>
          Edit board
        </Link>
        <Link className="btn btn-secondary" to={`/builder/${guildId}?mode=greeting`}>
          Edit greeting
        </Link>
      </div>
    </Tile>
  );
}

/* ── Daily question health ─────────────────────────────────────────── */

function QuestionHealth({ guildId, wyr }: { guildId: string; wyr: WyrOverview | null }) {
  if (!wyr) {
    return (
      <Tile span={5} title="Daily question health">
        <SectionUnavailable what="Question activity" />
      </Tile>
    );
  }

  const bank = wyr.bank;
  const available = bank.global + bank.guild;
  const left = Math.max(0, available - bank.used_here);
  const usedPercent = available > 0 ? Math.min(100, (bank.used_here / available) * 100) : 0;
  const points = wyr.trend.map((point) => ({
    label: formatDayLabel(point.date),
    value: point.votes,
  }));

  return (
    <Tile
      span={5}
      title="Daily question health"
      action={
        <Link className="ov-link" to={`/settings/${guildId}?s=wyr`}>
          Question settings
        </Link>
      }
    >
      <div className="ov-statrow">
        <Stat small value={wyr.avg_votes_per_day.toFixed(1)} label="Votes per day" />
        <Stat small value={formatCount(wyr.voters_30d)} label="People, 30 days" />
        <Stat small value={wyr.days_posted_30d} sub="/30" label="Days posted" />
      </div>
      <AreaChart
        points={points}
        ariaLabel="Votes on the daily question for each of the last 30 days"
        unit="votes"
        emptyLabel="No votes recorded yet, so there is no trend to draw."
      />
      <Rule />
      <div>
        <div className="ov-meter">
          <div className="ov-meter__fill" style={{ width: `${usedPercent}%` }} />
        </div>
        <p className="ov-muted">
          {formatCount(available)} questions available · {formatCount(bank.used_here)} used ·{" "}
          {formatRunway(left)}
        </p>
      </div>
      {bank.unpostable > 0 && (
        <p className="ov-muted">
          {formatCount(bank.unpostable)} of them are in a format this server does not post, so
          they can never appear.
        </p>
      )}
    </Tile>
  );
}

/* ── Suggestions ───────────────────────────────────────────────────── */

function Suggestions({ suggestions }: { suggestions: SuggestionsOverview | null }) {
  if (!suggestions) {
    return (
      <Tile span={4} title="Suggestions">
        <SectionUnavailable what="Suggestions" />
      </Tile>
    );
  }

  const statuses = orderedStatuses(suggestions.by_status);

  return (
    <Tile span={4} title="Suggestions">
      <Stat value={formatCount(suggestions.total)} label="Submitted all time" />
      {statuses.length === 0 ? (
        <p className="ov-muted">Nobody has sent a suggestion in yet.</p>
      ) : (
        <div>
          {statuses.map(([status, count]) => (
            <KeyValue key={status} k={status} v={formatCount(count)} />
          ))}
        </div>
      )}
    </Tile>
  );
}

/* ── New members ───────────────────────────────────────────────────── */

function NewMembers({ guildId, members }: { guildId: string; members: MembersOverview | null }) {
  if (!members) {
    return (
      <Tile span={4} title="New members">
        <SectionUnavailable what="Member counts" />
      </Tile>
    );
  }

  const groups = members.monthly.map((m) => formatMonthLabel(m.month));
  const series: BarChartSeries[] = [
    { key: "joined", label: "Joined", values: members.monthly.map((m) => m.joined) },
  ];

  return (
    <Tile
      span={4}
      title="New members, 30 days"
      action={
        <Link className="ov-link" to={`/settings/${guildId}?s=new_members`}>
          Screening
        </Link>
      }
    >
      <div className="ov-statrow">
        <Stat small value={formatCount(members.joined_30d)} label="Joined" />
        <Stat small value={formatCount(members.left_30d)} label="Left" />
        <Stat small value={formatCount(members.whitelisted)} label="Whitelisted" />
      </div>
      <BarChart
        groups={groups}
        series={series}
        ariaLabel="People who joined each month"
        unit="joined"
        emptyLabel="No joins recorded yet."
      />
      <Rule />
      <KeyValue
        k="Members"
        v={members.total === null ? "not counted yet" : formatCount(members.total)}
      />
      <KeyValue
        k="Counted"
        v={members.snapshot_at ? formatRelative(members.snapshot_at) : "never"}
      />
    </Tile>
  );
}

/* ── Drops ─────────────────────────────────────────────────────────── */

function Drops({ guildId, drops }: { guildId: string; drops: DropsOverview | null }) {
  if (!drops) {
    return (
      <Tile span={4} title="Drops posted">
        <SectionUnavailable what="Drops" />
      </Tile>
    );
  }

  if (!drops.enabled) {
    return (
      <Tile
        span={4}
        title="Drops posted"
        chips={<span className="ov-chip">Off</span>}
        action={
          <Link className="ov-link" to={`/settings/${guildId}?s=drops`}>
            Turn it on
          </Link>
        }
      >
        <p className="ov-body">Drops are switched off, so nothing is being posted.</p>
      </Tile>
    );
  }

  const groups = drops.monthly.map((m) => formatMonthLabel(m.month));
  const series: BarChartSeries[] = drops.categories.map((category) => ({
    key: category,
    label: category.charAt(0).toUpperCase() + category.slice(1),
    values: drops.monthly.map((m) => m.counts[category] ?? 0),
  }));

  return (
    <Tile
      span={4}
      title="Drops posted"
      action={
        <Link className="ov-link" to={`/settings/${guildId}?s=drops`}>
          Configure
        </Link>
      }
    >
      <div>
        <Stat value={formatCount(drops.this_month)} label="This month" />
        <p className="ov-muted">{formatCount(drops.all_time)} posted all time</p>
      </div>
      <BarChart
        groups={groups}
        series={series}
        ariaLabel="Drops posted each month, split by category"
        unit="drops"
        emptyLabel="No drops posted yet."
      />
    </Tile>
  );
}
