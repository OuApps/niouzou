import { create } from 'zustand'
import { tokens } from '../api/http'

interface AuthState {
  token: string | null
  email: string | null
  /** Mirror in-memory state from localStorage after an API login/register. */
  sync: () => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: tokens.access(),
  email: tokens.email(),
  sync: () => set({ token: tokens.access(), email: tokens.email() }),
  logout: () => {
    tokens.clear()
    set({ token: null, email: null })
  },
}))
