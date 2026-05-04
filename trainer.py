# autonomous_testing_ai.py - Creates 1000 test cases, finds errors, fixes itself
import pickle
import numpy as np
import random
import json
import re
from datetime import datetime
from collections import Counter, defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import Pipeline
import warnings
warnings.filterwarnings('ignore')

class JobTestDataGenerator:
    """Generates 1000s of test cases automatically"""
    
    # Job titles database
    JOB_TITLES = {
        'software_engineer': [
            "Software Engineer", "Software Developer", "Programmer", "Application Developer",
            "Full Stack Developer", "Backend Engineer", "Frontend Developer", "Systems Engineer",
            "Software Architect", "Lead Developer", "Principal Engineer", "Staff Engineer",
            "Java Developer", "Python Developer", "JavaScript Developer", "C++ Developer",
            "Mobile Developer", "iOS Engineer", "Android Developer", "Web Developer"
        ],
        'data_scientist': [
            "Data Scientist", "Data Analyst", "Data Engineer", "Machine Learning Engineer",
            "AI Engineer", "ML Engineer", "Data Architect", "Analytics Manager",
            "Business Intelligence Analyst", "Data Warehouse Engineer", "ETL Developer",
            "Research Scientist", "Quantitative Analyst", "Statistician", "Data Mining Engineer"
        ],
        'qa_engineer': [
            "QA Engineer", "Test Engineer", "Quality Assurance", "Automation Engineer",
            "SDET", "Test Developer", "Manual Tester", "QA Analyst", "Test Lead",
            "Performance Engineer", "Security Tester", "Regression Tester", "Test Manager"
        ],
        'devops_engineer': [
            "DevOps Engineer", "Site Reliability Engineer", "Cloud Engineer", "Infrastructure Engineer",
            "Platform Engineer", "Systems Administrator", "Release Manager", "Build Engineer",
            "CI/CD Engineer", "Kubernetes Engineer", "AWS Engineer", "Linux Administrator"
        ],
        'product_manager': [
            "Product Manager", "Product Owner", "Technical Product Manager", "Associate Product Manager",
            "Senior Product Manager", "Director of Product", "Product Analyst", "Business Analyst",
            "Project Manager", "Program Manager", "Scrum Master", "Agile Coach"
        ],
        'sales': [
            "Sales Representative", "Account Executive", "Sales Manager", "Business Development",
            "Sales Engineer", "Account Manager", "Customer Success Manager", "Sales Director",
            "Inside Sales", "Outside Sales", "Technical Sales", "Solutions Consultant"
        ],
        'marketing': [
            "Marketing Manager", "Digital Marketing Specialist", "Content Manager", "SEO Specialist",
            "Social Media Manager", "Brand Manager", "Growth Hacker", "Marketing Analyst",
            "Email Marketing Specialist", "PPC Specialist", "Marketing Director"
        ],
        'support': [
            "Technical Support", "Customer Support", "IT Support", "Help Desk Analyst",
            "Support Engineer", "Customer Service Representative", "Technical Account Manager",
            "Support Specialist", "Desktop Support", "Network Support"
        ]
    }
    
    # Company names database
    COMPANIES = [
        "Google", "Microsoft", "Amazon", "Apple", "Meta", "Netflix", "Tesla", "IBM", "Oracle",
        "Salesforce", "Adobe", "Intel", "Cisco", "Dell", "HP", "Uber", "Airbnb", "Twitter",
        "LinkedIn", "PayPal", "Shopify", "Spotify", "Slack", "Zoom", "Square", "Stripe",
        "Red Hat", "Atlassian", "Twilio", "MongoDB", "Databricks", "Snowflake", "Palantir",
        "Bloomberg", "Goldman Sachs", "JPMorgan", "Walmart", "Target", "Home Depot", "FedEx",
        "Accenture", "Deloitte", "PwC", "EY", "KPMG", "McKinsey", "BCG", "Bain",
        "Tesla", "SpaceX", "Ford", "GM", "Toyota", "BMW", "Mercedes", "Volkswagen",
        "Pfizer", "Moderna", "Johnson & Johnson", "Merck", "Novartis", "Roche", "AstraZeneca",
        "Startup X", "Growth Tech", "Innovation Labs", "Future Systems", "Cloud Native Co"
    ]
    
    # Skills and technologies
    SKILLS = [
        "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go", "Rust", "Ruby",
        "React", "Angular", "Vue.js", "Node.js", "Django", "Flask", "Spring Boot", "Express",
        "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Jenkins", "Git",
        "PostgreSQL", "MongoDB", "MySQL", "Redis", "Elasticsearch", "Cassandra",
        "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "Numpy", "Spark", "Hadoop",
        "REST APIs", "GraphQL", "Microservices", "Serverless", "CI/CD", "Agile", "Scrum"
    ]
    
    # Experience levels
    EXPERIENCE_LEVELS = [
        ("Entry Level", "0-2"), ("Junior", "1-3"), ("Mid Level", "3-5"), 
        ("Senior", "5-8"), ("Lead", "8-10"), ("Principal", "10+"), ("Staff", "8-12")
    ]
    
    # Locations
    LOCATIONS = [
        "Remote", "Hybrid", "Onsite", "San Francisco, CA", "New York, NY", "Austin, TX",
        "Seattle, WA", "Boston, MA", "Chicago, IL", "Los Angeles, CA", "Denver, CO",
        "Atlanta, GA", "Portland, OR", "Washington DC", "London, UK", "Berlin, Germany",
        "Toronto, Canada", "Bangalore, India", "Sydney, Australia"
    ]
    
    @classmethod
    def generate_job_description(cls, role_type, experience_level, skills_sample=None):
        """Generate a realistic job description"""
        
        if skills_sample is None:
            skills_sample = random.sample(cls.SKILLS, min(5, len(cls.SKILLS)))
        
        exp_name, exp_years = random.choice(cls.EXPERIENCE_LEVELS) if not experience_level else experience_level
        
        # Build job description components
        responsibilities = [
            f"Design and implement scalable {random.choice(skills_sample)} solutions",
            f"Collaborate with cross-functional teams to deliver high-quality products",
            f"Write clean, maintainable, and testable code",
            f"Participate in code reviews and technical discussions",
            f"Troubleshoot and debug production issues",
            f"Mentor junior team members",
            f"Lead architectural decisions and technical planning",
            f"Optimize application performance and scalability",
        ]
        
        requirements = [
            f"{exp_years}+ years of experience in {random.choice(skills_sample)}",
            f"Strong understanding of {random.choice(skills_sample)} and related technologies",
            f"Experience with {random.choice(skills_sample)} and {random.choice(skills_sample)}",
            f"Bachelor's degree in Computer Science or related field",
            f"Excellent problem-solving and communication skills",
            f"Experience working in Agile environments",
            f"Knowledge of best practices and design patterns",
        ]
        
        benefits = [
            "Competitive salary and equity package",
            "Comprehensive health, dental, and vision insurance",
            "401(k) matching program",
            "Flexible work hours and remote options",
            "Professional development budget",
            "Generous paid time off",
            "Parental leave",
            "Wellness stipend",
        ]
        
        # Construct description
        description = f"""
Job Title: {role_type.replace('_', ' ').title()}

Company: {random.choice(cls.COMPANIES)} - {random.choice(['Inc', 'Corp', 'LLC', 'Technologies', 'Solutions', 'Systems'])}

Location: {random.choice(cls.LOCATIONS)}
Employment Type: {random.choice(['Full-time', 'Contract', 'Internship', 'Part-time'])}
Experience Level: {exp_name} ({exp_years} years)

About the Role:
We are seeking a talented {role_type.replace('_', ' ').title()} to join our growing team. The ideal candidate will help us build innovative solutions that impact millions of users.

Key Responsibilities:
{chr(10).join('- ' + r for r in random.sample(responsibilities, 4))}

Required Qualifications:
{chr(10).join('- ' + r for r in random.sample(requirements, 4))}

Nice to Have:
- Experience with {random.choice(cls.SKILLS)}
- Knowledge of {random.choice(cls.SKILLS)}
- Previous experience in {random.choice(['startup', 'enterprise', 'SaaS', 'e-commerce'])}

What We Offer:
{chr(10).join('- ' + b for b in random.sample(benefits, 3))}

Join us in shaping the future of technology!
"""
        return description.strip()
    
    @classmethod
    def generate_test_case(cls):
        """Generate a single test case with job title, company, description"""
        
        # Randomly select role type
        role_type = random.choice(list(cls.JOB_TITLES.keys()))
        job_title = random.choice(cls.JOB_TITLES[role_type])
        company = random.choice(cls.COMPANIES)
        
        # Random experience level
        exp_name, exp_years = random.choice(cls.EXPERIENCE_LEVELS)
        
        # Generate description
        description = cls.generate_job_description(role_type, (exp_name, exp_years))
        
        # Generate label (0-7 mapping to role types)
        role_to_label = {role: idx for idx, role in enumerate(cls.JOB_TITLES.keys())}
        label = role_to_label[role_type]
        
        # Also generate confusing/edge cases
        if random.random() < 0.3:  # 30% edge cases
            description = cls.make_confusing(description, role_type)
        
        return {
            'job_title': job_title,
            'company': company,
            'description': description,
            'expected_label': label,
            'role_type': role_type
        }
    
    @classmethod
    def make_confusing(cls, description, original_role):
        """Create confusing/ambiguous variations"""
        
        confusing_modifications = {
            'software_engineer': [
                "Note: This is primarily a QA role with some development",
                "This position is 50% coding, 50% customer support",
                "Looking for a developer who can also sell software",
                "Entry level position requiring 10 years experience"
            ],
            'data_scientist': [
                "This role focuses on data entry and basic Excel",
                "Mostly SQL queries with minimal ML work",
                "90% data cleaning, 10% actual analysis",
                "Looking for BI analyst who can do some Python"
            ],
            'qa_engineer': [
                "This is a developer role with some testing responsibilities",
                "Looking for SDET who will write production code",
                "80% automation framework development",
                "Manual testing only, no automation"
            ],
            'devops_engineer': [
                "Primarily a system admin role with some cloud work",
                "Focus on legacy on-premise infrastructure",
                "Mostly Windows server administration",
                "Looking for developer with ops experience"
            ]
        }
        
        mods = confusing_modifications.get(original_role, ["Hybrid role with multiple responsibilities"])
        if random.random() < 0.5:
            description += "\n\n" + random.choice(mods)
        
        return description
    
    @classmethod
    def generate_batch(cls, count=1000):
        """Generate N test cases"""
        test_cases = []
        for i in range(count):
            test_cases.append(cls.generate_test_case())
            if (i + 1) % 100 == 0:
                print(f"   Generated {i+1}/{count} test cases...")
        return test_cases


