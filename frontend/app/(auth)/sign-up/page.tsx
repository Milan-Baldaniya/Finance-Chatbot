import { AuthSwitcher } from "../AuthSwitcher";
import { login, signup } from "../auth-actions";

type SignUpSearchParams = Promise<{ error?: string }>;

export default async function SignUp({
  searchParams,
}: {
  searchParams: SignUpSearchParams;
}) {
  const params = await searchParams;

  return (
    <AuthSwitcher
      initialMode="sign-up"
      error={params?.error}
      loginAction={login}
      signupAction={signup}
    />
  );
}
