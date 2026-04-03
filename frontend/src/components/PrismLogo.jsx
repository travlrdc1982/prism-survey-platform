export default function PrismLogo({ size = 'md' }) {
  const sizes = { sm: 28, md: 44, lg: 64 };
  const dim = sizes[size] || sizes.md;
  const fontSize = dim * 0.45;

  return (
    <div
      className="prism-logo"
      style={{
        width: dim,
        height: dim,
        fontSize: `${fontSize}px`,
      }}
    >
      <svg viewBox="0 0 44 44" width={dim} height={dim} aria-label="PRISM logo">
        <defs>
          <linearGradient id="prism-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#6B7F4E" />
            <stop offset="100%" stopColor="#4A5A35" />
          </linearGradient>
        </defs>
        <polygon
          points="22,2 42,38 2,38"
          fill="url(#prism-grad)"
          stroke="#4A5A35"
          strokeWidth="1"
        />
        <text
          x="22"
          y="30"
          textAnchor="middle"
          fill="#FFFFFF"
          fontFamily="'Fraunces', Georgia, serif"
          fontWeight="700"
          fontSize="14"
        >
          P
        </text>
      </svg>
    </div>
  );
}
