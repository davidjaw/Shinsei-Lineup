import { ref, computed, readonly } from 'vue'
import {
  type Session, type OAuthProvider,
  getSession, signInWithProvider, signOut as signOutLib,
  updateDisplayName as updateDisplayNameLib,
  onSessionEvent,
} from '../lib/auth'

// Single shared reactive session for the whole app. Initialized from
// localStorage so a returning user stays logged in across reloads.
const session = ref<Session | null>(getSession())

// Counter that increments each time the session is involuntarily cleared
// (refresh returned a revoked token). Components watch this to show a
// "your session expired" toast without coupling to the auth lib directly.
const sessionExpiredCount = ref(0)

// Subscribe once at module load: keep the reactive ref in sync with storage
// for every persist/clear, and bump sessionExpiredCount on involuntary clears.
onSessionEvent((e) => {
  session.value = getSession()
  if (e === 'expired') sessionExpiredCount.value++
})

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

const updateDisplayName = async (name: string): Promise<void> => {
  await updateDisplayNameLib(name)
  // Re-read from storage so the reactive ref picks up the persisted change.
  session.value = getSession()
}

export function useAuth() {
  return {
    session: readonly(session),
    user: computed(() => session.value?.user ?? null),
    isLoggedIn: computed(() => session.value !== null),
    // Best-effort name to display: explicit display_name > email prefix > 'user'
    displayName: computed(() => {
      const u = session.value?.user
      if (!u) return ''
      return u.display_name?.trim() || u.email.split('@')[0] || 'user'
    }),
    /** True if user has never set display_name — used to trigger first-time prompt. */
    needsDisplayName: computed(() => {
      const u = session.value?.user
      return u != null && (!u.display_name || u.display_name.trim() === '')
    }),
    signIn,
    signOut,
    updateDisplayName,
    refreshFromStorage,
    /** Increments when the session is cleared involuntarily (token revoked).
     *  Watch this to surface a "session expired" toast — the value itself is
     *  meaningless beyond "did it just change". */
    sessionExpiredCount: readonly(sessionExpiredCount),
  }
}
