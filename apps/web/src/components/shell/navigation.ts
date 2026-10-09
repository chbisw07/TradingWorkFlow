import type { IconName } from "./icon";

export type NavigationItem = {
  label: string;
  href: string;
  icon: IconName;
  planned?: boolean;
};
export const navigationSections: { label: string; items: NavigationItem[] }[] =
  [
    {
      label: "WORKSPACE",
      items: [
        { label: "Home", href: "/", icon: "home" },
        { label: "Brokers", href: "/brokers", icon: "positions" },
        {
          label: "Market Overview",
          href: "/market-overview",
          icon: "positions",
          planned: true,
        },
        { label: "Scanners", href: "/scanners", icon: "scanners" },
        { label: "Discovery", href: "/candidates", icon: "compass" },
        {
          label: "Watchlists",
          href: "/watchlists",
          icon: "watchlists",
        },
        {
          label: "Positions",
          href: "/positions",
          icon: "portfolio",
          planned: true,
        },
        { label: "Orders", href: "/orders", icon: "document", planned: true },
        { label: "Alerts", href: "/alerts", icon: "alerts", planned: true },
      ],
    },
    {
      label: "TOOLS",
      items: [
        {
          label: "Options Analytics",
          href: "/options-analytics",
          icon: "target",
        },
        {
          label: "Strategy Builder",
          href: "/strategy-builder",
          icon: "nodes",
          planned: true,
        },
        {
          label: "Risk & Greeks",
          href: "/risk-greeks",
          icon: "crosshair",
          planned: true,
        },
      ],
    },
    {
      label: "INSIGHTS",
      items: [
        {
          label: "Market Intelligence",
          href: "/market-intelligence",
          icon: "document",
          planned: true,
        },
        {
          label: "News & Events",
          href: "/news-events",
          icon: "news",
          planned: true,
        },
      ],
    },
    {
      label: "SETTINGS",
      items: [
        { label: "Preferences", href: "/settings#preferences", icon: "gear" },
        {
          label: "Integrations",
          href: "/settings#integrations",
          icon: "nodes",
        },
        { label: "Advanced", href: "/settings#advanced", icon: "tools" },
      ],
    },
  ];
