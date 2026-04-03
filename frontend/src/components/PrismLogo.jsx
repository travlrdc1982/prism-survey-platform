export default function PrismLogo({ size = 'md' }) {
  const sizes = { sm: 28, md: 44, lg: 64 };
  const dim = sizes[size] || sizes.md;
  const textSize = size === 'lg' ? 20 : size === 'md' ? 14 : 10;

  return (
    <div
      className="prism-logo"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: size === 'lg' ? 8 : 4,
      }}
    >
      <img
        src="/prism_glyph.svg"
        alt="PRISM logo"
        width={dim}
        height={dim}
        style={{ display: 'block' }}
        onError={(e) => {
          // Fallback: hide broken image
          e.target.style.display = 'none';
        }}
      />
      <span
        style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontWeight: 700,
          fontSize: textSize,
          letterSpacing: 3,
          color: '#2C261C',
          textTransform: 'uppercase',
        }}
      >
        PRISM
      </span>
    </div>
  );
}
