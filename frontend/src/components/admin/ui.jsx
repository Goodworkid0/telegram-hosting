/**
 * Shared admin UI primitives — single source of truth for the admin panel's
 * "cyberpunk / terminal" look (cyan primary, matrix-green neon, mono accents,
 * scanline card tops, glow borders). Every admin tab composes these instead of
 * hand-rolling raw utility classes, so spacing/contrast/colors stay unified.
 */
import { forwardRef } from 'react'
import { t as translate } from '../../lib/i18n'
import { motion, AnimatePresence } from 'framer-motion'

const cx = (...parts) => parts.filter(Boolean).join(' ')

/* ----------------------------------------------------------------------- Card */
export const Card = forwardRef(function Card({ children, className = '', glow = false, blur = true, as: Tag = 'div', ...rest }, ref) {
  return (
    <Tag
      ref={ref}
      className={cx(
        'relative bg-dark-900/80 border border-primary-500/15 rounded-xl p-4',
        // backdrop-filter on a position:sticky/fixed layer crashes the Telegram
        // mobile WebView (iOS WKWebView) when it repaints on tap/scroll. Sticky
        // cards must pass blur={false}. See Board.jsx header.
        blur && 'backdrop-blur-sm',
        'transition-all duration-300 hover:border-primary-500/25',
        glow && 'shadow-neon-cyan',
        className
      )}
      {...rest}
    >
      {/* scanline accent on the top edge */}
      <span className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary-500/40 to-transparent" />
      {children}
    </Tag>
  )
})

/* ------------------------------------------------------------- SectionHeader */
export function SectionHeader({ children, right, className = '' }) {
  return (
    <div className={cx('flex items-center justify-between gap-3 mb-4', className)}>
      <h3 className="font-mono text-sm font-bold uppercase tracking-widest text-primary-300 flex items-center gap-2">
        <span className="text-primary-500/60">&gt;</span>
        {children}
        <span className="text-primary-500/25 animate-pulse">_</span>
      </h3>
      {right}
    </div>
  )
}

/* ------------------------------------------------------------------- Button */
const BTN_VARIANTS = {
  primary: 'bg-primary-500 text-dark-950 font-semibold border border-transparent hover:bg-primary-400 hover:shadow-neon-cyan shadow-lg shadow-primary-500/20',
  secondary: 'bg-dark-800/80 text-dark-100 border border-primary-500/20 hover:border-primary-500/40 hover:bg-dark-700 hover:shadow-neon-cyan',
  neon: 'bg-dark-900 text-neon-400 font-semibold border border-neon-500/30 hover:bg-neon-500/10 hover:border-neon-500/60 hover:shadow-neon-green',
  danger: 'bg-red-500/15 text-red-300 border border-red-500/30 hover:bg-red-500/25 hover:border-red-500/50',
  warn: 'bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 hover:border-amber-500/50',
  ghost: 'bg-transparent text-dark-300 border border-transparent hover:text-white hover:bg-dark-800/60',
}
const BTN_SIZES = {
  xs: 'px-2 py-1 text-[11px]',
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
}
export function Button({ variant = 'primary', size = 'md', className = '', icon: Icon, children, ...rest }) {
  return (
    <button
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-all duration-200',
        'active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100',
        BTN_VARIANTS[variant] || BTN_VARIANTS.primary,
        BTN_SIZES[size] || BTN_SIZES.md,
        className
      )}
      {...rest}
    >
      {Icon && <Icon size={size === 'lg' ? 18 : size === 'xs' ? 12 : 15} />}
      {children}
    </button>
  )
}

/* --------------------------------------------------------------- Form inputs */
const FIELD_CLS =
  'w-full bg-dark-950/60 border border-primary-500/15 rounded-lg px-3 py-2.5 text-sm text-white font-mono ' +
  'placeholder:text-dark-500 focus:border-primary-500/50 focus:outline-none ' +
  'focus:shadow-[0_0_0_1px_rgba(0,200,230,0.35)] transition-all'

const FieldLabel = ({ children }) =>
  children ? (
    <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-primary-400/70">{children}</label>
  ) : null

export function FormInput({ label, className = '', inputClassName = '', ...rest }) {
  return (
    <div className={className}>
      <FieldLabel>{label}</FieldLabel>
      <input className={cx(FIELD_CLS, inputClassName)} {...rest} />
    </div>
  )
}

