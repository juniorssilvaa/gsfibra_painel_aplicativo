import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import axios from 'axios'
import { getApiBaseUrl } from '../utils/apiBaseUrl'

const AuthContext = createContext(null)

axios.defaults.baseURL = getApiBaseUrl()

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(async () => {
    try {
      await axios.post('/api/auth/logout/')
    } catch {
      // ignore
    }
    localStorage.removeItem('auth_token')
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setUser(null)
  }, [])

  const login = useCallback(async (username, password) => {
    try {
      const { data } = await axios.post('/api/auth/login/', { username, password })
      if (!data?.token) throw new Error('Token ausente')
      localStorage.setItem('auth_token', data.token)
      const me = await axios.get('/api/auth/me/', {
        headers: { Authorization: `Token ${data.token}` },
      })
      if (
        me.data?.user_type === 'admin' &&
        !me.data?.niohub_support &&
        (me.data?.provedor_is_active === false || me.data?.mobile_app_is_active === false)
      ) {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('token')
        const err = new Error('Acesso desativado. Entre em contato com o suporte.')
        err.response = { status: 403, data: { error: err.message } }
        throw err
      }
      setUser(me.data)
      localStorage.setItem('user', JSON.stringify(me.data))
      return me.data
    } catch (err) {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('token')
      throw err
    }
  }, [])

  useEffect(() => {
    const req = axios.interceptors.request.use((config) => {
      const token = localStorage.getItem('auth_token')
      if (token) {
        config.headers = config.headers || {}
        config.headers.Authorization = `Token ${token}`
      }
      return config
    })
    return () => axios.interceptors.request.eject(req)
  }, [])

  useEffect(() => {
    const bootstrap = async () => {
      const token = localStorage.getItem('auth_token')
      if (!token) {
        setLoading(false)
        return
      }
      try {
        const { data } = await axios.get('/api/auth/me/', {
          headers: { Authorization: `Token ${token}` },
        })
        if (
          data?.user_type === 'admin' &&
          !data?.niohub_support &&
          (data?.provedor_is_active === false || data?.mobile_app_is_active === false)
        ) {
          localStorage.removeItem('auth_token')
          localStorage.removeItem('token')
          localStorage.removeItem('user')
          setUser(null)
        } else {
          setUser(data)
        }
      } catch {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        setUser(null)
      } finally {
        setLoading(false)
      }
    }
    bootstrap()
  }, [])

  return (
    <AuthContext.Provider value={{ user, setUser, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
