import { createClient } from '@/utils/supabase/server'
import { type EmailOtpType } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const allowedOtpTypes = new Set<EmailOtpType>([
  'signup',
  'invite',
  'magiclink',
  'recovery',
  'email_change',
  'email',
])

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const tokenHash = searchParams.get('token_hash')
  const type = searchParams.get('type') as EmailOtpType | null
  const next = searchParams.get('next') ?? '/onboarding'

  if (tokenHash && type && allowedOtpTypes.has(type)) {
    const supabase = await createClient()
    const { error } = await supabase.auth.verifyOtp({
      type,
      token_hash: tokenHash,
    })

    if (!error) {
      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  const message =
    'This confirmation link is invalid or expired. If your email is already verified, please sign in below.'

  return NextResponse.redirect(`${origin}/sign-in?error=${encodeURIComponent(message)}`)
}
