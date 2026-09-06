import { defineStore } from 'pinia'
import http from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('chatkb_token') || '',
    user: JSON.parse(localStorage.getItem('chatkb_user') || 'null'), // 含 roles/perms/menus
    loaded: false,
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    perms: (s) => s.user?.perms || [],
    menus: (s) => s.user?.menus || [],
  },
  actions: {
    hasPerm(code) {
      if (!code) return true
      if (this.user?.is_superuser) return true
      return this.perms.includes(code)
    },
    async login(username, password) {
      const d = await http.post('/auth/login', { username, password })
      this._apply(d)
    },
    async register(form) {
      const d = await http.post('/auth/register', form)
      this._apply(d)
    },
    _apply(d) {
      this.token = d.access_token
      this.user = d.user
      this.loaded = true
      localStorage.setItem('chatkb_token', this.token)
      localStorage.setItem('chatkb_user', JSON.stringify(this.user))
    },
    async fetchMe() {
      this.user = await http.get('/auth/me')
      this.loaded = true
      localStorage.setItem('chatkb_user', JSON.stringify(this.user))
    },
    async ensure() {
      if (!this.loaded && this.token) await this.fetchMe()
    },
    logout() {
      this.token = ''
      this.user = null
      this.loaded = false
      localStorage.removeItem('chatkb_token')
      localStorage.removeItem('chatkb_user')
    },
    async changePassword(oldPassword, newPassword) {
      await http.post('/auth/change-password', { old_password: oldPassword, new_password: newPassword })
    },
  },
})
