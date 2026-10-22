/**
 * Compatibility shim. RoleBadge is now defined once in the shared UI primitives;
 * this file re-exports it (and a getRoleStyle helper backed by the same role
 * metadata) so existing `import RoleBadge from '../../components/RoleBadge'` and
 * `import { getRoleStyle } from '../../components/RoleBadge'` consumers render the
 * unified badge without changing their imports.
 */
import { RoleBadge, roleStyle } from './ui'

// getRoleStyle returns { labelKey, text, badge }. Consumers use `.text` and
// translate `.labelKey` themselves (roles are i18n'd).
export function getRoleStyle(role) {
  return roleStyle(role)
}

export default RoleBadge
