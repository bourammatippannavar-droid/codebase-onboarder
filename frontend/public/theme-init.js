try {
  const saved = localStorage.getItem('onboarder-theme')
  const theme =
    saved === 'light' || saved === 'dark'
      ? saved
      : matchMedia('(prefers-color-scheme: light)').matches
        ? 'light'
        : 'dark'
  document.documentElement.dataset.theme = theme
} catch {
  document.documentElement.dataset.theme = matchMedia(
    '(prefers-color-scheme: light)',
  ).matches
    ? 'light'
    : 'dark'
}
