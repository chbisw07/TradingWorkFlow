const paths = {
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
