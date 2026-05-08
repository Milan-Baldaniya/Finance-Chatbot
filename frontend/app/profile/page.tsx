'use client'

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
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
  { value: 'Low Premium + High Cover', icon: '🛡️', desc: 'Pure term life protection' },
  { value: 'Guaranteed Returns + Insurance', icon: '📈', desc: 'Endowment & safe savings' },
  { value: 'Market-Linked Wealth Creation', icon: '🚀', desc: 'ULIPs for long-term growth' },
  { value: 'Lifelong Income / Retirement', icon: '🌅', desc: 'Annuity & whole life' },
  { value: 'Tax Saving', icon: '💰', desc: 'Maximize 80C & 80D deductions' },
  { value: 'Critical Illness Protection', icon: '🏥', desc: 'Coverage for severe diseases' },
  { value: 'Motor Insurance', icon: '🚗', desc: 'Vehicle protection & OD cover' },
]

const profileGoalOptions = [
  ...goalOptions.map(({ value, desc }) => ({
    value,
    desc: desc.replace(/&/g, 'and'),
  })),
  { value: 'Health & Hospitalization', desc: 'Cashless mediclaim coverage' },
  { value: 'Personal Accident Protection', desc: 'Accidental death and disability cover' },
  { value: 'Group / Corporate Health', desc: 'Employee health benefits' },
  { value: 'Maternity & Parenthood', desc: 'Coverage for growing families' },
  { value: 'OPD & Day-to-Day Care', desc: 'Outpatient and routine health expenses' },
  { value: 'Chronic & Long-term Illness', desc: 'Ongoing disease management' },
  { value: 'Commercial Vehicle & Fleet', desc: 'Business and trade vehicle cover' },
]

interface UserProfile {
  date_of_birth?: string
  gender?: string
  residential_status?: string
  annual_income_band?: string
  occupation_type?: string
  is_smoker?: boolean
  has_preexisting_conditions?: boolean
  preexisting_conditions?: string[]
  primary_insurance_goal?: string
  life_stage_dependents?: string[]
  vehicle_status?: string | null
  has_existing_long_term_tp_policy?: boolean | null
  onboarding_completed?: boolean
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [hasPreexisting, setHasPreexisting] = useState(false)
  const [primaryGoal, setPrimaryGoal] = useState('Low Premium + High Cover')
  const supabaseRef = useRef<ReturnType<typeof createClient> | null>(null)
  const router = useRouter()
  const isMotorGoal = primaryGoal === 'Motor Insurance'

  const getSupabase = useCallback(() => {
    if (!supabaseRef.current) {
      supabaseRef.current = createClient()
    }

    return supabaseRef.current
  }, [])

