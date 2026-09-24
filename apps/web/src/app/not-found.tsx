import Link from "next/link";
import { SurfaceState } from "../components/ui/surface-state";

export default function NotFound() {
  return (
    <div className="route-state">
      <h1>Page not found</h1>
      <SurfaceState
        headingLevel={2}
        state="UNAVAILABLE"
        title="This view is not available"
        description="Return to the workspace overview to continue."
        action={
          <Link className="action-link" href="/">
            Back to workspace
          </Link>
        }
      />
    </div>
  );
}
