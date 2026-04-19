import type { DocsThemeConfig } from 'nextra-theme-docs'

const config: DocsThemeConfig = {
  logo: (
    <span style={{ fontWeight: 700, fontSize: '1.1rem', letterSpacing: '-0.02em' }}>
      Vortex <span style={{ color: '#a78bfa', fontWeight: 400 }}>Docs</span>
    </span>
  ),
  project: {
    link: 'https://github.com/your-org/vortex',
  },
  docsRepositoryBase: 'https://github.com/your-org/vortex/tree/main/docs',
  footer: {
    content: '© 2026 Vortex',
  },
  head: (
    <>
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <meta name="description" content="Vortex self-hosting documentation" />
    </>
  ),
  darkMode: true,
}

export default config
