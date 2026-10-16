# TWF Visual Design Language v1

**Status:** Current production workspace baseline, 16 October 2026. The existing Scanner is the visual reference. This document governs presentation, not trading authority or data contracts.

## Color and tokens

The default workstation canvas is white with a soft neutral background. Blue carries structure and interaction: active navigation and tabs, selected cards, primary actions, links, informational badges, and filter chips. The shared `--twf-*` variables in `apps/web/src/styles/tokens.css` define the primary/hover blues, pale-blue surfaces, borders, canvas, text, and semantic colors. Components should use these tokens rather than introduce isolated hex colors.

Green and red are reserved for meaningful facts such as profit/loss, up/down movement, connected/error status, and buy/sell intent. Amber signals warning or attention; grey signals neutral, unavailable, or disabled states. Labels and icons must convey the state without relying on color alone. A row is not colored green merely because it represents an open position. The existing optional dark theme remains available; no new dark-mode feature is part of v1.

## Workstation layout

Trade, Scanners, Brokers, Watchlists, and Options Analytics begin with operational controls and content. Their redundant full-width visible page-title/subtitle banners are removed. Each retains a screen-reader page heading. Utility actions displaced by a banner belong in a compact toolbar or Settings/Integrations; Scanner and Options Analytics keep a visible Provider connections link.

Compact top rows place mode or section tabs on the left and context selection plus primary action on the right. Controls may wrap at medium widths. At 390px, essential tabs and actions remain reachable; dense data tables may scroll within their own container, never by clipping actions.

## Components

- **Tables:** white body rows, pale-blue headers, subtle neutral borders, pale-blue hover and stronger selected states. Align numeric columns consistently. Use green/red only on semantic values.
- **Tabs:** compact height, dark readable text, pale-blue active surface, blue underline, and an accessible current/selected attribute.
- **Buttons:** primary actions use solid blue and white text; secondary actions use white with blue border/text. Destructive disconnect and sell actions retain semantic red. Disabled states remain legible.
- **Chips and badges:** default informational chips are pale blue with blue border/text. Success, error, warning, and neutral states use their respective semantic tokens and explicit text.
- **Focus:** visible blue outline, keyboard-reachable controls, descriptive labels, and no color-only distinction.

The established Scanner density guides spacing across Trade and Brokers. Actual data, existing lifecycle states, Queue ordering, Broker actions, and execution boundaries remain authoritative.