export function FormTextarea({ label, className = '', inputClassName = '', ...rest }) {
  return (
    <div className={className}>
      <FieldLabel>{label}</FieldLabel>
      <textarea className={cx(FIELD_CLS, 'resize-y min-h-[80px]', inputClassName)} {...rest} />
    </div>
  )
}

export function FormSelect({ label, className = '', children, ...rest }) {
  return (
    <div className={className}>
      <FieldLabel>{label}</FieldLabel>
      <select
        className={cx(
          'w-full bg-dark-950/60 border border-primary-500/15 rounded-lg px-3 py-2.5 text-sm text-white',
          'focus:border-primary-500/50 focus:outline-none transition-all'
        )}
        {...rest}
      >
        {children}
      </select>
    </div>
  )
}

/* ------------------------------------------------------------------- Toggle */
export function Toggle({ checked, onChange, label, className = '' }) {
  return (
    <label className={cx('flex items-center gap-3 cursor-pointer select-none', className)}>
      <span
        className={cx(
          'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors duration-200',
          checked ? 'bg-neon-500/25 border-neon-500/60' : 'bg-dark-800 border-dark-600'
        )}
      >
        <span
          className={cx(
            'inline-block h-3.5 w-3.5 rounded-full transition-transform duration-200',
            checked ? 'translate-x-4 bg-neon-400 shadow-neon-green' : 'translate-x-1 bg-dark-400'
          )}
        />
      </span>
      <input type="checkbox" checked={!!checked} onChange={onChange} className="sr-only" />
      {label && <span className="text-sm text-dark-200">{label}</span>}
    </label>
  )
}

/* ------------------------------------------------------------------- Badges */
const STATUS_STYLES = {
  pending: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  processing: 'bg-primary-500/15 text-primary-300 border-primary-500/30',
  approved: 'bg-neon-500/15 text-neon-400 border-neon-500/30',
  completed: 'bg-neon-500/15 text-neon-400 border-neon-500/30',
  confirmed: 'bg-neon-500/15 text-neon-400 border-neon-500/30',
  finished: 'bg-neon-500/15 text-neon-400 border-neon-500/30',
  active: 'bg-neon-500/15 text-neon-400 border-neon-500/30',
  rejected: 'bg-red-500/15 text-red-400 border-red-500/30',
  failed: 'bg-red-500/15 text-red-400 border-red-500/30',
  expired: 'bg-dark-700/60 text-dark-400 border-dark-600',
  cancelled: 'bg-dark-700/60 text-dark-400 border-dark-600',
  needs_review: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
}
export function StatusBadge({ status, className = '' }) {
  const key = String(status || '').toLowerCase()
  const cls = STATUS_STYLES[key] || 'bg-dark-700/60 text-dark-300 border-dark-600'
  // Translate known statuses; unknown ones fall back to the raw value.
  const translated = translate(`status.${key}`)
  const label = translated === `status.${key}` ? status : translated
  return (
    <span className={cx('inline-block rounded px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider border', cls, className)}>
      {label}
    </span>
  )
}

// Single source of truth for role presentation (badge + text color + label),
// used by the RoleBadge here and by roleStyle() for inline role-colored text
// (e.g. mention autocomplete). Friendly short labels, cyberpunk palette.
const ROLE_META = {
  admin:     { labelKey: 'role.admin',  text: 'text-red-400',     badge: 'bg-red-500/15 text-red-400 border-red-500/30' },
  moderator: { labelKey: 'role.mod',    text: 'text-purple-300',  badge: 'bg-purple-500/15 text-purple-300 border-purple-500/30' },
  user:      { labelKey: 'role.member', text: 'text-primary-300', badge: 'bg-primary-500/15 text-primary-300 border-primary-500/30' },
  trial:     { labelKey: 'role.trial',  text: 'text-dark-300',    badge: 'bg-dark-700/60 text-dark-300 border-dark-600' },
}
export function roleStyle(role) {
  const key = String(role || '').toLowerCase().replace('userrole.', '')
  return ROLE_META[key] || ROLE_META.trial
}
export function RoleBadge({ role, className = '' }) {
  const m = roleStyle(role)
  return (
    <span className={cx('inline-block rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider border', m.badge, className)}>
      {translate(m.labelKey)}
    </span>
  )
}

