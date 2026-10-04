const paths = {
  panelLeft: 'M3 3h18v18H3z M9 3v18',
  plus: 'M12 5v14 M5 12h14',
  search: 'M10.5 3a7.5 7.5 0 1 0 0 15a7.5 7.5 0 0 0 0-15 M16 16l5 5',
  chat: 'M4 4h16v12H9l-5 4z',
  folder: 'M3 5h6l2 3h10v12H3z',
  folderOpen: 'M3 8V5h6l2 3h10 M3 8h18l-3 12H3z',
  chevronDown: 'M6 9l6 6l6-6',
  chevronRight: 'M9 6l6 6l-6 6',
  chevronUp: 'M6 15l6-6l6 6',
  git: 'M6 3a2 2 0 1 0 0 4a2 2 0 0 0 0-4 M6 17a2 2 0 1 0 0 4a2 2 0 0 0 0-4 M18 3a2 2 0 1 0 0 4a2 2 0 0 0 0-4 M6 7v10 M18 7v3c0 4-12 2-12 7',
  history: 'M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v5l3 2',
  puzzle: 'M4 4h5a3 3 0 1 1 6 0h5v5a3 3 0 1 0 0 6v5h-5a3 3 0 1 0-6 0H4v-5a3 3 0 1 1 0-6z',
  layers: 'M12 3l10 6l-10 6L2 9z M2 13l10 6l10-6 M2 17l10 6l10-6',
  settings: 'M9 3h6l1 3l3 1l2 5l-2 5l-3 1l-1 3H9l-1-3l-3-1l-2-5l2-5l3-1z M12 8a4 4 0 1 0 0 8a4 4 0 0 0 0-8',
  code: 'M8 6l-6 6l6 6 M16 6l6 6l-6 6 M14 3l-4 18',
  terminal: 'M3 4h18v16H3z M6 8l4 4l-4 4 M13 16h5',
  close: 'M6 6l12 12 M18 6L6 18',
  check: 'M4 12l5 5L20 6',
  more: 'M4 12h.01 M12 12h.01 M20 12h.01',
  edit: 'M4 16L16 4l4 4L8 20H4z M13 7l4 4',
  trash: 'M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7',
  arrowUp: 'M12 20V4 M5 11l7-7l7 7',
  stop: 'M6 6h12v12H6z',
  microphone: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0z M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M8 22h8',
  monitor: 'M3 3h18v14H3z M12 17v4 M7 21h10',
  shield: 'M12 2l9 4v6c0 5-5 8-9 10c-4-2-9-5-9-10V6z M8 12l3 3l5-6',
  paperclip: 'M8 13l8-8a4 4 0 0 1 6 6L11 22a6 6 0 0 1-8-8L13 4 M6 17l11-11',
  copy: 'M8 8h13v13H8z M16 8V3H3v13h5',
  refresh: 'M20 9a8 8 0 0 0-14-4L3 8 M3 3v5h5 M4 15a8 8 0 0 0 14 4l3-3 M16 16h5v5',
  external: 'M14 3h7v7 M21 3L10 14 M10 3H3v18h18v-7',
  activity: 'M2 12h5l3-9l4 18l3-9h5',
  globe: 'M12 2a10 10 0 1 0 0 20a10 10 0 0 0 0-20 M2 12h20 M12 2c-6 6-6 14 0 20c6-6 6-14 0-20',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
  file: 'M4 2h10l6 6v14H4z M14 2v6h6 M8 13h8 M8 17h6',
  sparkles: 'M12 2l3 7l7 3l-7 3l-3 7l-3-7l-7-3l7-3z',
} satisfies Record<string, string>;

export type AppIconName = keyof typeof paths;

interface AppIconProps {
  name: AppIconName;
  size?: number;
  className?: string;
}

export function AppIcon({ name, size = 20, className }: AppIconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false" className={className}>
      <path d={paths[name]} />
    </svg>
  );
}
