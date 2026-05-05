"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LanguageToggle } from "@/components/LanguageToggle";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useT, type TranslationKey } from "@/lib/i18n-context";
import type { RoleName, User } from "@/lib/types";

interface NavLink {
  href: string;
  labelKey: TranslationKey;
  roles?: RoleName[];
}

interface NavGroup {
  labelKey: TranslationKey;
  children: NavLink[];
}

type NavItem = NavLink | NavGroup;

const isGroup = (i: NavItem): i is NavGroup => "children" in i;

const NAV: NavItem[] = [
  { href: "/prompts", labelKey: "nav.prompts" },
  {
    labelKey: "nav.content",
    children: [
      { href: "/create", labelKey: "nav.single" },
      { href: "/library", labelKey: "nav.bulk" },
      { href: "/publish", labelKey: "nav.publish", roles: ["admin", "manager"] },
    ],
  },
  { href: "/users", labelKey: "nav.users", roles: ["admin", "manager"] },
  { href: "/errors", labelKey: "nav.errors", roles: ["admin", "manager"] },
  { href: "/settings", labelKey: "nav.settings", roles: ["admin"] },
  { href: "/docs", labelKey: "nav.docs" },
];

function visibleForRole(item: NavItem, role: RoleName): boolean {
  if (isGroup(item)) {
    return item.children.some((c) => !c.roles || c.roles.includes(role));
  }
  return !item.roles || item.roles.includes(role);
}

function isActive(href: string, pathname: string): boolean {
  return pathname === href || pathname.startsWith(href + "/");
}

export function Header({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const pathname = usePathname();
  const { t } = useT();
  const visible = NAV.filter((item) => visibleForRole(item, user.role.name));

  return (
    <header className="flex h-14 shrink-0 items-center gap-6 border-b border-neutral-200 bg-white px-5 dark:border-neutral-800 dark:bg-neutral-900">
      {/* Left: brand. flex-1 + min-w-0 lets it shrink while balancing the right side. */}
      <div className="flex min-w-0 flex-1 items-center">
        <Link
          href="/dashboard"
          className="truncate text-sm font-semibold text-neutral-900 dark:text-neutral-100"
        >
          {t("app.brand")}
        </Link>
      </div>

      {/* Center: nav links + groups. */}
      <nav className="flex shrink-0 items-center gap-1">
        {visible.map((item) =>
          isGroup(item) ? (
            <NavDropdown
              key={item.labelKey}
              group={item}
              role={user.role.name}
              pathname={pathname}
            />
          ) : (
            <NavPill
              key={item.href}
              href={item.href}
              labelKey={item.labelKey}
              active={isActive(item.href, pathname)}
            />
          ),
        )}
      </nav>

      {/* Right: theme + language + user + sign out. flex-1 mirrors the left so the center stays centered. */}
      <div className="flex flex-1 items-center justify-end gap-3">
        <LanguageToggle />
        <ThemeToggle />
        <div className="hidden text-right sm:block">
          <p className="truncate text-xs font-medium text-neutral-900 dark:text-neutral-100">
            {user.full_name ?? user.email}
          </p>
          <p className="truncate text-[10px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {user.role.name}
          </p>
        </div>
        <button
          onClick={onLogout}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {t("app.signOut")}
        </button>
      </div>
    </header>
  );
}

function pillClass(active: boolean) {
  return (
    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors " +
    (active
      ? "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
      : "text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100")
  );
}

function NavPill({
  href,
  labelKey,
  active,
}: {
  href: string;
  labelKey: TranslationKey;
  active: boolean;
}) {
  const { t } = useT();
  return (
    <Link href={href} className={pillClass(active)}>
      {t(labelKey)}
    </Link>
  );
}

function NavDropdown({
  group,
  role,
  pathname,
}: {
  group: NavGroup;
  role: RoleName;
  pathname: string;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const visibleChildren = group.children.filter(
    (c) => !c.roles || c.roles.includes(role),
  );
  const groupActive = visibleChildren.some((c) => isActive(c.href, pathname));

  // Close dropdown when route changes.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Click-outside to close.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapperRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={pillClass(groupActive) + " inline-flex items-center gap-1"}
      >
        {t(group.labelKey)}
        <svg
          aria-hidden
          viewBox="0 0 12 12"
          className={
            "h-3 w-3 transition-transform " + (open ? "rotate-180" : "")
          }
        >
          <path
            d="M2 4.5l4 4 4-4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full z-20 mt-1 min-w-[160px] overflow-hidden rounded-md border border-neutral-200 bg-white py-1 shadow-lg dark:border-neutral-800 dark:bg-neutral-900"
        >
          {visibleChildren.map((c) => {
            const active = isActive(c.href, pathname);
            return (
              <Link
                key={c.href}
                href={c.href}
                role="menuitem"
                className={
                  "block px-3 py-1.5 text-sm transition-colors " +
                  (active
                    ? "bg-neutral-100 font-medium text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                    : "text-neutral-700 hover:bg-neutral-50 hover:text-neutral-900 dark:text-neutral-300 dark:hover:bg-neutral-800 dark:hover:text-neutral-100")
                }
              >
                {t(c.labelKey)}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