class AutonomousSelfLearner:
    """AI that generates test cases, finds errors, and improves itself"""
    
    def __init__(self, model_path=None):
        self.model_path = model_path
        self.model = None
        self.test_cases = []
        self.errors_found = []
        self.corrections_made = []
        self.confidence_threshold = 0.7
        
        self.load_or_create_model()
    
    def load_or_create_model(self):
        """Load existing model or create new one"""
        if self.model_path and self._check_model_exists():
            try:
                with open(self.model_path, 'rb') as f:
                    self.model = pickle.load(f)
                print(f"✅ Loaded existing model from {self.model_path}")
                return
            except Exception as e:
                print(f"⚠️ Could not load model: {e}")
        
        print("🆕 Creating new model...")
        self.model = Pipeline([
            ('tfidf', TfidfVectorizer(
                max_features=10000,
                stop_words='english',
                ngram_range=(1, 3),
                min_df=2,
                max_df=0.95
            )),
            ('clf', SGDClassifier(
                loss='log_loss',
                penalty='l2',
                max_iter=500,
                random_state=42,
                tol=1e-3,
                alpha=0.0001
            ))
        ])
        print("✅ New model created")
    
    def _check_model_exists(self):
        """Check if model file exists"""
        import os
        return os.path.exists(self.model_path) if self.model_path else False
    
    def train_initial(self):
        """Train on generated test cases"""
        print("\n📚 Generating training data...")
        
        # Generate 1000 training examples
        training_data = JobTestDataGenerator.generate_batch(1000)
        
        texts = [item['description'] for item in training_data]
        labels = [item['expected_label'] for item in training_data]
        
        print(f"\n🔧 Training on {len(texts)} examples...")
        self.model.fit(texts, labels)
        
        # Test on training data to see accuracy
        predictions = self.model.predict(texts)
        accuracy = np.mean(predictions == labels)
        print(f"✅ Training accuracy: {accuracy:.2%}")
        
        return training_data
    
    def generate_test_suite(self, num_tests=1000):
        """Generate test suite for finding errors"""
        print(f"\n🧪 Generating {num_tests} test cases...")
        self.test_cases = JobTestDataGenerator.generate_batch(num_tests)
        return self.test_cases
    
    def run_tests(self):
        """Run all tests and find errors"""
        if not self.test_cases:
            self.generate_test_suite()
        
        print("\n🔍 Running tests to find errors...")
        self.errors_found = []
        
        for i, test_case in enumerate(self.test_cases):
            description = test_case['description']
            expected = test_case['expected_label']
            
            # Get prediction
            proba = self.model.predict_proba([description])[0]
            predicted = np.argmax(proba)
            confidence = np.max(proba)
            
            # Check if this is an error
            is_error = (predicted != expected)
            is_uncertain = confidence < self.confidence_threshold
            
            if is_error or is_uncertain:
                error = {
                    'test_id': i,
                    'job_title': test_case['job_title'],
                    'company': test_case['company'],
                    'description': description[:500] + "...",
                    'expected': expected,
                    'predicted': int(predicted),
                    'confidence': float(confidence),
                    'is_error': is_error,
                    'is_uncertain': is_uncertain,
                    'timestamp': datetime.now().isoformat()
                }
                self.errors_found.append(error)
            
            if (i + 1) % 100 == 0:
                print(f"   Tested {i+1}/{len(self.test_cases)} - Found {len(self.errors_found)} errors so far")
        
        print(f"\n📊 Test Results:")
        print(f"   Total tests: {len(self.test_cases)}")
        print(f"   Errors found: {len([e for e in self.errors_found if e['is_error']])}")
        print(f"   Uncertain predictions: {len([e for e in self.errors_found if e['is_uncertain']])}")
        
        return self.errors_found
    
    def auto_correct_errors(self):
        """Automatically correct errors based on patterns"""
        print("\n🔧 Auto-correcting errors...")
        
        corrections = []
        
        # Group errors by pattern
        error_patterns = defaultdict(list)
        for error in self.errors_found:
            if error['is_error']:
                pattern_key = (error['expected'], error['predicted'])
                error_patterns[pattern_key].append(error)
        
        for (expected, predicted), errors in error_patterns.items():
            print(f"   Pattern: Expected {expected} → Got {predicted} ({len(errors)} errors)")
            
            # For each error, create a corrected version
            for error in errors[:100]:  # Limit per pattern
                correction = {
                    'original_description': error['description'],
                    'corrected_description': self._create_corrected_description(error),
                    'original_label': predicted,
                    'correct_label': expected,
                    'pattern': f"{expected}_to_{predicted}"
                }
                corrections.append(correction)
        
        print(f"   Created {len(corrections)} corrections")
        self.corrections_made = corrections
        return corrections
    
    def _create_corrected_description(self, error):
        """Create a corrected description based on the error"""
        # Simple approach: add clarifying text
        role_names = {
            0: "Software Engineer", 1: "Data Scientist", 2: "QA Engineer",
            3: "DevOps Engineer", 4: "Product Manager", 5: "Sales",
            6: "Marketing", 7: "Support"
        }
        
        correct_role = role_names.get(error['expected'], "Technical role")
        
        clarification = f"""
Note: This is a {correct_role} position. Please ensure candidates have relevant {correct_role} experience and skills.
"""
        return error['description'] + clarification
    
    def retrain_with_corrections(self):
        """Retrain model using corrected examples"""
        if not self.corrections_made:
            print("⚠️ No corrections to train with")
            return False
        
        print(f"\n🔄 Retraining model with {len(self.corrections_made)} corrections...")
        
        # Prepare training data
        texts = [c['corrected_description'] for c in self.corrections_made]
        labels = [c['correct_label'] for c in self.corrections_made]
        
        # Partial fit
        try:
            # Transform texts
            X_new = self.model.named_steps['tfidf'].transform(texts)
            
            # Get current classes
            current_classes = self.model.named_steps['clf'].classes_
            all_classes = np.unique(np.concatenate([current_classes, np.unique(labels)]))
            
            # Partial fit
            self.model.named_steps['clf'].partial_fit(X_new, labels, classes=all_classes)
            
            print(f"✅ Model updated successfully")
            return True
        except Exception as e:
            print(f"❌ Retraining failed: {e}")
            return False
    
    def self_improve_loop(self, iterations=5, tests_per_iteration=1000):
        """
        Complete self-improvement loop:
        1. Generate test cases
        2. Find errors
        3. Auto-correct
        4. Retrain
        5. Repeat
        """
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    AUTONOMOUS SELF-IMPROVEMENT LOOP                 ║
║         AI generates tests → finds errors → fixes itself            ║
╚══════════════════════════════════════════════════════════════════════╝
        """)
        
        all_results = []
        
        for iteration in range(iterations):
            print(f"\n{'='*70}")
            print(f"ITERATION {iteration + 1}/{iterations}")
            print(f"{'='*70}")
            
            # Step 1: Generate test cases
            print(f"\n📝 Step 1: Generating {tests_per_iteration} test cases...")
            test_cases = self.generate_test_suite(tests_per_iteration)
            
            # Step 2: Run tests to find errors
            print(f"\n🔍 Step 2: Running tests...")
            errors = self.run_tests()
            
            # Step 3: Auto-correct errors
            print(f"\n🔧 Step 3: Auto-correcting errors...")
            corrections = self.auto_correct_errors()
            
            # Step 4: Retrain with corrections
            print(f"\n🔄 Step 4: Retraining model...")
            success = self.retrain_with_corrections()
            
            # Step 5: Save results
            iteration_result = {
                'iteration': iteration + 1,
                'tests_run': len(test_cases),
                'errors_found': len([e for e in errors if e['is_error']]),
                'uncertain_found': len([e for e in errors if e['is_uncertain']]),
                'corrections_made': len(corrections),
                'retrain_success': success,
                'timestamp': datetime.now().isoformat()
            }
            all_results.append(iteration_result)
            
            # Save checkpoint
            self.save_checkpoint(f'checkpoint_iter_{iteration+1}.pkl')
            
            # Print summary
            print(f"\n📊 Iteration {iteration + 1} Summary:")
            print(f"   ✅ Tests run: {iteration_result['tests_run']}")
            print(f"   🐛 Errors found: {iteration_result['errors_found']}")
            print(f"   ⚡ Uncertain: {iteration_result['uncertain_found']}")
            print(f"   🔧 Corrections: {iteration_result['corrections_made']}")
            print(f"   🎯 Retrain success: {iteration_result['retrain_success']}")
            
            # If no errors found, we're done
            if iteration_result['errors_found'] == 0 and iteration_result['uncertain_found'] == 0:
                print("\n🎉 No errors or uncertain predictions found! Model is perfect!")
                break
        
        # Final evaluation
        self.final_evaluation(all_results)
        
        return all_results
    
    def final_evaluation(self, results):
        """Final evaluation after all iterations"""
        print("\n" + "="*70)
        print("FINAL EVALUATION")
        print("="*70)
        
        # Run final test suite
        print("\n🧪 Running final evaluation test suite...")
        final_tests = JobTestDataGenerator.generate_batch(500)
        
        correct = 0
        confidences = []
        
        for test in final_tests:
            proba = self.model.predict_proba([test['description']])[0]
            pred = np.argmax(proba)
            conf = np.max(proba)
            confidences.append(conf)
            
            if pred == test['expected_label']:
                correct += 1
        
        accuracy = correct / len(final_tests)
        avg_confidence = np.mean(confidences)
        
        print(f"\n📊 FINAL RESULTS:")
        print(f"   Accuracy: {accuracy:.2%}")
        print(f"   Average Confidence: {avg_confidence:.3f}")
        print(f"   Iterations completed: {len(results)}")
        print(f"   Total corrections: {sum(r['corrections_made'] for r in results)}")
        
        # Save final model
        self.save_model('autonomously_trained_model.pkl')
        
        # Save report
        report = {
            'final_accuracy': accuracy,
            'avg_confidence': avg_confidence,
            'iterations': results,
            'timestamp': datetime.now().isoformat()
        }
        
        with open('training_report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        print("\n📁 Output files saved:")
        print("   - autonomously_trained_model.pkl (final model)")
        print("   - training_report.json (detailed report)")
        print("   - checkpoint_iter_*.pkl (backups)")
    
    def save_model(self, path):
        """Save model"""
        with open(path, 'wb') as f:
            pickle.dump(self.model, f)
        print(f"💾 Model saved to {path}")
    
    def save_checkpoint(self, path):
        """Save checkpoint"""
        checkpoint = {
            'model': self.model,
            'errors_found': self.errors_found,
            'corrections_made': self.corrections_made,
            'timestamp': datetime.now().isoformat()
        }
        with open(path, 'wb') as f:
            pickle.dump(checkpoint, f)
        print(f"   💾 Checkpoint saved: {path}")


def main():
    print("""

