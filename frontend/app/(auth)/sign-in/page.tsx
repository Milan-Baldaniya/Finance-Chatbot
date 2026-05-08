import { AuthSwitcher } from "../AuthSwitcher";
import { login, signup } from "../auth-actions";

type SignInSearchParams = Promise<{ error?: string; message?: string }>;

export default async function SignIn({
  searchParams,
}: {
  searchParams: SignInSearchParams;
}) {
  const params = await searchParams;

  return (
    <AuthSwitcher
      initialMode="sign-in"
      error={params?.error}
      message={params?.message}
      loginAction={login}
      signupAction={signup}
    />
  );
}
