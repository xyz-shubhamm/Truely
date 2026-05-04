import re
from pathlib import Path
import joblib

# Load model
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_ROOT / 'artifacts' / 'personal_job_model.pkl'
model = joblib.load(MODEL_PATH)

hard_cases = [
    {
        "name": "Legitimate Finance Role (False Positive Risk)",
        "schema": {
            "Job Title": "Senior Accounts Payable Specialist",
            "Company Name": "Enterprise Bank",
            "Job Description": "You will be responsible for initiating wire transfers, handling processing fees for international clients, and ensuring payment before shipment is verified. Base salary is $85k with excellent benefits."
        }
    },
    {
        "name": "Highly Sophisticated Scam (False Negative Risk)",
        "schema": {
            "Job Title": "Data Entry Representative",
            "Company Name": "Growing Tech Startup",
            "Job Description": "Work from home opportunity for a growing tech startup. We offer a flexible schedule and provide all necessary equipment. Upon hiring, we will send a check to cover your home office setup from our approved vendor network."
        }
    },
    {
        "name": "Legitimate High-Salary Startup (False Positive Risk)",
        "schema": {
            "Job Title": "Founding Software Engineer",
            "Company Name": "Stealth AI Startup",
            "Job Description": "We are offering an unparalleled package of 50LPA base + massive equity. You must be willing to join immediately and work extremely fast in a high-pressure environment."
        }
    },
    {
        "name": "Standard Real Job - Software Engineering",
        "schema": {
            "Job Title": "Full Stack Developer",
            "Company Name": "TechCorp Solutions",
            "Job Description": "We are looking for an experienced Full Stack Developer with 3+ years of experience in React and Node.js. Responsibilities include building scalable web applications, collaborating with cross-functional teams, and writing clean, maintainable code. Comprehensive health benefits and 401(k) matching provided."
        }
    },
    {
        "name": "Blatant Scam - Upfront Payment",
        "schema": {
            "Job Title": "Customer Service Agent (Remote)",
            "Company Name": "Global Support Group",
            "Job Description": "Earn $50/hour working from home! No experience required. To secure your spot and receive your training materials, you must pay a fully refundable registration fee of $150. Start making money tomorrow!"
        }
    },
    {
        "name": "MLM / Pyramid Scheme Scam",
        "schema": {
            "Job Title": "Independent Business Owner",
            "Company Name": "Health & Wealth Network",
            "Job Description": "Be your own boss and achieve financial freedom! Purchase our starter kit for $99 and earn massive commissions by building your downline. Recruit just 3 people and watch your passive income grow."
        }
    },
    {
        "name": "Phishing Scam - Sensitive Info",
        "schema": {
            "Job Title": "Administrative Assistant",
            "Company Name": "National Healthcare Providers",
            "Job Description": "Immediate hiring for administrative assistants. Due to the urgency of filling this role, we require you to provide your Social Security Number, bank account details for direct deposit, and a copy of your ID before the interview process."
        }
    },
    {
        "name": "Legitimate Customer Service Role",
        "schema": {
            "Job Title": "Customer Success Representative",
            "Company Name": "SaaS Platform Inc.",
            "Job Description": "Join our support team to help clients navigate our software platform. Requirements: excellent communication skills, ability to troubleshoot technical issues, and high empathy. Shift hours may vary. Includes medical, dental, and paid time off."
        }
    },
    {
        "name": "Scam - Personal Contact & Urgency",
        "schema": {
            "Job Title": "Office Manager - URGENT",
            "Company Name": "Confidential",
            "Job Description": "Urgent hiring! We need an office manager to start today. High salary paid weekly in cash. Do not apply through the platform, send your resume directly to our HR manager at urgent.hiring.manager2024@gmail.com or text us on WhatsApp."
        }
    },
    {
        "name": "Legitimate Freelance/Contract Work",
        "schema": {
            "Job Title": "Freelance Graphic Designer",
            "Company Name": "Creative Agency LLC",
            "Job Description": "Looking for a talented graphic designer for a 3-month contract to help rebrand our flagship product. Must have a strong portfolio demonstrating expertise in Adobe Creative Suite and Figma. Compensation is $45/hr."
        }
    }
]

print('=== TESTING HARD EDGE CASES (USING 3-FIELD SCHEMA) ===\n')

for case in hard_cases:
    print(f'--- {case["name"]} ---')
    
    # Combine the 3 fields just like the real API does
    test_text = f"{case['schema']['Job Title']} {case['schema']['Company Name']} {case['schema']['Job Description']}"
    probs = model.predict_proba([test_text])[0]
    
    print(f'Job Title: "{case["schema"]["Job Title"]}"')
    print(f'Company Name: "{case["schema"]["Company Name"]}"')
    print(f'Job Description: "{case["schema"]["Job Description"]}"')
    print(f'-> Raw Model Fraud Probability: {100*probs[1]:.1f}%')
    
    # Red flag detection
    text_lower = test_text.lower()
    critical_flags = []
    payment_patterns = [
        (r'entry\s+fee|registration\s+fee|upfront\s+payment|deposit\s+required|pay\s+.*\s+before|transfer\s+fee|processing\s+fee', 'Entry/Payment Fee Required'),
        (r'wire\s+transfer|wire\s+money|send\s+money|payment\s+before|upfront\s+cost', 'Upfront Payment Demanded'),
        (r'\$\d+.*fee|£\d+.*fee', 'Explicit Fee Amount'),
    ]
    
    for pattern, label in payment_patterns:
        if re.search(pattern, text_lower):
            critical_flags.append(label)
            print(f'[FLAG] Detected: {label}')
            
    if critical_flags:
        boost = 2.5 if any('Entry' in f or 'Payment' in f for f in critical_flags) else 1.5
        boosted = min(probs[1] * boost, 1.0)
        boosted = max(boosted, 0.85)
        print(f'Final Boosted Probability: {100*boosted:.1f}%\n')
    else:
        print('Final Probability: Same as Raw\n')

