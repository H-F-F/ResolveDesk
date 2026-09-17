import "@testing-library/jest-dom/vitest";

// antd 的响应式组件依赖 window.matchMedia，jsdom 未提供
if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

// antd 的 message 等组件需要 ResizeObserver
if (!window.ResizeObserver) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Object.defineProperty(window, "ResizeObserver", {
    writable: true,
    value: ResizeObserverStub,
  });
}

// jsdom 未实现 scrollIntoView，ChatPage 的自动滚动依赖它
Object.defineProperty(Element.prototype, "scrollIntoView", {
  writable: true,
  value: () => undefined,
});
