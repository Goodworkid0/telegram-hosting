// Shared modal & utility components (DailyReward, Onboarding, TrialWelcome,
// SessionExpiry, Confirm, Report, UserList, ErrorBoundary, MarkdownToolbar, BannerRows).
export default {
  // Shared
  'modals.maybe_later': 'Maybe later',

  // DailyRewardModal
  'modals.daily.title': 'Daily Reward',
  'modals.daily.streak_line': 'Day {n} streak! Keep it going!',
  'modals.daily.come_back': 'Come back daily for bigger rewards!',
  'modals.daily.xp_bonus': 'XP Bonus',
  'modals.daily.balance_bonus': 'Balance Bonus',
  'modals.daily.badge': 'Badge',
  'modals.daily.streak': 'Streak',
  'modals.daily.day_n': 'Day {n}',
  'modals.daily.claiming': 'Claiming...',
  'modals.daily.claim': 'Claim Reward',

  // OnboardingModal
  'modals.onboarding.pw_min': 'Password must be at least 6 characters',
  'modals.onboarding.pw_digit': 'Password must contain at least 1 digit',
  'modals.onboarding.name_required': 'Display name is required',
  'modals.onboarding.pw_mismatch': 'Passwords do not match',
  'modals.onboarding.setup_failed': 'Setup failed',
  'modals.onboarding.title': 'Welcome to Forum',
  'modals.onboarding.subtitle': 'Choose a username and password to secure your account',
  'modals.onboarding.display_name': 'Display Name',
  'modals.onboarding.display_name_ph': 'Your name',
  'modals.onboarding.display_name_hint': 'Shown on your profile, threads and posts. Changing it later costs $20.',
  'modals.onboarding.password': 'Password',
  'modals.onboarding.password_ph': '6+ characters, 1+ digit',
  'modals.onboarding.password_hint': 'Must be 6+ characters with at least 1 digit',
  'modals.onboarding.confirm_password': 'Confirm Password',
  'modals.onboarding.confirm_password_ph': 're-enter password',
  'modals.onboarding.show_handle': 'Show my Telegram handle',
  'modals.onboarding.handle_desc_before': 'Your ',
  'modals.onboarding.handle_desc_after': ' will be visible on your profile, threads and posts. Turn this off to show only your display name. You can change it anytime in Settings.',
  'modals.onboarding.creating': 'Creating account...',
  'modals.onboarding.enter': 'Enter Forum',
  'modals.onboarding.ready_title': 'Account Ready',
  'modals.onboarding.ready_subtitle': 'Your account is set up. Now customize your profile.',
  'modals.onboarding.set_avatar': 'Set Profile Picture',
  'modals.onboarding.set_avatar_desc': 'Upload an avatar so people recognize you',
  'modals.onboarding.write_bio': 'Write Your Bio',
  'modals.onboarding.write_bio_desc': 'Tell the community about yourself',
  'modals.onboarding.settings': 'Configure Settings',
  'modals.onboarding.settings_desc': 'Notification preferences and account options',
  'modals.onboarding.skip': 'Skip for now',

  // TrialWelcomeModal
  'modals.trial.title': 'Welcome to the Forum!',
  'modals.trial.intro_before': "You're currently in ",
  'modals.trial.intro_mode': 'Trial Mode',
  'modals.trial.intro_after': ' with limited access.',
  'modals.trial.step1_title': 'Introduce Yourself',
  'modals.trial.step1_before': 'Post in ',
  'modals.trial.step1_board': 'Request Full Access',
  'modals.trial.step1_after': " — tell the community who you are and why you're here.",
  'modals.trial.step2_title': 'Earn Reputation',
  'modals.trial.step2_desc': 'Existing members will read your intro and give you +rep if they think you should get access.',
  'modals.trial.step3_title': 'Earn Full Access',
  'modals.trial.step3_before': 'Earn ',
  'modals.trial.step3_strong': '+rep from established members',
  'modals.trial.step3_after': ' and an admin will upgrade you to a full member!',
  'modals.trial.request_access': 'Request Full Access',
  'modals.trial.purchase_premium': 'Purchase Premium',

  // SessionExpiryModal
  'modals.session.title': 'Session Expiring',
  'modals.session.expires_in': 'Expires in {time}',
  'modals.session.body': 'Your login session is about to expire due to inactivity. Would you like to stay logged in?',
  'modals.session.logout': 'Log out',
  'modals.session.stay': 'Stay logged in',

  // ConfirmModal
  'modals.confirm.title': 'Confirm action',

  // ReportModal
  'modals.report.intro': 'Report {target} to the moderators.',
  'modals.report.target_post': 'this post',
  'modals.report.target_thread': 'this thread',
  'modals.report.target_user': 'this user',
  'modals.report.reason': 'Reason',
  'modals.report.reason_spam': 'Spam',
  'modals.report.reason_scam': 'Scam or fraud',
  'modals.report.reason_abuse': 'Abusive behavior',
  'modals.report.reason_illegal': 'Illegal content',
  'modals.report.reason_other': 'Other',
  'modals.report.details': 'Details (optional)',
  'modals.report.details_ph': 'Anything that helps the moderators understand the issue...',
  'modals.report.submitted': 'Report submitted — a moderator will review it',
  'modals.report.failed': 'Failed to submit report',
  'modals.report.submitting': 'Submitting…',
  'modals.report.submit': 'Submit Report',

  // UserListModal
  'modals.userlist.empty': 'Nobody here yet',

  // ErrorBoundary
  'modals.error.title': 'Something went wrong',
  'modals.error.body': 'An unexpected error occurred. Please try going back to the home page.',
  'modals.error.go_home': 'Go Home',

  // MarkdownToolbar
  'modals.md.bold': 'Bold',
  'modals.md.italic': 'Italic',
  'modals.md.strikethrough': 'Strikethrough',
  'modals.md.h1': 'Heading 1',
  'modals.md.h2': 'Heading 2',
  'modals.md.inline_code': 'Inline code',
  'modals.md.code_block': 'Code block',
  'modals.md.insert_link': 'Insert link',
  'modals.md.quote': 'Quote',
  'modals.md.list': 'List',
  'modals.md.upload_image': 'Upload image',
  'modals.md.invalid_url': 'Enter a valid URL',
  'modals.md.upload_failed': 'Image upload failed',
  'modals.md.link_text_ph': 'Link text (optional)',
  'modals.md.insert': 'Insert',

  // BannerRows
  'modals.banner.learn_more': 'Learn More',
}
