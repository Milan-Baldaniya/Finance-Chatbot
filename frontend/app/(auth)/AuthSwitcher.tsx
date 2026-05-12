'use client'

import { useState } from 'react'
import Lottie from 'lottie-react'
import animationData from '../../public/Isometric data analysis.json'

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
    <div className="flex min-h-screen relative overflow-hidden bg-[#f8fafc]">
      {/* Abstract Background Elements */}
      <div className="absolute top-[-15%] left-[-10%] w-[50%] h-[50%] rounded-full bg-blue-400/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-5%] w-[40%] h-[40%] rounded-full bg-indigo-400/20 blur-[100px] pointer-events-none" />
      <div className="absolute top-[20%] right-[30%] w-[20%] h-[20%] rounded-full bg-cyan-300/20 blur-[80px] pointer-events-none" />

      {/* Left Side: Forms */}
      <div className="relative z-10 w-full flex flex-col justify-center items-center px-6 py-12 md:w-1/2 md:px-12 bg-white/70 backdrop-blur-2xl border-r border-white/50 shadow-[4px_0_40px_rgba(0,0,0,0.03)]">
        <div className="w-full max-w-md">
          {/* Header */}
          <div className="mb-10 text-center">
            <h2 className="text-4xl font-extrabold tracking-tight text-slate-900 mb-3">
              {isSignUp ? 'Create an Account' : 'Welcome Back'}
            </h2>
            <p className="text-base text-slate-500 font-medium">
              {isSignUp
                ? 'Sign up to get started with the finance chatbot.'
                : 'Sign in to access your finance workspace.'}
            </p>
          </div>

          {/* Switcher Buttons */}
          <div className="relative flex w-full rounded-2xl bg-slate-100/80 p-1.5 mb-10 shadow-inner">
            <div
              className={`absolute top-1.5 bottom-1.5 w-[calc(50%-6px)] rounded-xl bg-white shadow-[0_2px_8px_rgba(0,0,0,0.08)] transition-transform duration-500 cubic-bezier(0.4, 0, 0.2, 1) ${
                isSignUp ? 'translate-x-full left-[3px]' : 'translate-x-0 left-[3px]'
              }`}
            />
            <button
              suppressHydrationWarning
              type="button"
              className={`relative z-10 w-1/2 rounded-xl py-3 text-sm font-semibold transition-all duration-300 ${
                !isSignUp ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'
              }`}
              onClick={() => setMode('sign-in')}
            >
              Sign In
            </button>
            <button
              suppressHydrationWarning
              type="button"
              className={`relative z-10 w-1/2 rounded-xl py-3 text-sm font-semibold transition-all duration-300 ${
                isSignUp ? 'text-slate-900' : 'text-slate-500 hover:text-slate-700'
              }`}
              onClick={() => setMode('sign-up')}
            >
              Sign Up
            </button>
          </div>

          {/* Forms Container */}
          <div className="relative">
            {error && (
              <div className="mb-6 rounded-[20px] border border-red-200 bg-red-50/80 backdrop-blur-md px-4 py-3 text-sm text-red-700 shadow-sm">
                {error}
              </div>
            )}
            {!isSignUp && message && (
              <div className="mb-6 rounded-[20px] border border-emerald-200 bg-emerald-50/80 backdrop-blur-md px-4 py-3 text-sm text-emerald-700 shadow-sm">
                {message}
              </div>
            )}

            {/* Sign In Form */}
            <div
              className={`transition-all duration-500 ${
                !isSignUp ? 'block opacity-100 transform-none' : 'hidden opacity-0 translate-y-4'
              }`}
            >
              <form className="space-y-6" action={loginAction}>
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
                    className="app-input w-full mt-1.5 transition-all duration-300 hover:border-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 shadow-sm"
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
                    className="app-input w-full mt-1.5 transition-all duration-300 hover:border-slate-300 focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 shadow-sm"
                    placeholder="Enter your password"
                  />
                </div>
                <button
                  suppressHydrationWarning
                  type="submit"
                  className="primary-button w-full mt-2 px-5 py-3.5 shadow-[0_8px_20px_rgba(0,123,229,0.24)] hover:shadow-[0_12px_24px_rgba(0,123,229,0.32)] hover:-translate-y-0.5 transition-all duration-300"
                >
                  Sign in
                </button>
              </form>
            </div>

            {/* Sign Up Form */}
            <div
              className={`transition-all duration-500 ${
                isSignUp ? 'block opacity-100 transform-none' : 'hidden opacity-0 translate-y-4'
              }`}
            >
              <form className="space-y-6" action={signupAction}>
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
                    className="app-input w-full mt-1.5 transition-all duration-300 hover:border-slate-300 focus:border-[var(--accent-primary)] focus:ring-4 focus:ring-[var(--accent-primary)]/10 shadow-sm"
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
                    className="app-input w-full mt-1.5 transition-all duration-300 hover:border-slate-300 focus:border-[var(--accent-primary)] focus:ring-4 focus:ring-[var(--accent-primary)]/10 shadow-sm"
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
                    className="app-input w-full mt-1.5 transition-all duration-300 hover:border-slate-300 focus:border-[var(--accent-primary)] focus:ring-4 focus:ring-[var(--accent-primary)]/10 shadow-sm"
                    placeholder="Repeat your password"
                  />
                </div>
                <button
                  suppressHydrationWarning
                  type="submit"
                  className="primary-button w-full mt-2 bg-[var(--accent-primary)] px-5 py-3.5 text-white shadow-[0_8px_20px_rgba(0,123,229,0.24)] hover:shadow-[0_12px_24px_rgba(0,123,229,0.32)] hover:-translate-y-0.5 transition-all duration-300"
                >
                  Sign up
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>

      {/* Right Side: Blank space for Lottie animation */}
      <div className="hidden md:flex relative z-10 w-1/2 items-center justify-center bg-transparent p-12">
        {/* Subtle decorative grid background for the blank space */}
        <div className="absolute inset-0 opacity-[0.03] bg-[linear-gradient(to_right,#000_1px,transparent_1px),linear-gradient(to_bottom,#000_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_70%_70%_at_50%_50%,#000_30%,transparent_100%)]" />
        
        <div className="w-full max-w-lg flex flex-col items-center justify-center relative z-20">
          {/* Lottie animation container */}
          <div id="lottie-container" className="w-full aspect-square relative rounded-3xl bg-white/20 backdrop-blur-sm flex items-center justify-center shadow-[0_8px_32px_rgba(0,0,0,0.02)] overflow-hidden transition-all duration-500">
            <div className="w-[120%] h-[120%] flex items-center justify-center">
              <Lottie animationData={animationData} loop={true} className="w-full h-full" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
