import React, { useState } from 'react';

const AnimatedDeleteButton = ({ onDelete, disabled, text = "Delete" }) => {
  const [isDeleting, setIsDeleting] = useState(false);

  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (isDeleting || disabled) return;

    setIsDeleting(true);
    
    // Animation duration is roughly 1.6s
    setTimeout(() => {
      onDelete();
      // Reset state in case the component stays mounted (though usually the item is removed)
      setIsDeleting(false);
    }, 1800);
  };

  return (
    <button 
      className={`animated-delete-btn ${isDeleting ? 'deleting' : ''}`}
      onClick={handleClick}
      disabled={disabled || isDeleting}
      type="button"
    >
      <div className="icon">
        <div className="trash">
          <div className="top"></div>
          <svg viewBox="0 0 24 24">
            <path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19V4Z" />
            <path d="M6,7V19C6,20.1 6.9,21 8,21H16C17.1,21 18,20.1 18,19V7H6ZM14,19H12V11H14V19ZM10,19H8V11H10V19Z" />
          </svg>
        </div>
        <div className="paper"></div>
        <div className="check">
          <svg viewBox="0 0 16 16">
            <polyline points="3 8 7 12 13 4" />
          </svg>
        </div>
      </div>
      <span className="text">{isDeleting ? 'Deleting' : text}</span>
    </button>
  );
};

export default AnimatedDeleteButton;
