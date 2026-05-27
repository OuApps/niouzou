import { create } from 'zustand'

interface AuthState {
  token: string | null
  email: string | null
  setAuth: (token: string, email: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('niouzou_token'),
  email: localStorage.getItem('niouzou_email'),
  setAuth: (token, email) => {
    localStorage.setItem('niouzou_token', token)
    localStorage.setItem('niouzou_email', email)
    set({ token, email })
  },
  logout: () => {
    localStorage.removeItem('niouzou_token')
    localStorage.removeItem('niouzou_email')
    set({ token: null, email: null })
  },
}))
