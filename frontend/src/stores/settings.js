import { defineStore } from 'pinia'
import http from '../api'

export const useSettingsStore = defineStore('settings', {
  state: () => ({ settings: {}, loaded: false }),
  actions: {
    async ensure() {
      if (!this.loaded) {
        this.settings = await http.get('/system/settings')
        this.loaded = true
      }
      return this.settings
    },
    async save(patch) {
      this.settings = await http.put('/system/settings', patch)
      return this.settings
    },
  },
})