/* ---------------------------------------------------------------------- Tag */
// Generic chip for forum metadata (Pinned / Locked / Best Answer / tags / etc).
const TAG_TONES = {
  neutral: 'bg-dark-800/70 text-dark-300 border-dark-600',
  cyan: 'bg-primary-500/15 text-primary-300 border-primary-500/30',
  green: 'bg-neon-500/15 text-neon-400 border-neon-500/30',
  amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  red: 'bg-red-500/15 text-red-400 border-red-500/30',
  purple: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
}
export function Tag({ tone = 'neutral', icon: Icon, className = '', children }) {
  return (
    <span className={cx(
      'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider border',
      TAG_TONES[tone] || TAG_TONES.neutral,
      className
    )}>
      {Icon && <Icon size={11} />}
      {children}
    </span>
  )
}

/* ----------------------------------------------------------------- PageHeading */
// Consistent page title block: glowing icon chip + gradient title + subtitle.
export function PageHeading({ icon: Icon, title, subtitle, right, className = '' }) {
  return (
    <div className={cx('flex items-start justify-between gap-3', className)}>
      <div className="flex items-center gap-3 min-w-0">
        {Icon && (
          <div className="w-10 h-10 rounded-xl bg-primary-500/15 border border-primary-500/25 flex items-center justify-center shrink-0">
            <Icon size={20} className="text-primary-400" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="font-display text-xl font-bold gradient-text leading-tight truncate">{title}</h1>
          {subtitle && <p className="text-xs text-dark-400 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {right}
    </div>
  )
}

/* ------------------------------------------------------------------ tabClass */
// Shared segmented-tab / pill styling so every tab strip looks identical.
export const tabClass = (active) => cx(
  'px-3 py-1.5 rounded-lg text-sm font-medium transition-all whitespace-nowrap',
  active
    ? 'bg-primary-500 text-dark-950 shadow-lg shadow-primary-500/20'
    : 'text-dark-400 hover:text-dark-100 hover:bg-dark-800/60'
)

/* --------------------------------------------------------------- StatTile */
const TILE_ACCENT = {
  default: 'text-white',
  cyan: 'text-primary-400',
  green: 'text-neon-400',
  red: 'text-red-400',
  amber: 'text-amber-400',
  emerald: 'text-emerald-400',
  purple: 'text-purple-300',
}
export function StatTile({ label, value, accent = 'default', onClick }) {
  return (
    <Card
      as={onClick ? 'button' : 'div'}
      onClick={onClick}
      className={cx('!p-3 text-center', onClick && 'w-full cursor-pointer hover:border-primary-500/35')}
    >
      <p className={cx('text-xl font-bold font-mono', TILE_ACCENT[accent] || TILE_ACCENT.default)}>{value}</p>
      <p className="mt-0.5 text-[10px] uppercase tracking-widest text-dark-400">{label}</p>
    </Card>
  )
}

/* --------------------------------------------------------- Empty / Loading */
export function EmptyState({ children = 'no_entries', icon: Icon, className = '' }) {
  return (
    <div className={cx('py-10 text-center', className)}>
      {Icon && <Icon className="mx-auto mb-2 text-primary-500/30" size={28} />}
      <p className="font-mono text-sm text-dark-500">// {children}</p>
    </div>
  )
}

export function LoadingState({ label, className = '' }) {
  return (
    <div className={cx('py-10 text-center', className)}>
      <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-primary-400 border-t-transparent" />
      <p className="font-mono text-xs uppercase tracking-widest text-dark-500">{label || translate('common.loading')}...</p>
    </div>
  )
}

/* ------------------------------------------------------------------- Modal */
export function Modal({ open, onClose, title, children, maxWidth = 'max-w-md' }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
            className={cx('relative w-full bg-dark-900/95 border border-primary-500/20 rounded-xl p-6 backdrop-blur-xl shadow-2xl', maxWidth)}
          >
            <span className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary-500/50 to-transparent" />
            {title && (
              <h3 className="mb-4 font-mono text-sm font-bold uppercase tracking-widest text-primary-300 flex items-center gap-2">
                <span className="text-primary-500/60">&gt;</span>
                {title}
              </h3>
            )}
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
