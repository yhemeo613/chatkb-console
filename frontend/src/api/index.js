import axios from 'axios'
import { message } from 'ant-design-vue'

const http = axios.create({ baseURL: '/api', timeout: 600000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('chatkb_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const status = err.response?.status
    const detail = err.response?.data?.detail || err.message || '请求失败'
    if (status === 401 && !location.pathname.startsWith('/login')) {
      localStorage.removeItem('chatkb_token')
      localStorage.removeItem('chatkb_user')
      if (!location.pathname.startsWith('/login')) location.href = '/login'
    } else {
      message.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    }
    return Promise.reject(err)
  },
)

export default http
