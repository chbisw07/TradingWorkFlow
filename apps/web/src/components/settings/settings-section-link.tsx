"use client";
import { useEffect } from "react";
import { useLocationHash } from "../shell/use-location-hash";
export function useSettingsSectionLink(section: string, ready: boolean) {
  const hash = useLocationHash();
  useEffect(() => {
    if (!ready || hash !== `#${section}`) return;
    const target = document.getElementById(section);
    const disclosure = target?.closest("details");
    if (disclosure) disclosure.open = true;
    const focus =
      target instanceof HTMLDetailsElement
        ? target.querySelector("summary")
        : target;
    focus?.focus({ preventScroll: true });
    target?.scrollIntoView({ block: "start" });
  }, [hash, section, ready]);
}
