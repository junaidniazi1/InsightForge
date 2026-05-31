import Link from "next/link";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { SignOutButton } from "./sign-out-button";
import { ThemeToggle } from "./theme-toggle";

export async function Nav() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = await supabase.auth.getUser();

  return (
    <header className="border-b border-[var(--color-border)] bg-[var(--color-panel)]/80 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <Link
          href="/"
          className="text-lg font-semibold tracking-tight text-[var(--color-fg)]"
        >
          InsightForge
        </Link>
        <nav className="flex items-center gap-3 text-sm">
          {user ? (
            <>
              <Link
                href="/sources"
                className="text-[var(--color-muted)] transition-colors hover:text-[var(--color-fg)]"
              >
                Sources
              </Link>
              <Link
                href="/connections"
                className="text-[var(--color-muted)] transition-colors hover:text-[var(--color-fg)]"
              >
                Connections
              </Link>
              <span className="hidden text-[var(--color-muted)] sm:inline">
                {user.email}
              </span>
              <ThemeToggle />
              <SignOutButton />
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="text-[var(--color-muted)] transition-colors hover:text-[var(--color-fg)]"
              >
                Log in
              </Link>
              <Link
                href="/signup"
                className="text-[var(--color-accent)] transition-colors hover:text-[var(--color-accent-strong)] hover:underline"
              >
                Sign up
              </Link>
              <ThemeToggle />
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