  useEffect(() => {
    const loadProfile = async () => {
      const {
        data: { session },
      } = await getSupabase().auth.getSession()

      if (!session) {
        router.push('/sign-in')
        return
      }

      try {
        const response = await fetch(`${API_BASE}/api/profile`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        })

        if (response.ok) {
          const data = await response.json()
          setProfile(data)
          setHasPreexisting(Boolean(data.has_preexisting_conditions))
          setPrimaryGoal(data.primary_insurance_goal || 'Low Premium + High Cover')
        }
      } catch (error) {
        console.error('Error loading profile:', error)
      } finally {
        setLoading(false)
      }
    }

    loadProfile()
  }, [getSupabase, router])

  const handleSave = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSaving(true)
    setMessage('')
    const form = event.currentTarget

    const {
      data: { session },
    } = await getSupabase().auth.getSession()

    if (!session) {
      router.push('/sign-in')
      return
    }

    const formData = new FormData(form)
    const payload = {
      date_of_birth: String(formData.get('dateOfBirth') || ''),
      gender: String(formData.get('gender') || ''),
      residential_status: String(formData.get('residentialStatus') || ''),
      annual_income_band: String(formData.get('annualIncome') || ''),
      occupation_type: String(formData.get('occupation') || ''),
      is_smoker: formData.get('isSmoker') === 'true',
      has_preexisting_conditions: hasPreexisting,
      preexisting_conditions: hasPreexisting
        ? formData.getAll('preexistingConditions').map(String)
        : [],
      primary_insurance_goal: primaryGoal,
      life_stage_dependents: formData.getAll('lifeStageDependents').map(String),
      vehicle_status: isMotorGoal ? String(formData.get('vehicleStatus') || '') : null,
      has_existing_long_term_tp_policy: isMotorGoal
        ? formData.get('existingTpPolicy') === 'true'
        : null,
    }

    try {
      const response = await fetch(`${API_BASE}/api/profile`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error('Profile update failed')
      }

      const updated = await response.json()
      setProfile(updated)
      setMessage('Profile updated successfully.')
      setTimeout(() => setMessage(''), 3000)
    } catch (error) {
      console.error('Save error:', error)
      setMessage('Failed to save profile. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  const hasCondition = (condition: string) =>
    Array.isArray(profile?.preexisting_conditions) &&
    profile.preexisting_conditions.includes(condition)

  const hasDependent = (dependent: string) =>
    Array.isArray(profile?.life_stage_dependents) &&
    profile.life_stage_dependents.includes(dependent)

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="surface-card flex w-full max-w-sm flex-col items-center gap-4 rounded-[30px] p-10 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--accent-primary)] text-xl font-bold text-white">
            F
          </div>
          <div className="h-10 w-10 rounded-full border-2 border-[var(--accent-primary)] border-t-transparent animate-spin" />
          <p className="text-sm text-[var(--text-secondary)]">Loading your saved profile...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen overflow-hidden px-3 py-5 min-[437px]:px-4 min-[437px]:py-6 md:px-8 md:py-8">
      <div className="page-orb left-[-3rem] top-12 h-44 w-44 bg-[rgba(0,123,229,0.14)]" />
      <div
        className="page-orb right-[-4rem] top-24 h-72 w-72 bg-[rgba(210,136,66,0.16)]"
        style={{ animationDelay: '1.6s' }}
      />

      <div className="relative mx-auto max-w-7xl">
        <div className="mb-6 flex flex-col items-start justify-between gap-3 min-[437px]:flex-row min-[437px]:flex-wrap min-[437px]:items-center">
          <div className="min-w-0">
            <p className="section-kicker">Profile settings</p>
            <h1 className="mt-2 text-2xl font-semibold leading-tight text-[var(--text-primary)] min-[437px]:text-3xl md:text-4xl">
              Update your insurance details
            </h1>

          </div>

          <button
            type="button"
            onClick={() => router.push('/')}
            className="secondary-button w-full px-5 py-3 text-sm min-[437px]:w-auto"
          >
            Back to chat
          </button>
        </div>

        <div className="grid gap-6 xl:grid-cols-[0.9fr_1.3fr]">
          <aside className="space-y-5 xl:sticky xl:top-8 xl:self-start">
            <div className="surface-card rounded-[24px] p-5 min-[437px]:rounded-[30px] min-[437px]:p-6">
              <div className="flex h-14 w-14 items-center justify-center rounded-[20px] bg-[var(--accent-primary)] text-xl font-bold text-white glow-ring">
                F
              </div>
              <h2 className="mt-5 text-xl font-semibold text-[var(--text-primary)] min-[437px]:text-2xl">
                Your profile powers safer answers
              </h2>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                Updated details help with age-sensitive plans, NRI handling,
                smoking-related premium context, dependents, and health-related
                waiting period discussions.
              </p>
            </div>

            <div className="surface-card-soft rounded-[22px] p-5 min-[437px]:rounded-[28px] min-[437px]:p-6">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Good to know
              </p>
              <ul className="mt-4 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">

                <li>Document retrieval and citations still stay central to the answer flow.</li>
                <li>You can return to chat immediately after saving.</li>
              </ul>
            </div>
          </aside>

          <form onSubmit={handleSave} className="surface-card rounded-[24px] p-4 min-[437px]:rounded-[32px] min-[437px]:p-6 md:p-8">
            {message && (
              <div
                className={`mb-6 rounded-[20px] px-4 py-3 text-sm ${message.includes('successfully')
                  ? 'border border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border border-red-200 bg-red-50 text-red-700'
                  }`}
              >
                {message}
              </div>
            )}

            <div className="space-y-6">
              <section className="surface-card-soft rounded-[20px] p-4 min-[437px]:rounded-[28px] min-[437px]:p-5 md:p-6">
                <div className="mb-5">
                  <p className="section-kicker">Section 1</p>
                  <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                    Personal details
                  </h3>
                </div>

                <div className="grid gap-5 md:grid-cols-2">
                  <label className="block">
                    <span className="field-label">Date of birth</span>
                    <input
                      type="date"
                      name="dateOfBirth"
                      defaultValue={profile?.date_of_birth || ''}
                      required
                      className="app-input"
                    />
                  </label>

                  <div>
                    <span className="field-label">Gender</span>
                    <div className="flex flex-wrap gap-3">
                      {['Male', 'Female'].map((option) => (
                        <label key={option} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="gender"
                            value={option}
                            required
                            defaultChecked={profile?.gender === option}
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
                    <div className="flex flex-wrap gap-3">
                      {['Resident Indian', 'Non-Resident Indian (NRI)'].map((option) => (
                        <label key={option} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="residentialStatus"
                            value={option}
                            required
                            defaultChecked={
                              (profile?.residential_status || 'Resident Indian') === option
                            }
                            className="h-4 w-4 accent-[var(--accent-primary)]"
                          />
                          <div>
                            <p className="text-sm font-medium text-[var(--text-primary)]">
                              {option}
                            </p>
                            <p className="mt-1 text-xs text-[var(--text-secondary)]">
                              {option === 'Resident Indian'
                                ? 'Standard domestic routing.'
                                : 'Useful when comparing NRI-compatible insurers.'}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </section>

              <section className="surface-card-soft rounded-[20px] p-4 min-[437px]:rounded-[28px] min-[437px]:p-5 md:p-6">
                <div className="mb-5">
                  <p className="section-kicker">Section 2</p>
                  <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                    Income and occupation
                  </h3>
                </div>

                <div className="grid gap-6">
                  <div>
                    <span className="field-label mb-3 block">Annual income</span>
                    <div className="flex flex-wrap gap-3">
                      {['Below Rs 5 Lakh', 'Rs 5 Lakh - Rs 10 Lakh', 'Above Rs 10 Lakh'].map((option) => (
                        <label key={option} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="annualIncome"
                            value={option}
                            required
                            defaultChecked={(profile?.annual_income_band || 'Below Rs 5 Lakh') === option}
                            className="h-4 w-4 accent-[var(--accent-primary)] shrink-0"
                          />
                          <span className="text-sm font-medium text-[var(--text-primary)]">
                            {option}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div>
                    <span className="field-label mb-3 block">Occupation type</span>
                    <div className="flex flex-wrap gap-3">
                      {['Salaried', 'Self-Employed', 'Business Owner'].map((option) => (
                        <label key={option} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="occupation"
                            value={option}
                            required
                            defaultChecked={(profile?.occupation_type || 'Salaried') === option}
                            className="h-4 w-4 accent-[var(--accent-primary)] shrink-0"
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

              <section className="surface-card-soft rounded-[20px] p-4 min-[437px]:rounded-[28px] min-[437px]:p-5 md:p-6">
                <div className="mb-5">
                  <p className="section-kicker">Section 3</p>
                  <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                    Lifestyle, health, and goals
                  </h3>
                </div>

                <div className="grid gap-6">
                  <div>
                    <span className="field-label">Tobacco or smoker status</span>
                    <div className="flex flex-wrap gap-3">
                      {[
                        { label: 'No', value: 'false', note: 'Non-smoker context.' },
                        { label: 'Yes', value: 'true', note: 'Useful for premium impact discussions.' },
                      ].map((option) => (
                        <label key={option.value} className="choice-chip cursor-pointer">
                          <input
                            type="radio"
                            name="isSmoker"
                            value={option.value}
                            required
                            defaultChecked={
                              (profile?.is_smoker ? 'true' : 'false') === option.value
                            }
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
                            defaultChecked={
                              (profile?.has_preexisting_conditions ? 'true' : 'false') ===
                              option.value
                            }
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
                      <div className="flex flex-wrap gap-3">
                        {conditionOptions.map((condition) => (
                          <label key={condition} className="choice-chip cursor-pointer">
                            <input
                              type="checkbox"
                              name="preexistingConditions"
                              value={condition}
                              defaultChecked={hasCondition(condition)}
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

                  <div className="md:col-span-2">
                    <span className="field-label mb-3 block">Primary insurance goal</span>
                    <div className="flex flex-wrap gap-3">
                      {profileGoalOptions.map((goal) => (
                        <label
                          key={goal.value}
                          data-selected={primaryGoal === goal.value}
                          className="profile-option-card"
                        >
                          <input
                            type="radio"
                            name="primaryGoal"
                            value={goal.value}
                            checked={primaryGoal === goal.value}
                            onChange={(e) => setPrimaryGoal(e.target.value)}
                            className="absolute right-4 top-4 h-4 w-4 accent-[var(--accent-primary)]"
                            required
                          />
                          <div className="pr-7">
                            <p className="text-sm font-semibold leading-5 text-[var(--text-primary)]">
                              {goal.value}
                            </p>
                            <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                              {goal.desc}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div>
                    <span className="field-label">Life stage and dependents</span>
                    <div className="flex flex-wrap gap-3">
                      {dependentOptions.map((option) => (
                        <label key={option} className="choice-chip cursor-pointer">
                          <input
                            type="checkbox"
                            name="lifeStageDependents"
                            value={option}
                            defaultChecked={hasDependent(option)}
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
                <section className="surface-card-soft rounded-[20px] p-4 min-[437px]:rounded-[28px] min-[437px]:p-5 md:p-6">
                  <div className="mb-5">
                    <p className="section-kicker">Section 4</p>
                    <h3 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">
                      Motor insurance details
                    </h3>
                  </div>

                  <div className="grid gap-5 md:grid-cols-2">
                    <label className="block">
                      <span className="field-label">Vehicle status</span>
                      <select
                        name="vehicleStatus"
                        defaultValue={profile?.vehicle_status || 'Newly Purchased'}
                        required={isMotorGoal}
                        className="app-select"
                      >
                        <option value="Newly Purchased">Newly Purchased</option>
                        <option value="Existing Vehicle">Existing Vehicle</option>
                      </select>
                    </label>

                    <div>
                      <span className="field-label">Existing long-term third-party policy</span>
                      <div className="flex flex-wrap gap-3">
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
                              defaultChecked={
                                (profile?.has_existing_long_term_tp_policy ? 'true' : 'false') ===
                                option.value
                              }
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
                disabled={saving}
                className="primary-button w-full px-6 py-3.5 text-sm min-[437px]:w-auto"
              >
                {saving ? 'Saving changes...' : 'Save profile changes'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
