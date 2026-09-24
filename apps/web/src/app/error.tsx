"use client";

import Link from "next/link";
import { SurfaceState } from "../components/ui/surface-state";

export default function ErrorView({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="route-state">
      <h1>Workspace unavailable</h1>
      <SurfaceState
        headingLevel={2}
        state="ERROR"
        title="Something interrupted this view"
        description="Try loading the view again. Your trading authority has not changed."
        action={
          <>
            <button className="action-link" type="button" onClick={reset}>
              Try again
            </button>
            <Link className="text-link" href="/">
              Back to workspace
            </Link>
          </>
        }
      />
    </div>
  );
}
