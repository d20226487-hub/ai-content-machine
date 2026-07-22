import type { Metadata } from "next";

/**
 * Shared previews must never be indexed. The token IS the credential, so a URL
 * that reaches a crawler is a leaked one — `noindex, nofollow` is part of the
 * feature's security posture, not a nicety.
 */
export const metadata: Metadata = {
  title: "Shared preview",
  robots: { index: false, follow: false, nocache: true },
};

export default function SharedPreviewLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
