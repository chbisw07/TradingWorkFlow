const paths = {
  compass: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm4 5-3 5-5 3 3-5 5-3Z",
  portfolio: "M3 6h18v5H3V6Zm0 9h18v5H3v-5Zm4-6h1m-1 9h1M8 3h8v3",
  document: "M5 3h10l4 4v14H5V3Zm10 0v5h4M8 12h8m-8 4h5",
  target:
    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4a5 5 0 1 0 0 10 5 5 0 0 0 0-10Zm0 3v4m-2-2h4",
  nodes:
    "M9 5a2 2 0 1 0-4 0 2 2 0 0 0 4 0Zm10 0a2 2 0 1 0-4 0 2 2 0 0 0 4 0ZM9 19a2 2 0 1 0-4 0 2 2 0 0 0 4 0Zm10 0a2 2 0 1 0-4 0 2 2 0 0 0 4 0ZM7 7v4h10v6M17 7v4M7 17v-3",
  crosshair:
    "M12 2v5m0 10v5M2 12h5m10 0h5M12 5a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM9 9h6v6H9V9Z",
  news: "M3 4h18v16H3V4Zm0 4h18M6 11h5v6H6v-6Zm8 0h4m-4 3h4m-4 3h3",
  gear: "m10 3 4 0 1 3 3 1 2 3-2 2v3l-3 2-1 3h-4l-1-3-3-1-2-3 2-2V8l3-2 1-3ZM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z",
  tools:
    "m4 3 4 4-1 3-3 1-2-4m5 3 13 11m-2-18a5 5 0 0 0-5 6L3 19l2 2L15 11a5 5 0 0 0 6-5l-4 2-2-2 3-3Z",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "m6 6 12 12M6 18 18 6",
  search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6",
  chevron: "m6 9 6 6 6-6",
  home: "M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9",
  watchlists: "M5 4h14v17l-7-4-7 4V4Z",
  scanners: "M4 8V4h4m8 0h4v4M4 16v4h4m8 0h4v-4M7 12h10m-5-5v10",
  candidates: "M4 5h16v14H4V5Zm0 5h16m-10 0v9",
  positions: "M4 20V10h4v10m4 0V4h4v16m4 0V7",
  orders: "M5 5h14M5 12h14M5 19h9m2-3 4 3-4 3",
  alerts: "M6 9a6 6 0 0 1 12 0v6l2 3H4l2-3V9Zm4 12h4",
  consoles: "m5 7 5 5-5 5m8 0h6",
  history: "M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2",
  settings: "M4 7h16M4 17h16M8 4v6m8 4v6",
} as const;

export type IconName = keyof typeof paths;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
