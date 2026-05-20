// Reusable input component for forms. Supports text, email, tel, password, select, textarea.
export default function InputField({
  label,
  name,
  type = 'text',
  value = '',
  onChange,
  placeholder,
  options,        // for type="select"
  rows = 3,       // for type="textarea"
  required = false,
  disabled = false,
  hint,
  error,
}) {
  const inputClass =
    'w-full rounded-lg border bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 shadow-sm transition focus:outline-none focus:ring-2 ' +
    (error
      ? 'border-red-300 focus:border-red-400 focus:ring-red-100'
      : 'border-slate-200 focus:border-brand-600 focus:ring-brand-100') +
    (disabled ? ' bg-slate-50 cursor-not-allowed text-slate-500' : '');

  const inputProps = {
    id: name,
    name,
    value,
    onChange,
    placeholder,
    required,
    disabled,
    className: inputClass,
  };

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={name} className="text-xs font-semibold text-slate-700">
          {label}
          {required && <span className="ml-0.5 text-red-500">*</span>}
        </label>
      )}
      {type === 'textarea' ? (
        <textarea {...inputProps} rows={rows} />
      ) : type === 'select' ? (
        <select {...inputProps}>
          {options && options.map((o) =>
            typeof o === 'string'
              ? <option key={o} value={o}>{o}</option>
              : <option key={o.value} value={o.value}>{o.label}</option>
          )}
        </select>
      ) : (
        <input {...inputProps} type={type} />
      )}
      {error ? (
        <p className="text-xs text-red-600">{error}</p>
      ) : hint ? (
        <p className="text-xs text-slate-500">{hint}</p>
      ) : null}
    </div>
  );
}