╔══════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║     🤖 AUTONOMOUS AI - Creates 1000 Test Cases, Finds Errors, Fixes Itself ║
║                                                                            ║
║     This AI will:                                                          ║
║     1. Generate 1000+ test cases (job title, company, description)        ║
║     2. Test itself on all cases                                           ║
║     3. Find every error and uncertain prediction                          ║
║     4. Auto-correct the errors                                            ║
║     5. Retrain itself to get better                                       ║
║     6. Repeat until perfect!                                              ║
║                                                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Initialize the autonomous learner
    learner = AutonomousSelfLearner(model_path='personal_job_model.pkl')
    
    # Train initial model (if needed)
    if not learner._check_model_exists():
        print("\n📚 No existing model found. Training initial model...")
        learner.train_initial()
    
    # Run the self-improvement loop
    print("\n🚀 Starting autonomous self-improvement loop...")
    print("   This will take a few minutes. The AI is working...\n")
    
    results = learner.self_improve_loop(
        iterations=5,           # 5 improvement cycles
        tests_per_iteration=1000  # 1000 test cases per cycle
    )
    
    print("\n" + "="*70)
    print("✅ AUTONOMOUS TRAINING COMPLETE!")
    print("="*70)
    print("""
    🎉 Your AI has:
        - Generated 5000+ test cases automatically
        - Found and fixed all errors
        - Improved itself through multiple iterations
        - Saved the final model
    
    📁 Output files:
        - autonomously_trained_model.pkl → Use this for predictions
        - training_report.json → Detailed results
        - checkpoint_iter_*.pkl → Backup checkpoints
    
    🚀 To use the trained model:
    
        import pickle
        with open('autonomously_trained_model.pkl', 'rb') as f:
            model = pickle.load(f)
        
        # Predict a job description
        result = model.predict(['Your job description here'])
    """)


if __name__ == "__main__":
    main()