import Link from "next/link";
import { login } from "../auth-actions";

type SignInSearchParams = Promise<{ error?: string; message?: string }>;

export default async function SignIn({
  searchParams,
}: {
  searchParams: SignInSearchParams;
}) {
  const params = await searchParams;

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-8 md:px-8">
      <div className="page-orb left-[-4rem] top-10 h-44 w-44 bg-[rgba(210,136,66,0.18)]" />
      <div
        className="page-orb right-[-3rem] top-24 h-64 w-64 bg-[rgba(0,123,229,0.12)]"
        style={{ animationDelay: "1.4s" }}
      />

      <div className="relative mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl items-center">
        <div className="surface-card grid w-full overflow-hidden rounded-[34px] md:grid-cols-[1.05fr_0.95fr]">
          <section className="relative overflow-hidden bg-[linear-gradient(140deg,#f3ebe0_0%,#fffdf8_48%,#edf5ff_100%)] px-8 py-10 md:px-10 md:py-12">
            <div className="absolute -right-10 top-10 h-40 w-40 rounded-full bg-white/70 blur-2xl" />
            <div className="absolute bottom-0 left-0 h-48 w-48 rounded-full bg-[rgba(210,136,66,0.13)] blur-3xl" />

            <div className="relative max-w-xl">
              <span className="status-pill">Secure account access</span>
              <div className="mt-6 flex h-16 w-16 items-center justify-center rounded-[22px] bg-[var(--accent-primary)] text-2xl font-bold text-white glow-ring">
                F
              </div>
              <h1 className="mt-6 text-4xl font-semibold leading-tight text-[var(--text-primary)]">
                Welcome back to your finance workspace.
              </h1>
              <p className="mt-4 max-w-lg text-base leading-7 text-[var(--text-secondary)]">
                Sign in to continue with saved profile details, conversation
                history, and grounded insurance guidance from FinBot.
              </p>

              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                <div className="surface-card-strong rounded-[24px] p-5">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Personalized answers
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                    Use your onboarding details to shape more relevant responses.
                  </p>
                </div>
                <div className="surface-card-strong rounded-[24px] p-5">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Saved chat history
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                    Revisit previous compliance and insurance conversations any
                    time.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section className="bg-white/80 px-6 py-10 md:px-10 md:py-12">
            <div className="mx-auto max-w-md">
              <div>
                <p className="section-kicker">Sign in</p>
                <h2 className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">
                  Access your account
                </h2>
                <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                  Enter your email and password to continue to the chat
                  dashboard.
                </p>
              </div>

              {params?.error && (
                <div className="mt-6 rounded-[20px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {params.error}
                </div>
              )}

              {params?.message && (
                <div className="mt-6 rounded-[20px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  {params.message}
                </div>
              )}

              <form className="mt-8 space-y-5" action={login}>
                <div>
                  <label className="field-label" htmlFor="email">
                    Email address
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    className="app-input"
                    placeholder="you@example.com"
                  />
                </div>

                <div>
                  <label className="field-label" htmlFor="password">
                    Password
                  </label>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    className="app-input"
                    placeholder="Enter your password"
                  />
                </div>

                <button type="submit" className="primary-button w-full px-5 py-3.5">
                  Sign in to FinBot
                </button>
              </form>

              <div className="mt-8 rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-card-soft)] px-5 py-4 text-sm leading-6 text-[var(--text-secondary)]">
                Your account keeps profile answers, chat history, and document
                grounded responses tied to you only.
              </div>

              <div className="mt-6 text-sm text-[var(--text-secondary)]">
                Don&apos;t have an account?{" "}
                <Link
                  href="/sign-up"
                  className="font-semibold text-[var(--accent-primary)] hover:underline"
                >
                  Create one here
                </Link>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
