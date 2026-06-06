import plugin from 'tailwindcss/plugin'

export const uiPlugin = plugin(function ({ addComponents, theme }) {
  addComponents({
    /* =====================
       BADGES - Light & Dark Mode
    ===================== */
    '.badge': {
      padding: '0.25rem 0.625rem',
      borderRadius: '9999px',
      fontSize: '0.75rem',
      fontWeight: '600',
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.25rem',
      transition: 'all 0.2s ease',
    },

    '.badge-success': {
      backgroundColor: 'rgb(16 185 129 / 0.1)',
      color: theme('colors.emerald.600'),
      border: '1px solid rgb(16 185 129 / 0.2)',
    },
    '.dark .badge-success': {
      backgroundColor: 'rgb(16 185 129 / 0.15)',
      color: theme('colors.emerald.400'),
      border: '1px solid rgb(16 185 129 / 0.3)',
    },

    '.badge-danger': {
      backgroundColor: 'rgb(239 68 68 / 0.1)',
      color: theme('colors.red.600'),
      border: '1px solid rgb(239 68 68 / 0.2)',
    },
    '.dark .badge-danger': {
      backgroundColor: 'rgb(239 68 68 / 0.15)',
      color: theme('colors.red.400'),
      border: '1px solid rgb(239 68 68 / 0.3)',
    },

    '.badge-warning': {
      backgroundColor: 'rgb(245 158 11 / 0.1)',
      color: theme('colors.amber.600'),
      border: '1px solid rgb(245 158 11 / 0.2)',
    },
    '.dark .badge-warning': {
      backgroundColor: 'rgb(245 158 11 / 0.15)',
      color: theme('colors.amber.400'),
      border: '1px solid rgb(245 158 11 / 0.3)',
    },

    '.badge-info': {
      backgroundColor: 'rgb(6 182 212 / 0.1)',
      color: theme('colors.cyan.600'),
      border: '1px solid rgb(6 182 212 / 0.2)',
    },
    '.dark .badge-info': {
      backgroundColor: 'rgb(6 182 212 / 0.15)',
      color: theme('colors.cyan.400'),
      border: '1px solid rgb(6 182 212 / 0.3)',
    },

    /* =====================
       BUTTONS - Light & Dark Mode
    ===================== */
    '.btn': {
      padding: '0.625rem 1rem',
      borderRadius: '0.5rem',
      fontWeight: '500',
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '0.5rem',
      transition: 'all 0.2s ease',
      cursor: 'pointer',
    },

    '.btn-primary': {
      background: 'linear-gradient(to right, #2563eb, #3b82f6)',
      color: '#ffffff',
      border: 'none',
    },

    '.btn-primary:hover': {
      boxShadow: '0 10px 25px rgb(59 130 246 / 0.25)',
      transform: 'translateY(-1px)',
    },

    '.btn-primary:disabled': {
      opacity: '0.5',
      cursor: 'not-allowed',
      transform: 'none',
    },

    '.btn-ghost': {
      backgroundColor: '#f1f5f9',
      color: '#374151',
      border: '1px solid #e2e8f0',
    },
    '.dark .btn-ghost': {
      backgroundColor: theme('colors.dark.800'),
      color: theme('colors.dark.200'),
      border: `1px solid ${theme('colors.dark.600')}`,
    },

    '.btn-ghost:hover': {
      backgroundColor: '#e2e8f0',
      color: '#111827',
    },
    '.dark .btn-ghost:hover': {
      backgroundColor: theme('colors.dark.700'),
      color: '#ffffff',
    },

    '.btn-danger': {
      backgroundColor: '#ef4444',
      color: '#ffffff',
      border: 'none',
    },

    '.btn-danger:hover': {
      backgroundColor: '#dc2626',
      boxShadow: '0 10px 25px rgb(239 68 68 / 0.25)',
    },

    /* =====================
       FORM ELEMENTS
    ===================== */
    '.select-field': {
      appearance: 'none',
      backgroundColor: '#f1f5f9',
      color: '#374151',
      padding: '0.5rem 2rem 0.5rem 0.75rem',
      borderRadius: '0.5rem',
      border: '1px solid #e2e8f0',
      fontSize: '0.875rem',
      fontWeight: '500',
      transition: 'all 0.2s ease',
    },
    '.dark .select-field': {
      backgroundColor: theme('colors.dark.800'),
      color: '#ffffff',
      border: `1px solid ${theme('colors.dark.600')}`,
    },

    '.select-field:focus': {
      outline: 'none',
      borderColor: '#3b82f6',
      boxShadow: '0 0 0 3px rgb(59 130 246 / 0.1)',
    },

    /* =====================
       TABLE STYLES
    ===================== */
    '.table-header': {
      backgroundColor: '#f8fafc',
      color: '#64748b',
      fontSize: '0.75rem',
      fontWeight: '700',
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
    },
    '.dark .table-header': {
      backgroundColor: 'rgb(15 22 41 / 0.5)',
      color: theme('colors.dark.400'),
    },

    '.table-row': {
      borderBottom: '1px solid #e2e8f0',
      transition: 'background-color 0.15s ease',
    },
    '.dark .table-row': {
      borderBottom: `1px solid ${theme('colors.dark.700')}`,
    },

    '.table-row:hover': {
      backgroundColor: '#f8fafc',
    },
    '.dark .table-row:hover': {
      backgroundColor: 'rgb(15 22 41 / 0.3)',
    },
  })
})
