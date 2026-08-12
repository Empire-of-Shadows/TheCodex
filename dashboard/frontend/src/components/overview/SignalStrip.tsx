import type { ReactNode } from "react";

export interface Signal {
  key: string;
  value: ReactNode;
  /** Short caption. Qualifiers such as "not counted yet" belong here. */
  label: string;
}

/**
 * The numbers that are only numbers.
 *
 * A figure with nothing to say beyond itself does not earn a tile, so it lives
 * in this strip instead.
 */
export default function SignalStrip({ signals }: { signals: Signal[] }) {
  if (signals.length === 0) return null;
  return (
    <div className="ov-signals">
      {signals.map((signal) => (
        <div className="ov-signal" key={signal.key}>
          <div className="ov-signal__v">{signal.value}</div>
          <div className="ov-signal__l">{signal.label}</div>
        </div>
      ))}
    </div>
  );
}
