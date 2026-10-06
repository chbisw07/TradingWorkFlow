import Link from "next/link";
import { notFound } from "next/navigation";
import { navigationSections } from "../../../components/shell/navigation";
export default async function PlannedPage({
  params,
}: {
  params: Promise<{ path: string[] }>;
}) {
  const { path } = await params;
  const href = "/" + path.join("/");
  const item = navigationSections
    .flatMap((section) => section.items)
    .find((item) => item.planned && item.href === href);
  if (!item) notFound();
  return (
    <section className="planned-workspace">
      <p className="eyebrow">WORKSPACE</p>
      <h1>{item.label}</h1>
      <p>Coming later</p>
      <p>This workspace is not available yet.</p>
      {(href === "/positions" || href === "/orders") && (
        <p>
          Account-specific {item.label.toLowerCase()} are available in{" "}
          <Link className="text-link" href="/brokers">
            Brokers
          </Link>
          .
        </p>
      )}
      <Link className="action-link" href="/scanners">
        Open Scanners
      </Link>
    </section>
  );
}
