// Merged English dictionary. Each domain file owns the strings for one area of
// the app so work on different pages never touches the same file.
import common from './common'
import settings from './settings'
import shop from './shop'
import social from './social'
import files from './files'
import modals from './modals'

export default {
  ...common,
  ...settings,
  ...shop,
  ...social,
  ...files,
  ...modals,
}
