"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function PublishIndex() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/publish/autotool");
  }, [router]);
  return null;
}
