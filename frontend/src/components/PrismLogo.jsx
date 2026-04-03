export default function PrismLogo({ size = 'md' }) {
  const sizes = { sm: 20, md: 32, lg: 40 };
  const dim = sizes[size] || sizes.md;

  return (
    <div
      className="prism-logo"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}
    >
      <img
        src="/prism_glyph.svg"
        alt="PRISM"
        width={dim}
        height={dim}
        style={{ display: 'block' }}
        onError={(e) => { e.target.style.display = 'none'; }}
      />
    </div>
  );
}
