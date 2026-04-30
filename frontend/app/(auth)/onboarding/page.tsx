'use client'

import { FormEvent, useCallback, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/utils/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

const conditionOptions = [
  'Cancer',
  'Heart Disease',
  'AIDS',
  'Renal Failure',
  'Diabetes',
  'Hypertension',
]

const dependentOptions = ['Single', 'Married', 'Kids', 'Senior Parents']

const goalOptions = [
  'Low Premium + High Cover',
  'Guaranteed Returns + Insurance',
  'Market-Linked Wealth Creation',
  'Lifelong Income / Retirement',
  'Tax Saving',
  'Critical Illness Protection',
  'Motor Insurance',
]

export default function Onboarding() {
  const [hasPreexisting, setHasPreexisting] = useState(false)
  const [primaryGoal, setPrimaryGoal] = useState('Low Premium + High Cover')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const supabaseRef = useRef<ReturnType<typeof createClient> | null>(null)
  const router = useRouter()
  const isMotorGoal = primaryGoal === 'Motor Insurance'

  const getSupabase = useCallback(() => {
    if (!supabaseRef.current) {
      supabaseRef.current = createClient()
    }

    return supabaseRef.current
  }, [])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setIsSubmitting(true)
    setError('')
    const form = event.currentTarget

    const {
      data: { session },
    } = await getSupabase().auth.getSession()

    if (!session) {
      router.push('/sign-in')
      return
    }

    const formData = new FormData(form)
    const preexistingConditions = hasPreexisting
      ? formData.getAll('preexistingConditions').map(String)
      : []

    const payload = {
      date_of_birth: String(formData.get('dateOfBirth') || ''),
      gender: String(formData.get('gender') || ''),
      residential_status: String(formData.get('residentialStatus') || ''),
      annual_income_band: String(formData.get('annualIncome') || ''),
      occupation_type: String(formData.get('occupation') || ''),
      is_smoker: formData.get('isSmoker') === 'true',
      has_preexisting_conditions: hasPreexisting,
      preexisting_conditions: preexistingConditions,
      primary_insurance_goal: primaryGoal,
      life_stage_dependents: formData.getAll('lifeStageDependents').map(String),
      vehicle_status: isMotorGoal ? String(formData.get('vehicleStatus') || '') : null,
      has_existing_long_term_tp_policy: isMotorGoal
        ? formData.get('existingTpPolicy') === 'true'
        : null,
    }

    try {
      const response = await fetch(`${API_BASE}/api/profile/onboarding`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error('Profile save failed')
      }

      router.push('/')
      router.refresh()
    } catch {
      setError(
        'Could not save your profile yet. Please check that the backend and Supabase tables are running correctly.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-6 md:px-8 md:py-8">
      <div className="page-orb left-[-4rem] top-14 h-44 w-44 bg-[rgba(210,136,66,0.18)]" />
      <div
        className="page-orb right-[-3rem] top-24 h-72 w-72 bg-[rgba(0,123,229,0.12)]"
        style={{ animationDelay: '1.8s' }}
      />

      <div className="relative mx-auto max-w-7xl">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="section-kicker">One-time onboarding</p>
            <h1 className="mt-2 text-3xl font-semibold text-[var(--text-primary)] md:text-4xl">
              Set up your insurance profile
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--text-secondary)] md:text-base">
              These answers help chatbot respond with better context for eligibility,
              underwriting, family needs, and product fit.
            </p>
          </div>
          <span className="status-pill">Required before chat access</span>
        </div>

        <div className="grid gap-6 xl:grid-cols-[0.9fr_1.3fr]">
          <aside className="space-y-5 xl:sticky xl:top-8 xl:self-start">
            <div className="surface-card rounded-[30px] p-6">

              <h2 className="mt-5 text-2xl font-semibold text-[var(--text-primary)]">
                Why we ask this
              </h2>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                Your profile helps the chatbot be more careful with plan type
                suggestions, smoking impact, waiting periods, NRI handling, and
                family-specific recommendations.
              </p>
            </div>

            <div className="surface-card-soft rounded-[28px] p-6">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                What will happen next
              </p>
              <ul className="mt-4 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">
                <li>We save your details to your account only once.</li>
                <li>You can edit the profile any time from the chat sidebar.</li>

              </ul>
            </div>

            <div className="surface-card-soft rounded-[28px] p-6">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Estimated time
              </p>
              <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                Around 2 minutes. Most fields are quick selections, and motor-only
                questions appear only if you choose motor insurance as a goal.
              </p>
            </div>
          </aside>

          <form onSubmit={handleSubmit} className="surface-card rounded-[32px] p-6 md:p-8">
            {error && (
              <div className="mb-6 rounded-[20px] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="space-y-6">
              <section className="surface-card-soft rounded-[28px] p-5 md:p-6">
                <div className="mb-5">
                  <p className="section-kicker">Section 1</p>
                  <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                    Personal details
                  </h3>
                </div>

                <div className="grid gap-5 md:grid-cols-2">
                  <label className="block">
                    <span className="field-label">Date of birth</span>
                    <input type="date" name="dateOfBirth" required className="app-input" />
                    <span className="field-help">
                      Used to derive age range and plan eligibility buckets.
                    </span>
                  </label>

                  <div>
                    <span className="field-label">Gender</span>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {['Male', 'Female'].map((option) => (
                        <label key={option} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="gender"
                            value={option}
                            required
                            className="h-4 w-4 accent-[var(--accent-primary)]"
                          />
                          <span className="text-sm font-medium text-[var(--text-primary)]">
                            {option}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="md:col-span-2">
                    <span className="field-label">Residential status</span>
                    <div className="grid gap-3 md:grid-cols-2">
                      {['Resident Indian', 'Non-Resident Indian (NRI)'].map((option) => (
                        <label key={option} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="residentialStatus"
                            value={option}
                            required
                            defaultChecked={option === 'Resident Indian'}
                            className="h-4 w-4 accent-[var(--accent-primary)]"
                          />
                          <div>
                            <p className="text-sm font-medium text-[var(--text-primary)]">
                              {option}
                            </p>
                            <p className="mt-1 text-xs text-[var(--text-secondary)]">
                              {option === 'Resident Indian'
                                ? 'Standard domestic plan routing.'
                                : 'Useful for insurers that explicitly support NRI applications.'}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </section>

              <section className="surface-card-soft rounded-[28px] p-5 md:p-6">
                <div className="mb-5">
                  <p className="section-kicker">Section 2</p>
                  <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                    Income and occupation
                  </h3>
                </div>

                <div className="grid gap-5 md:grid-cols-2">
                  <label className="block">
                    <span className="field-label">Annual income</span>
                    <select name="annualIncome" required className="app-select">
                      <option value="Below Rs 5 Lakh">Below Rs 5 Lakh</option>
                      <option value="Rs 5 Lakh - Rs 10 Lakh">Rs 5 Lakh - Rs 10 Lakh</option>
                      <option value="Above Rs 10 Lakh">Above Rs 10 Lakh</option>
                    </select>
                  </label>

                  <label className="block">
                    <span className="field-label">Occupation type</span>
                    <select name="occupation" required className="app-select">
                      <option value="Salaried">Salaried</option>
                      <option value="Self-Employed">Self-Employed</option>
                      <option value="Business Owner">Business Owner</option>
                    </select>
                    <span className="field-help">
                      Business-oriented profiles can trigger broader protection
                      suggestions.
                    </span>
                  </label>
                </div>
              </section>

              <section className="surface-card-soft rounded-[28px] p-5 md:p-6">
                <div className="mb-5">
                  <p className="section-kicker">Section 3</p>
                  <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                    Lifestyle, health, and goals
                  </h3>
                </div>

                <div className="grid gap-6">
                  <div>
                    <span className="field-label">Tobacco or smoker status</span>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {[
                        { label: 'No', value: 'false', note: 'Use standard non-smoker assumptions.' },
                        { label: 'Yes', value: 'true', note: 'Lets chatbot discuss premium impact more carefully.' },
                      ].map((option) => (
                        <label key={option.value} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="isSmoker"
                            value={option.value}
                            required
                            defaultChecked={option.value === 'false'}
                            className="h-4 w-4 accent-[var(--accent-primary)]"
                          />
                          <div>
                            <p className="text-sm font-medium text-[var(--text-primary)]">
                              {option.label}
                            </p>
                            <p className="mt-1 text-xs text-[var(--text-secondary)]">
                              {option.note}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div>
                    <span className="field-label">Pre-existing diseases or medical conditions</span>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {[
                        { label: 'No', value: 'false' },
                        { label: 'Yes', value: 'true' },
                      ].map((option) => (
                        <label key={option.value} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="hasPreexisting"
                            value={option.value}
                            required
                            defaultChecked={option.value === 'false'}
                            onChange={(event) => setHasPreexisting(event.target.value === 'true')}
                            className="h-4 w-4 accent-[var(--accent-primary)]"
                          />
                          <span className="text-sm font-medium text-[var(--text-primary)]">
                            {option.label}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {hasPreexisting && (
                    <div>
                      <span className="field-label">Select the relevant conditions</span>
                      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                        {conditionOptions.map((condition) => (
                          <label key={condition} className="choice-chip cursor-pointer">
                            <input
                              type="checkbox"
                              name="preexistingConditions"
                              value={condition}
                              className="h-4 w-4 accent-[var(--accent-primary)]"
                            />
                            <span className="text-sm font-medium text-[var(--text-primary)]">
                              {condition}
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="block">
                      <span className="field-label">Primary insurance goal</span>
                      <select
                        name="primaryGoal"
                        value={primaryGoal}
                        onChange={(event) => setPrimaryGoal(event.target.value)}
                        required
                        className="app-select"
                      >
                        {goalOptions.map((goal) => (
                          <option key={goal} value={goal}>
                            {goal}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div>
                    <span className="field-label">Life stage and dependents</span>
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      {dependentOptions.map((option) => (
                        <label key={option} className="choice-chip cursor-pointer">
                          <input
                            type="checkbox"
                            name="lifeStageDependents"
                            value={option}
                            className="h-4 w-4 accent-[var(--accent-primary)]"
                          />
                          <span className="text-sm font-medium text-[var(--text-primary)]">
                            {option}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </section>

              {isMotorGoal && (
                <section className="surface-card-soft rounded-[28px] p-5 md:p-6">
                  <div className="mb-5">
                    <p className="section-kicker">Section 4</p>
                    <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                      Motor insurance details
                    </h3>
                  </div>

                  <div className="grid gap-5 md:grid-cols-2">
                    <label className="block">
                      <span className="field-label">Vehicle status</span>
                      <select name="vehicleStatus" required={isMotorGoal} className="app-select">
                        <option value="Newly Purchased">Newly Purchased</option>
                        <option value="Existing Vehicle">Existing Vehicle</option>
                      </select>
                    </label>

                    <div>
                      <span className="field-label">Existing long-term third-party policy</span>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {[
                          { label: 'No', value: 'false' },
                          { label: 'Yes', value: 'true' },
                        ].map((option) => (
                          <label key={option.value} className="choice-chip cursor-pointer">
                            <input
                              type="radio"
                              name="existingTpPolicy"
                              value={option.value}
                              required={isMotorGoal}
                              defaultChecked={option.value === 'false'}
                              className="h-4 w-4 accent-[var(--accent-primary)]"
                            />
                            <span className="text-sm font-medium text-[var(--text-primary)]">
                              {option.label}
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>
              )}
            </div>

            <div className="mt-8 flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-6 md:flex-row md:items-center md:justify-between">

              <button
                type="submit"
                disabled={isSubmitting}
                className="primary-button px-6 py-3.5 text-sm"
              >
                {isSubmitting ? 'Saving your profile...' : 'Complete setup and enter chat'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
