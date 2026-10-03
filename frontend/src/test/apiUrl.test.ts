import { afterEach, describe, expect, it } from 'vitest'
import { __setApiBaseForTests, apiBase, apiUrl } from '../api/client'

describe('apiUrl / apiBase', () => {
  afterEach(() => {
    __setApiBaseForTests(null)
  })

  it('prefixes relative /api paths with VITE_API_BASE_URL', () => {
    __setApiBaseForTests('https://api.example.com')
    expect(apiBase()).toBe('https://api.example.com')
    expect(apiUrl('/api/public/reports/1/scan-pages/page-01.jpg')).toBe(
      'https://api.example.com/api/public/reports/1/scan-pages/page-01.jpg',
    )
  })

  it('leaves absolute and data URLs unchanged', () => {
    __setApiBaseForTests('https://api.example.com')
    expect(apiUrl('https://cdn.example.com/x.jpg')).toBe('https://cdn.example.com/x.jpg')
    expect(apiUrl('data:image/png;base64,xx')).toBe('data:image/png;base64,xx')
  })

  it('returns same-origin relative paths when base is empty', () => {
    __setApiBaseForTests('')
    expect(apiBase()).toBe('')
    expect(apiUrl('/api/health')).toBe('/api/health')
  })

  it('strips trailing slash on the API base', () => {
    __setApiBaseForTests('https://api.example.com/')
    expect(apiUrl('/api/public/reports/1/scan-pages/page-01.jpg')).toBe(
      'https://api.example.com/api/public/reports/1/scan-pages/page-01.jpg',
    )
  })
})
