import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { vi } from 'vitest'

import { server } from './server'

class ResizeObserverMock implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

class DOMMatrixMock {
  a = 1
  b = 0
  c = 0
  d = 1
  e = 0
  f = 0
  is2D = true
  isIdentity = true

  constructor(init?: string | number[]) { void init }
  inverse(): DOMMatrixMock { return new DOMMatrixMock() }
  multiply(): DOMMatrixMock { return new DOMMatrixMock() }
  translate(): DOMMatrixMock { return this }
  scale(): DOMMatrixMock { return this }
  transformPoint<T extends DOMPointInit>(point: T): T { return point }
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  configurable: true,
  value: ResizeObserverMock,
})
Object.defineProperty(globalThis, 'DOMMatrix', {
  configurable: true,
  value: DOMMatrixMock,
})
Object.defineProperty(globalThis, 'DOMMatrixReadOnly', {
  configurable: true,
  value: DOMMatrixMock,
})

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  vi.unstubAllGlobals()
})
afterAll(() => server.close())
