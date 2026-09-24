import type { ReactNode } from "react";

type PanelProps = {
  id: string;
  title: string;
  eyebrow?: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
};

/** The body owns scrolling; children may measure it or host a virtualized surface. */
export function Panel({
  id,
  title,
  eyebrow,
  meta,
  children,
  className = "",
}: PanelProps) {
  return (
    <section className={`panel ${className}`} aria-labelledby={`${id}-title`}>
      <div className="panel-heading">
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h2 id={`${id}-title`}>{title}</h2>
        </div>
        {meta}
      </div>
      <div
        className="panel-body"
        tabIndex={0}
        role="region"
        aria-label={`${title} content`}
      >
        {children}
      </div>
    </section>
  );
}
