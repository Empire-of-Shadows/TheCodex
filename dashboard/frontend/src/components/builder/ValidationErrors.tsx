interface Props {
  errors: string[];
}

export default function ValidationErrors({ errors }: Props) {
  if (errors.length === 0) return null;
  return (
    <div className="validation-errors">
      <h4>Validation Errors</h4>
      <ul>
        {errors.map((err, i) => (
          <li key={i}>{err}</li>
        ))}
      </ul>
    </div>
  );
}
