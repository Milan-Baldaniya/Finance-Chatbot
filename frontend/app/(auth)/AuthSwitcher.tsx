'use client'

import { useState } from 'react'

type AuthMode = 'sign-in' | 'sign-up'

type AuthSwitcherProps = {
  initialMode: AuthMode
  error?: string
  message?: string
  loginAction: (formData: FormData) => void | Promise<void>
  signupAction: (formData: FormData) => void | Promise<void>
}

export function AuthSwitcher({
  initialMode,
  error,
  message,
  loginAction,
  signupAction,
}: AuthSwitcherProps) {
  const [mode, setMode] = useState<AuthMode>(initialMode)
  const isSignUp = mode === 'sign-up'

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-8 md:px-8">
      <div className="page-orb left-[-4rem] top-10 h-44 w-44 bg-[rgba(0,123,229,0.14)]" />
      <div
        className="page-orb right-[-4rem] top-12 h-72 w-72 bg-[rgba(210,136,66,0.16)]"
        style={{ animationDelay: '1.2s' }}
      />

      <div className="relative mx-auto flex min-h-[calc(100vh-4rem)] max-w-6xl items-start md:items-center">
        <div className="surface-card relative grid w-full overflow-hidden rounded-[34px] bg-white/88 md:min-h-[640px] md:grid-cols-2">
          <div
            className={`order-1 overflow-hidden bg-white/88 px-6 transition-all duration-700 ease-[cubic-bezier(0.4,0,0.2,1)] md:absolute md:inset-y-0 md:left-0 md:order-none md:flex md:max-h-none md:w-1/2 md:translate-y-0 md:items-center md:overflow-visible md:px-10 md:py-12 ${
              isSignUp
                ? 'max-h-[820px] translate-y-0 py-10 opacity-100 md:z-20 md:translate-x-full md:opacity-100'
                : 'max-h-0 -translate-y-6 py-0 opacity-0 pointer-events-none md:z-10 md:translate-x-0 md:opacity-0'
            }`}
          >
            <div className="mx-auto w-full max-w-md">
              <p className="section-kicker">Sign up</p>
              <h2 className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">
                Get Started
              </h2>
              <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                Set up your login details first. Onboarding comes right after this.
              </p>

              {isSignUp && error && (
                <div className="mt-6 rounded-[20px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <form className="mt-8 space-y-5" action={signupAction}>
                <div>
                  <label className="field-label" htmlFor="signup-email">
                    Email address
                  </label>
                  <input
                    suppressHydrationWarning
                    id="signup-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    className="app-input"
                    placeholder="you@example.com"
                  />
                </div>

                <div>
                  <label className="field-label" htmlFor="signup-password">
                    Password
                  </label>
                  <input
                    suppressHydrationWarning
                    id="signup-password"
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
                    suppressHydrationWarning
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

                <button
                  suppressHydrationWarning
                  type="submit"
                  className="primary-button w-full bg-[var(--accent-primary)] px-5 py-3.5 text-white"
                >
                  Sign up
                </button>
              </form>

              <button
                type="button"
                className="mt-6 text-sm font-semibold text-[var(--accent-primary)] hover:underline md:hidden"
                onClick={() => setMode('sign-in')}
              >
                Already have an account? Sign in
              </button>
            </div>
          </div>

          <div
            className={`order-1 overflow-hidden bg-white/88 px-6 transition-all duration-700 ease-[cubic-bezier(0.4,0,0.2,1)] md:absolute md:inset-y-0 md:left-0 md:order-none md:flex md:max-h-none md:w-1/2 md:translate-y-0 md:items-center md:overflow-visible md:px-10 md:py-12 ${
              isSignUp
                ? 'max-h-0 translate-y-6 py-0 opacity-0 pointer-events-none md:z-10 md:translate-x-full md:opacity-0'
                : 'max-h-[680px] translate-y-0 py-10 opacity-100 md:z-20 md:translate-x-0 md:opacity-100'
            }`}
          >
            <div className="mx-auto w-full max-w-md">
              <p className="section-kicker">Sign in</p>
              <h2 className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">
                Access your account
              </h2>
              <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                Enter your email and password to continue to the chat dashboard.
              </p>

              {!isSignUp && error && (
                <div className="mt-6 rounded-[20px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              {!isSignUp && message && (
                <div className="mt-6 rounded-[20px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  {message}
                </div>
              )}

              <form className="mt-8 space-y-5" action={loginAction}>
                <div>
                  <label className="field-label" htmlFor="signin-email">
                    Email address
                  </label>
                  <input
                    suppressHydrationWarning
                    id="signin-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    className="app-input"
                    placeholder="you@example.com"
                  />
                </div>

                <div>
                  <label className="field-label" htmlFor="signin-password">
                    Password
                  </label>
                  <input
                    suppressHydrationWarning
                    id="signin-password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    className="app-input"
                    placeholder="Enter your password"
                  />
                </div>

                <button
                  suppressHydrationWarning
                  type="submit"
                  className="primary-button w-full px-5 py-3.5"
                >
                  Sign in
                </button>
              </form>

              <button
                type="button"
                className="mt-6 text-sm font-semibold text-[var(--accent-primary)] hover:underline md:hidden"
                onClick={() => setMode('sign-up')}
              >
                Don&apos;t have an account? Sign up
              </button>
            </div>
          </div>

          <section
            className={`order-2 min-h-[340px] overflow-hidden bg-[linear-gradient(145deg,#e9f6ff_0%,#f4fbff_48%,#dcf0ff_100%)] px-6 pb-12 pt-8 transition-transform duration-700 ease-[cubic-bezier(0.4,0,0.2,1)] md:absolute md:inset-y-0 md:left-1/2 md:order-none md:z-30 md:flex md:min-h-[360px] md:w-1/2 md:items-center md:px-10 md:py-12 ${
              isSignUp ? 'md:-translate-x-full' : 'md:translate-x-0'
            }`}
          >
            <div className="absolute right-0 top-0 h-52 w-52 rounded-full bg-white/75 blur-3xl" />
            <div className="absolute bottom-0 left-0 h-56 w-56 rounded-full bg-[rgba(0,123,229,0.12)] blur-3xl" />

            <div className="relative mx-auto w-full max-w-xl">
              <div className="relative min-h-[285px] md:min-h-[280px]">
                <div
                  className={`absolute inset-0 flex flex-col items-center justify-center text-center transition-all duration-700 md:items-start md:text-left ${
                    isSignUp
                      ? 'translate-y-0 opacity-100 md:translate-x-0'
                      : 'translate-y-8 opacity-0 pointer-events-none md:translate-x-8'
                  }`}
                >
                  <span className="status-pill w-fit">Secure account access</span>
                  <h1 className="mt-5 text-3xl font-semibold leading-tight text-[var(--text-primary)] md:mt-6 md:text-4xl">
                    Welcome back to your finance workspace.
                  </h1>
                  <p className="mt-4 max-w-lg text-sm leading-6 text-[var(--text-secondary)] md:text-base md:leading-7">
                    Sign in to continue with saved profile details, conversation history,
                    and grounded insurance guidance.
                  </p>
                  <button
                    suppressHydrationWarning
                    type="button"
                    className="auth-switch-button mt-7 w-full max-w-[220px] px-6 py-3 md:mt-8 md:w-fit"
                    onClick={() => setMode('sign-in')}
                  >
                    Sign in
                  </button>
                </div>

                <div
                  className={`absolute inset-0 flex flex-col items-center justify-center text-center transition-all duration-700 md:items-start md:text-left ${
                    isSignUp
                      ? '-translate-y-8 opacity-0 pointer-events-none md:-translate-x-8'
                      : 'translate-y-0 opacity-100 md:translate-x-0'
                  }`}
                >
                  <span className="status-pill w-fit">New account setup</span>
                  <h1 className="mt-5 text-3xl font-semibold leading-tight text-[var(--text-primary)] md:mt-6 md:text-4xl">
                    Create your account and start with a cleaner setup.
                  </h1>
                  <p className="mt-4 max-w-lg text-sm leading-6 text-[var(--text-secondary)] md:text-base md:leading-7">
                    After sign up, we will ask a short onboarding form so the chatbot can
                    answer insurance questions more carefully for your situation.
                  </p>
                  <button
                    suppressHydrationWarning
                    type="button"
                    className="auth-switch-button mt-7 w-full max-w-[220px] px-6 py-3 md:mt-8 md:w-fit"
                    onClick={() => setMode('sign-up')}
                  >
                    Sign up
                  </button>
                </div>
              </div>

              <div className="mt-6 hidden gap-4 sm:grid sm:grid-cols-2 md:mt-8">
                <div className="surface-card-strong rounded-[24px] p-5">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Personalized answers
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                    Use onboarding details to shape relevant responses.
                  </p>
                </div>
                <div className="surface-card-strong rounded-[24px] p-5">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Saved history
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                    Revisit previous insurance conversations any time.
                  </p>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
