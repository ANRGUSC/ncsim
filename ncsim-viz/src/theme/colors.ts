export const NODE_COLORS = [
  '#00ffcc', // cyan
  '#ff00ff', // magenta
  '#ffd700', // yellow
  '#00ff88', // green
  '#ff6633', // orange
  '#7c7cff', // periwinkle
  '#ff69b4', // pink
  '#40e0d0', // turquoise
] as const;

export const NODE_COLORS_LIGHT = [
  '#0891b2', // cyan
  '#a855f7', // purple
  '#d97706', // amber
  '#16a34a', // green
  '#ea580c', // orange
  '#4f46e5', // indigo
  '#ec4899', // pink
  '#0d9488', // teal
] as const;

export function nodeColor(index: number, isDark: boolean): string {
  const palette = isDark ? NODE_COLORS : NODE_COLORS_LIGHT;
  return palette[index % palette.length];
}
