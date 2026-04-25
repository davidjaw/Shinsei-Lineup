import { ref, computed, readonly } from 'vue'
import {
  type Session, type OAuthProvider,
  getSession, signInWithProvider, signOut as signOutLib,
} from '../lib/auth'

// Single shared reactive session for the whole app. Initialized from
// localStorage so a returning user stays logged in across reloads.
const session = ref<Session | null>(getSession())

// Re-read after handleAuthCallback consumes the OAuth hash. Call this once
// after auth.handleAuthCallback() succeeds so reactive consumers update.
const refreshFromStorage = (): void => {
  session.value = getSession()
}

const signIn = (provider: OAuthProvider): void => {
  // Full-page redirect — nothing after this line will run.
  signInWithProvider(provider)
}

const signOut = async (): Promise<void> => {
  await signOutLib()
  session.value = null
}

export function useAuth() {
  return {
    session: readonly(session),
    user: computed(() => session.value?.user ?? null),
    isLoggedIn: computed(() => session.value !== null),
    signIn,
    signOut,
    refreshFromStorage,
  }
}
