import { SurfaceState } from "../components/ui/surface-state";

export default function Loading() {
  return (
    <SurfaceState
      headingLevel={1}
      state="LOADING"
      title="Loading workspace"
      description="Preparing this view."
    />
  );
}
