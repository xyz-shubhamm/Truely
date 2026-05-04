import React from 'react';

const JobDescriptionAnalyzer = ({ description, suspiciousWords = ["registration fee", "no interview", "earn money", "payment", "urgent hiring"] }) => {
  if (!description) return null;

  const lines = description.split('\n').map(line => line.trim()).filter(Boolean);
  
  const importantLines = lines.filter(line => {
    return suspiciousWords.some(word => line.toLowerCase().includes(word.toLowerCase()));
  });

  if (importantLines.length === 0) {
    return null;
  }

  return (
    <div style={{ lineHeight: '1.6', fontSize: '15px', marginTop: '1rem', padding: '1rem', background: 'var(--surface)', borderRadius: '8px', border: '1px solid var(--border)' }}>
      <ul style={{ margin: 0, paddingLeft: '1.5rem', color: 'var(--text)' }}>
        {importantLines.map((line, index) => {
          const regexPattern = new RegExp(`\\b(${suspiciousWords.join('|')})\\b`, 'gi');
          const parts = line.split(regexPattern);
          
          return (
            <li key={index} style={{ marginBottom: '0.8rem' }}>
              {parts.map((part, i) => {
                const isSuspicious = suspiciousWords.some(word => word.toLowerCase() === part.toLowerCase());
                return isSuspicious ? (
                  <span key={i} style={{ backgroundColor: '#ffcccc', color: '#cc0000', fontWeight: 'bold', padding: '0 4px', borderRadius: '4px' }}>
                    {part}
                  </span>
                ) : (
                  <span key={i}>{part}</span>
                );
              })}
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default JobDescriptionAnalyzer;

