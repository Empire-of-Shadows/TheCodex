import type { UserEntitlements } from "../../api/types";
import { Rule, Stat, Tile } from "../../_engine/components/overview/Tile";

/**
 * "What you can use here" - the member's entitlements in the selected guild.
 *
 * Owner ruling 2026-08-12: show ALL entitlements, with bot-granted items
 * clearly labeled as status rather than something the member can act on.
 * Every section of the payload is independently nullable; a section that
 * failed simply does not render.
 */
export default function MemberEntitlements({
  entitlements,
}: {
  entitlements: UserEntitlements;
}) {
  return (
    <div className="ov-grid">
      <EmbedBuilder entitlements={entitlements} />
      <YourAccess entitlements={entitlements} />
    </div>
  );
}

/* ── The embed builder - the detailed half ─────────────────────────── */

function EmbedBuilder({ entitlements }: { entitlements: UserEntitlements }) {
  const embed = entitlements.embed;
  if (!embed) return null;

  if (!embed.enabled) {
    return (
      <Tile span={7} title="Embed builder">
        <p className="ov-muted">The embed builder is not set up on this server.</p>
      </Tile>
    );
  }

  return (
    <Tile
      span={7}
      title="Embed builder"
      chips={
        embed.access ? (
          <span className="ov-chip ov-chip--good">You can use it</span>
        ) : (
          <span className="ov-chip">Not available to you</span>
        )
      }
    >
      {embed.tiers.length > 0 && (
        <p className="ov-muted">
          Your tier{embed.tiers.length === 1 ? "" : "s"}: {embed.tiers.join(", ")}
        </p>
      )}

      <div className="status-badges">
        {embed.features.map((feature) => (
          <span
            key={feature.key}
            className={feature.available ? "ov-chip ov-chip--good" : "ov-chip"}
            title={
              feature.restricted
                ? feature.available
                  ? "Granted by your roles"
                  : "Restricted to specific roles here"
                : "Open to everyone here"
            }
          >
            {feature.label}
            {feature.available ? "" : " · locked"}
          </span>
        ))}
      </div>

      <Rule />

      <span className="ov-card__title">Your colours</span>
      {embed.colors.mode === "free" ? (
        <p className="ov-body">
          Any colour - this server gives everyone free colour access. Type any hex
          code when you build an embed.
        </p>
      ) : embed.colors.mode === "palette" ? (
        embed.colors.sets.map((set) => (
          <div key={set.name}>
            <p className="ov-muted">{set.name}</p>
            <div className="status-badges">
              {Object.entries(set.colors).map(([name, hex]) => (
                <span key={name} className="ov-chip" title={hex}>
                  <span
                    aria-hidden
                    style={{
                      display: "inline-block",
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      background: hex,
                      marginRight: 6,
                      verticalAlign: "middle",
                    }}
                  />
                  {name}
                </span>
              ))}
            </div>
          </div>
        ))
      ) : (
        <p className="ov-muted">
          Colours here are tied to roles, and none are assigned to yours yet - your
          embeds post with the server default
          {embed.colors.default_color ? ` (${embed.colors.default_color})` : ""}.
        </p>
      )}

      <Rule />

      <div className="ov-statrow">
        <Stat
          small
          value={embed.description_limit.toLocaleString()}
          label="Description characters"
        />
      </div>
      <p className="ov-muted">
        You can re-edit an embed you posted for one hour after posting it.
      </p>
    </Tile>
  );
}

/* ── Everything else - capabilities, self-serve, status ────────────── */

function YourAccess({ entitlements }: { entitlements: UserEntitlements }) {
  const { capabilities, self_serve, status, submissions, roles_unavailable } = entitlements;
  if (!capabilities && !self_serve && !status && !submissions) return null;

  return (
    <Tile span={5} title="Your access here">
      {/* Everything in this tile is worked out from the member's roles. If those
          could not be read they all read as "no", which is a lie stated as fact -
          so say it once, at the top, before any of it. */}
      {roles_unavailable && (
        <p className="ov-body">
          <span className="ov-chip ov-chip--warn">Could not check your roles</span>{" "}
          We could not reach Discord to see which roles you have, so anything below
          that depends on them may be wrong. Try again in a minute.
        </p>
      )}
      {capabilities && (
        <>
          {capabilities.map((capability) => (
            <p className="ov-body" key={capability.key}>
              {capability.label}
              {" · "}
              {capability.granted ? (
                <span className="ov-chip ov-chip--good">Yes</span>
              ) : (
                <span className="ov-chip">No</span>
              )}
            </p>
          ))}
          <Rule />
        </>
      )}

      {self_serve && (
        <>
          <span className="ov-card__title">Yours to switch</span>
          {self_serve.wyr_ping.available ? (
            <p className="ov-body">
              Daily question ping ·{" "}
              {self_serve.wyr_ping.subscribed ? (
                <span className="ov-chip ov-chip--good">Subscribed</span>
              ) : (
                <span className="ov-chip">Not subscribed</span>
              )}
            </p>
          ) : (
            <p className="ov-muted">No daily question ping is set up here.</p>
          )}
          {self_serve.toggle_roles.map((role) => (
            <p className="ov-body" key={`${role.source}-${role.role_id}`}>
              {role.name ?? `Role ${role.role_id}`}
              <span className="ov-muted">
                {" "}
                · from the {role.source === "board" ? "info board" : "server guide"}
              </span>{" "}
              {role.held ? (
                <span className="ov-chip ov-chip--good">You have it</span>
              ) : (
                <span className="ov-chip">Available</span>
              )}
            </p>
          ))}
          <Rule />
        </>
      )}

      {status && (
        <>
          <span className="ov-card__title">Status (set by the bot)</span>
          <p className="ov-body">
            New-member screening ·{" "}
            {status.screening_whitelisted || status.whitelist_role_held ? (
              <span className="ov-chip ov-chip--good">Whitelisted</span>
            ) : (
              <span className="ov-chip">Standard</span>
            )}
          </p>
        </>
      )}

      {submissions && submissions.enabled && (
        <p className="ov-body">
          Question submissions · {submissions.pending}/{submissions.max} waiting
          slots used
        </p>
      )}
    </Tile>
  );
}
