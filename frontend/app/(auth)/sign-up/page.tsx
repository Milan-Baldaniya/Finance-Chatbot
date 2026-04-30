import Link from "next/link";
import { signup } from "../auth-actions";

type SignUpSearchParams = Promise<{ error?: string }>;

export default async function SignUp({
  searchParams,
}: {
  searchParams: SignUpSearchParams;
}) {
  const params = await searchParams;

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-8 md:px-8">
      <div className="page-orb left-[-4rem] top-16 h-44 w-44 bg-[rgba(0,123,229,0.14)]" />
      <div
        className="page-orb right-[-4rem] top-8 h-72 w-72 bg-[rgba(210,136,66,0.16)]"
        style={{ animationDelay: "1.2s" }}
      />

      <div className="relative mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl items-center">
        <div className="surface-card grid w-full overflow-hidden rounded-[34px] md:grid-cols-[1fr_1fr]">
          <section className="relative overflow-hidden bg-[linear-gradient(155deg,#eef5f2_0%,#fffef9_46%,#f3e8d8_100%)] px-8 py-10 md:px-10 md:py-12">
            <div className="absolute right-0 top-0 h-52 w-52 rounded-full bg-white/75 blur-3xl" />
            <div className="absolute bottom-0 left-0 h-56 w-56 rounded-full bg-[rgba(0,123,229,0.12)] blur-3xl" />

            <div className="relative max-w-xl">
              <span className="status-pill">New account setup</span>
              <h1 className="mt-6 text-4xl font-semibold leading-tight text-[var(--text-primary)]">
                Create your account and start with a cleaner setup.
              </h1>
              <p className="mt-4 max-w-lg text-base leading-7 text-[var(--text-secondary)]">
                After sign up, we will ask a short onboarding form so the chatbot
                can answer insurance questions more carefully and accurately for
                your situation.
              </p>

              <div className="mt-8 space-y-4">
                <div className="surface-card-strong rounded-[24px] p-5">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Step 1
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                    Create your secure account with email and password.
                  </p>
                </div>
                <div className="surface-card-strong rounded-[24px] p-5">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Step 2
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                    Complete your insurance profile once so answers can be more
                    relevant.
                  </p>
                </div>
                <div className="surface-card-strong rounded-[24px] p-5">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Step 3
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                    Chat with saved history, citations, and user-specific context.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section className="bg-white/84 px-6 py-10 md:px-10 md:py-12">
            <div className="mx-auto max-w-md">
              <div>
                <p className="section-kicker">Create account</p>
                <h2 className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">
                  Get Started
                </h2>
                <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                  Set up your login details first. Onboarding comes right after
                  this.
                </p>
              </div>

              {params?.error && (
                <div className="mt-6 rounded-[20px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {params.error}
                </div>
              )}

              <form className="mt-8 space-y-5" action={signup}>
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
                    autoComplete="new-password"
                    required
                    minLength={6}
                    className="app-input"
                    placeholder="Create a password"
                  />
                </div>

                <div>
                  <label className="field-label" htmlFor="confirmPassword">
                    Confirm password
                  </label>
                  <input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={6}
                    className="app-input"
                    placeholder="Repeat your password"
                  />
                </div>

                <button type="submit" className="primary-button w-full px-5 py-3.5">
                  Create account
                </button>
              </form>

              <div className="mt-8 rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-card-soft)] px-5 py-4 text-sm leading-6 text-[var(--text-secondary)]">
                We only use your onboarding answers to improve relevance, store
                chat history by account, and keep responses tailored to your
                needs.
              </div>

              <div className="mt-6 text-sm text-[var(--text-secondary)]">
                Already have an account?{" "}
                <Link
                  href="/sign-in"
                  className="font-semibold text-[var(--accent-primary)] hover:underline"
                >
                  Sign in instead
                </Link>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
