'use server'

import { revalidatePath } from 'next/cache'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'

function authErrorMessage(message: string) {
  const normalized = message.toLowerCase()

  if (normalized.includes('email not confirmed')) {
    return 'Please confirm your email first, then sign in.'
  }

  if (normalized.includes('invalid login credentials')) {
    return 'Email or password is incorrect.'
  }

  if (normalized.includes('user already registered')) {
    return 'This email is already registered. Please sign in instead.'
  }

  return message
}

export async function login(formData: FormData) {
  const supabase = await createClient()
  const email = String(formData.get('email') || '').trim()
  const password = String(formData.get('password') || '')

  if (!email || !password) {
    redirect('/sign-in?error=Email and password are required')
  }

  const { error } = await supabase.auth.signInWithPassword({
    email,
    password,
  })

  if (error) {
    const message = encodeURIComponent(authErrorMessage(error.message))
    return redirect(`/sign-in?error=${message}`)
  }

  revalidatePath('/', 'layout')
  redirect('/')
}

export async function signup(formData: FormData) {
  const supabase = await createClient()
  const email = String(formData.get('email') || '').trim()
  const password = String(formData.get('password') || '')
  const confirmPassword = String(formData.get('confirmPassword') || '')

  if (password !== confirmPassword) {
    return redirect('/sign-up?error=Passwords do not match')
  }

  if (!email || !password) {
    redirect('/sign-up?error=Email and password are required')
  }

  const origin = (await headers()).get('origin') ?? 'http://localhost:3000'

  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      emailRedirectTo: `${origin}/auth/callback?next=/onboarding`,
    },
  })

  if (error) {
    const message = encodeURIComponent(authErrorMessage(error.message))
    return redirect(`/sign-up?error=${message}`)
  }

  revalidatePath('/', 'layout')

  if (!data.session) {
    redirect('/sign-in?message=Account created. Please confirm your email, then sign in.')
  }

  redirect('/onboarding')
}

export async function logout() {
  const supabase = await createClient()
  await supabase.auth.signOut()
  redirect('/sign-in')
}
