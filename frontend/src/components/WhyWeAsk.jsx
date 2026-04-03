import { useState } from 'react';

export default function WhyWeAsk({ children }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="why-we-ask">
      <button
        type="button"
        className="why-we-ask-toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className="why-we-ask-icon">?</span>
      </button>
      {open && (
        <div className="why-we-ask-content">
          {children}
        </div>
      )}
    </div>
  );
}
