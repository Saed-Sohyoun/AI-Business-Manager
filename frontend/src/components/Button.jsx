export function Button({
  children,
  variant = 'secondary',
  size = 'md',
  type = 'button',
  disabled = false,
  onClick,
  className = '',
  ...rest
}) {
  const classes = ['btn', `btn--${variant}`, size !== 'md' ? `btn--${size}` : '', className]
    .filter(Boolean)
    .join(' ')

  return (
    <button type={type} className={classes} disabled={disabled} onClick={onClick} {...rest}>
      {children}
    </button>
  )
}
