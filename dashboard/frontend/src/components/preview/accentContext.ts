import { createContext } from "react";

/**
 * The colour a container takes when it sets none of its own.
 *
 * Discord draws an accent stripe only on a container, so a board's or a
 * greeting's top-level colour shows up as the stripe of each container that
 * has no colour of its own. The bot does exactly this
 * (utils/component_builders.py build_container); the preview mirrors it.
 * Undefined means no inherited colour (the guide, or a greeting with none set).
 */
export const InheritedAccentContext = createContext<string | number | undefined>(undefined);

/** The board's colour when none is set - mirrors _DEFAULT_ACCENT in Features/Board/board_renderer.py. */
export const BOARD_DEFAULT_ACCENT = "#4D0EB3";
