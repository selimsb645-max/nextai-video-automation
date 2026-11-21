/**
 * Fonts load through @remotion/google-fonts so the render is identical on a
 * GitHub runner (which has almost no fonts installed) and on a laptop.
 */
import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";

export const anton = loadAnton("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily;
export const inter = loadInter("normal", { weights: ["400", "600", "800"], subsets: ["latin"] }).fontFamily;
