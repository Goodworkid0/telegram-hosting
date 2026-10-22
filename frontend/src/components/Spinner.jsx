export default function Spinner({ size = 'md', className = '' }) {
  const sizes = {
    sm: 'w-5 h-5',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
  }
  return (
    <div className={`flex items-center justify-center ${className}`} role="status" aria-label="Loading">
      <div className={`${sizes[size] || sizes.md} border-2 border-primary-400 border-t-transparent rounded-full animate-spin`} />
    </div>
  )
}
