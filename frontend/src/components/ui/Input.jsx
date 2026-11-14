import { forwardRef, useId } from 'react';

/**
 * Labelled text field: surface-2 background, 1px border, 8px radius and a
 * 2px accent focus ring. `multiline` renders a textarea.
 */
const Input = forwardRef(function Input(
  { label, hint, error, multiline = false, id, className = '', inputClassName = '', ...rest },
  ref,
) {
  const autoId = useId();
  const fieldId = id || autoId;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const Control = multiline ? 'textarea' : 'input';

  return (
    <div className={`m-field ${error ? 'm-field--error' : ''} ${className}`.trim()}>
      {label && <label className="m-field__label" htmlFor={fieldId}>{label}</label>}
      <Control
        ref={ref}
        id={fieldId}
        className={`m-input ${inputClassName}`.trim()}
        aria-invalid={error ? true : undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined}
        {...rest}
      />
      {hint && !error && <p className="m-field__hint" id={hintId}>{hint}</p>}
      {error && <p className="m-field__error" id={errorId} role="alert">{error}</p>}
    </div>
  );
});

export default Input;
