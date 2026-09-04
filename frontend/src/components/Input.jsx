export function Input({
  id,
  label,
  hint,
  error,
  className = '',
  ...rest
}) {
  const inputId = id || rest.name
  return (
    <div className={`field ${className}`.trim()}>
      {label ? (
        <label className="field__label" htmlFor={inputId}>
          {label}
        </label>
      ) : null}
      <input
        id={inputId}
        className={`input${error ? ' input--error' : ''}`}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
        {...rest}
      />
      {hint && !error ? (
        <span id={`${inputId}-hint`} className="field__hint">
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={`${inputId}-error`} className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  )
}
