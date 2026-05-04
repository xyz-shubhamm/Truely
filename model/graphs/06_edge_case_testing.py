"""
Graph 06: Edge Case Testing Results
Horizontal bar chart showing fraud probability for 10 hard edge cases.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import joblib

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / 'model'))
MODEL_PATH = ROOT / 'artifacts' / 'personal_job_model.pkl'
OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

hard_cases = [
    ("Legitimate Finance Role", {
        "Job Title": "Senior Accounts Payable Specialist",
        "Company Name": "Enterprise Bank",
        "Job Description": "You will be responsible for initiating wire transfers, handling processing fees for international clients, and ensuring payment before shipment is verified. Base salary is $85k with excellent benefits."
    }, "legit"),
    ("Sophisticated Scam", {
        "Job Title": "Data Entry Representative",
        "Company Name": "Growing Tech Startup",
        "Job Description": "Work from home opportunity for a growing tech startup. We offer a flexible schedule and provide all necessary equipment. Upon hiring, we will send a check to cover your home office setup from our approved vendor network."
    }, "scam"),
    ("Legitimate High-Salary Startup", {
        "Job Title": "Founding Software Engineer",
        "Company Name": "Stealth AI Startup",
        "Job Description": "We are offering an unparalleled package of 50LPA base + massive equity. You must be willing to join immediately and work extremely fast in a high-pressure environment."
    }, "legit"),
    ("Standard Real Job", {
        "Job Title": "Full Stack Developer",
        "Company Name": "TechCorp Solutions",
        "Job Description": "We are looking for an experienced Full Stack Developer with 3+ years of experience in React and Node.js. Responsibilities include building scalable web applications, collaborating with cross-functional teams, and writing clean, maintainable code. Comprehensive health benefits and 401(k) matching provided."
    }, "legit"),
    ("Blatant Scam - Upfront Payment", {
        "Job Title": "Customer Service Agent (Remote)",
        "Company Name": "Global Support Group",
        "Job Description": "Earn $50/hour working from home! No experience required. To secure your spot and receive your training materials, you must pay a fully refundable registration fee of $150. Start making money tomorrow!"
    }, "scam"),
    ("MLM / Pyramid Scheme", {
        "Job Title": "Independent Business Owner",
        "Company Name": "Health & Wealth Network",
        "Job Description": "Be your own boss and achieve financial freedom! Purchase our starter kit for $99 and earn massive commissions by building your downline. Recruit just 3 people and watch your passive income grow."
    }, "scam"),
    ("Phishing Scam", {
        "Job Title": "Administrative Assistant",
        "Company Name": "National Healthcare Providers",
        "Job Description": "Immediate hiring for administrative assistants. Due to the urgency of filling this role, we require you to provide your Social Security Number, bank account details for direct deposit, and a copy of your ID before the interview process."
    }, "scam"),
    ("Legitimate Customer Service", {
        "Job Title": "Customer Success Representative",
        "Company Name": "SaaS Platform Inc.",
        "Job Description": "Join our support team to help clients navigate our software platform. Requirements: excellent communication skills, ability to troubleshoot technical issues, and high empathy. Shift hours may vary. Includes medical, dental, and paid time off."
    }, "legit"),
    ("Scam - Personal Contact", {
        "Job Title": "Office Manager - URGENT",
        "Company Name": "Confidential",
        "Job Description": "Urgent hiring! We need an office manager to start today. High salary paid weekly in cash. Do not apply through the platform, send your resume directly to our HR manager at urgent.hiring.manager2024@gmail.com or text us on WhatsApp."
    }, "scam"),
    ("Legitimate Freelance", {
        "Job Title": "Freelance Graphic Designer",
        "Company Name": "Creative Agency LLC",
        "Job Description": "Looking for a talented graphic designer for a 3-month contract to help rebrand our flagship product. Must have a strong portfolio demonstrating expertise in Adobe Creative Suite and Figma. Compensation is $45/hr."
    }, "legit"),
]

def main():
    model = joblib.load(MODEL_PATH)
    
    names = []
    probabilities = []
    colors = []
    
    payment_patterns = [
        (r'entry\s+fee|registration\s+fee|upfront\s+payment|deposit\s+required|pay\s+.*\s+before|transfer\s+fee|processing\s+fee', 'Entry/Payment Fee'),
        (r'wire\s+transfer|wire\s+money|send\s+money|payment\s+before|upfront\s+cost', 'Upfront Payment'),
        (r'\$\d+.*fee', 'Explicit Fee'),
    ]
    
    for name, schema, true_label in hard_cases:
        text = f"{schema['Job Title']} {schema['Company Name']} {schema['Job Description']}"
        probs = model.predict_proba([text])[0]
        raw_prob = probs[1]
        
        # Apply heuristic boost like test_prediction.py does
        text_lower = text.lower()
        critical_flags = []
        for pattern, _ in payment_patterns:
            if re.search(pattern, text_lower):
                critical_flags.append(True)
        
        if critical_flags:
            boosted = min(raw_prob * 2.5, 1.0)
            boosted = max(boosted, 0.85)
            final_prob = boosted
        else:
            final_prob = raw_prob
        
        names.append(name)
        probabilities.append(final_prob * 100)
        colors.append('#2ca02c' if true_label == 'legit' else '#d62728')
    
    fig, ax = plt.subplots(figsize=(12, 8))
    y_pos = np.arange(len(names))
    bars = ax.barh(y_pos, probabilities, color=colors, edgecolor='black', height=0.6)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel('Fraud Probability (%)', fontsize=12)
    ax.set_title('Edge Case Testing: Model Fraud Probability by Case', fontsize=14, fontweight='bold')
    ax.axvline(x=50, color='black', linestyle='--', alpha=0.7, label='50% Threshold')
    ax.legend()
    ax.grid(True, axis='x', alpha=0.3)
    ax.set_xlim(0, 105)
    
    for bar, prob in zip(bars, probabilities):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2, 
                f'{prob:.1f}%', va='center', fontsize=10, fontweight='bold')
    
    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor='#2ca02c', edgecolor='black', label='Legitimate'),
                       Patch(facecolor='#d62728', edgecolor='black', label='Scam')]
    ax.legend(handles=legend_elements, loc='lower right')
    
    plt.tight_layout()
    out_path = OUT_DIR / '06_edge_case_testing.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()
