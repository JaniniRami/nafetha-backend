from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, cast
from uuid import UUID

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import PROFILE_MATCH_CACHE_PATH
from app.models import ProfileInterest, User, UserCatalogMatchScore, UserProfile


MAJOR_SKILLS_2026 = {
  "Medicine": [
    "Clinical Diagnosis", "Telemedicine Proficiency", "Electronic Health Records (EHR)", "Patient Triage", "Emergency Medicine", 
    "Surgical Foundations", "Pharmacology", "Bioethics", "Public Health Policy", "Medical Imaging Analysis", 
    "Infection Control", "Case Management", "Preventive Care", "Patient Counseling", "Medical Research", 
    "Healthcare Quality Standards", "Mental Health Screening", "Geriatric Care", "Basic Life Support (BLS)", "Arabic/English Medical Terminology"
  ],
  "Dentistry": [
    "Oral Surgery", "Restorative Dentistry", "Orthodontic Planning", "Periodontal Care", "Digital Radiography", 
    "3D Intraoral Scanning", "Patient Management", "Dental Material Science", "Sterilization Protocols", "Endodontics", 
    "Pedodontics", "Local Anesthesia", "Prosthodontics", "Oral Pathology", "Dental Practice Software", 
    "Aesthetic Dentistry", "Teeth Whitening", "Oral Health Education", "Manual Dexterity", "Maxillofacial Trauma Basics"
  ],
  "Pharmacy": [
    "Medication Counseling", "Drug Interaction Analysis", "Compounding", "Pharmacotherapy", "Inventory Management", 
    "Regulatory Compliance (JFDA)", "Pharmacovigilance", "Retail Pharmacy Operations", "Clinical Pharmacy", "Hospital Pharmacy Systems", 
    "Point-of-Care Testing", "Health Supplement Consulting", "Drug Safety Protocols", "Medical Insurance Billing", "Pharmaceutical Marketing", 
    "Cold Chain Management", "Prescription Processing", "Dosage Calculations", "Quality Assurance", "Healthcare Sales"
  ],
  "Doctor of Pharmacy (PharmD)": [
    "Medication Therapy Management (MTM)", "Critical Care Pharmacy", "Infectious Disease Management", "Pharmacokinetics", "Therapeutic Drug Monitoring", 
    "Clinical Rounding", "Evidence-Based Medicine", "Patient Education", "Hospital Policy Development", "Antimicrobial Stewardship", 
    "Chronic Disease Management", "Toxicology", "Health Economics", "Clinical Trial Support", "Advanced Patient Assessment", 
    "Interprofessional Collaboration", "Palliative Care Pharmacy", "Oncology Pharmacy Basics", "Health Outcomes Research", "Medical Writing"
  ],
  "Nursing": [
    "Acute Care Management", "Wound Care", "IV Administration", "Patient Monitoring", "ICU Support", 
    "Pediatric Nursing", "Maternity Care", "Community Health", "ER Triage", "Surgical Assistance", 
    "Palliative Care", "Health Documentation", "Life Support (ACLS/PALS)", "Nutrition Support", "Patient Advocacy", 
    "Infection Prevention", "Mental Health Nursing", "Home Care Services", "Clinical Communication", "Ethics in Nursing"
  ],
  "Medical Laboratory Sciences": [
    "Hematology Analysis", "Clinical Microbiology", "Biochemical Testing", "Immunology", "Blood Banking", 
    "Molecular Diagnostics (PCR)", "Histopathology", "Quality Control Implementation", "Lab Safety & OSHA", "Specimen Collection", 
    "Lab Equipment Calibration", "Data Interpretation", "Toxicology Testing", "Pathology Reporting", "Phlebotomy", 
    "LIS (Lab Information Systems)", "Microscopy", "Endocrinology Testing", "Serology", "Urinalysis"
  ],
  "Physiotherapy": [
    "Manual Therapy", "Orthopedic Rehab", "Neurological Rehabilitation", "Sports Injury Treatment", "Kinesiology", 
    "Pediatric Physiotherapy", "Geriatric Rehab", "Electrotherapy", "Exercise Prescription", "Posture Correction", 
    "Pain Management", "Biomechanical Analysis", "Dry Needling", "Hydrotherapy", "Ergonomic Assessment", 
    "Cardiac Rehab", "Respiratory Therapy", "Patient Education", "Documentation", "Gait Training"
  ],
  "Occupational Therapy": [
    "Functional Living Skills (ADLs)", "Sensory Integration", "Hand Therapy", "Cognitive Rehab", "Pediatric OT", 
    "Mental Health Rehab", "Assistive Technology", "Ergonomics", "Splinting", "Workplace Adaptations", 
    "Developmental Milestones", "Adaptive Equipment Design", "Geriatric Support", "Group Therapy", "Client-Centered Planning", 
    "Caregiver Training", "Home Safety Assessment", "Psychosocial Intervention", "Fine Motor Development", "Behavioral Management"
  ],
  "Civil Engineering": [
    "Structural Design (ETABS/SAFE)", "AutoCAD/Revit (BIM)", "Project Management (Primavera)", "Quantity Surveying", "Site Supervision", 
    "Geotechnical Analysis", "Hydraulic Modeling", "Contract Management (FIDIC)", "Transportation Engineering", "Environmental Impact", 
    "Concrete Technology", "Steel Design", "Topographic Surveying", "Cost Estimation", "Construction Materials Testing", 
    "Building Codes (Jordanian)", "Infrastructure Planning", "Waste Water Management", "GIS Mapping", "Site Safety Management"
  ],
  "Mechanical Engineering": [
    "CAD/CAM Design (SolidWorks)", "HVAC System Design", "Thermodynamics", "Maintenance Management", "Fluid Mechanics", 
    "Manufacturing Processes", "Solid Mechanics", "Heat Transfer", "Internal Combustion Engines", "Plumbing & Firefighting Design", 
    "Materials Science", "Energy Auditing", "Hydraulic & Pneumatic Systems", "Vibration Analysis", "Quality Control", 
    "Project Engineering", "Machine Design", "Refrigeration Systems", "Robotics Basics", "Technical Reporting"
  ],
  "Electrical Engineering": [
    "Power System Analysis", "FPGA", "SemiConductors", "Circuit Design", "PLC Programming", "Control Systems", "Electrical Installation", 
    "Renewable Energy Systems", "Lighting Design", "Transmission & Distribution", "Microcontrollers", "Protection Systems", 
    "Electrical Troubleshooting", "MATLAB Simulation", "Smart Grid Technology", "Instrumentation", "EMC/EMI Knowledge", 
    "Project Estimation", "Site Commissioning", "Telecommunication Systems", "PCB Design", "Industrial Automation"
  ],
  "Chemical Engineering": [
    "Process Design & Simulation", "Mass & Energy Balances", "Chemical Reaction Engineering", "Separation Processes", "Industrial Chemistry", 
    "Process Control", "Safety Management (HAZOP)", "Petrochemical Analysis", "Water Treatment", "Materials Engineering", 
    "Plant Operations", "Thermodynamics", "Catalysis", "Environmental Compliance", "Food Processing Tech", 
    "Polymer Science", "Heat Exchanger Design", "Quality Assurance", "Project Management", "Waste Management"
  ],
  "Industrial Engineering": [
    "Process Optimization (Lean/Six Sigma)", "Operations Research", "Supply Chain Management", "Facilities Planning", "Quality Management Systems", 
    "Production Planning", "Ergonomics", "Work Study & Measurement", "ERP Systems (SAP)", "Statistical Quality Control", 
    "Project Management", "Financial Engineering", "Simulation (Arena/Simio)", "Inventory Control", "Strategic Planning", 
    "Cost Analysis", "Organizational Behavior", "Systems Engineering", "Risk Analysis", "Data Analytics"
  ],
  "Mechatronics Engineering": [
    "Robotics", "Automation", "PLC & SCADA", "Embedded Systems", "Sensor Fusion", 
    "Machine Vision", "Microcontroller Programming", "Digital Logic", "Control Theory", "Mechanical CAD", 
    "Actuators & Motors", "Analog & Digital Electronics", "System Integration", "IoT in Manufacturing", "Hydraulics/Pneumatics", 
    "Python/C++ for HW", "PCB Layout", "Real-time Systems", "Circuit Troubleshooting", "Artificial Intelligence Basics"
  ],
  "Renewable Energy Engineering": [
    "Solar PV Design (PVsyst)", "Wind Energy Analysis", "Energy Auditing", "Energy Storage Systems", "Sustainability Strategy", 
    "Grid Connection", "Hybrid Power Systems", "Energy Economics", "Solar Thermal Design", "Bioenergy", 
    "Environmental Policy", "LEED/Green Building", "Power Electronics", "Hydrothermal Energy", "Smart Grids", 
    "Energy Simulation", "Carbon Management", "Project Management", "Technical Feasibility", "Resource Assessment"
  ],
  "Computer Engineering": [
    "VHDL/Verilog", "Embedded Software", "Computer Architecture", "Microprocessor Interfacing", "Networking Protocols", 
    "OS Kernel Basics", "FPGA Design", "Digital Signal Processing", "C/C++ for Hardware", "Circuit Analysis", 
    "Logic Design", "System-on-Chip (SoC)", "Robotics Control", "IoT Architecture", "Cybersecurity Hardware", 
    "Assembly Language", "Hardware Debugging", "Compiler Design", "Parallel Computing", "Drivers Development"
  ],
  "Network Engineering": [
    "Routing & Switching (Cisco)", "Cloud Infrastructure (Azure/AWS)", "Network Security", "Virtualization (VMware)", "VoIP Systems", 
    "TCP/IP Protocols", "Firewall Configuration", "SD-WAN", "Network Monitoring", "Data Center Management", 
    "VPN Setup", "Troubleshooting", "Wireless Networking", "Server Administration", "DNS/DHCP Management", 
    "Network Automation (Python)", "Load Balancing", "Network Auditing", "Disaster Recovery", "Linux Administration"
  ],
  "Architecture": [
    "Architectural Design", "BIM (Revit)", "3D Visualization (3ds Max/V-Ray)", "Sustainable Design", "Urban Planning", 
    "Building Codes", "Construction Documents", "Landscape Design", "Conceptual Sketching", "Historical Preservation", 
    "Interior Architecture", "Materials Knowledge", "Structural Systems Basics", "Physical Modeling", "Project Coordination", 
    "Site Analysis", "Zoning Regulation", "Graphic Representation", "Building Services Integration", "Client Presentation"
  ],
  "Interior Design": [
    "Space Planning", "3D Rendering (SketchUp/Lumion)", "Color Theory", "Lighting Design", "Furniture Design", 
    "Material & Finish Selection", "Textiles Knowledge", "AutoCAD for Interiors", "Construction Details", "Kitchen & Bath Design", 
    "Commercial Interiors", "Residential Interiors", "Acoustics", "Project Management", "Cost Estimation", 
    "Sustainable Materials", "Manual Drafting", "Branding for Spaces", "Client Relationship Management", "Visual Merchandising"
  ],
  "Graphic Design": [
    "Adobe Creative Cloud", "Branding & Identity", "Typography", "UI/UX Design Basics", "Layout Design (InDesign)", 
    "Digital Illustration", "Logo Design", "Print Production", "Color Psychology", "Photo Editing", 
    "Motion Graphics", "Social Media Content", "Visual Storytelling", "Packaging Design", "Advertising Design", 
    "Creative Direction", "Infographic Design", "Portfolio Development", "Client Brief Analysis", "Generative AI Design Tools"
  ],
  "Computer Science": [
    "Algorithm Analysis", "Data Structures", "Java/C++/Python", "Web Development (Full-Stack)", "Database Management (SQL/NoSQL)", 
    "Artificial Intelligence", "Operating Systems", "Discrete Mathematics", "Software Architecture", "Distributed Systems", 
    "Compiler Construction", "Cloud Computing Basics", "Mobile App Development", "Functional Programming", "Problem Solving", 
    "API Design", "Object Oriented Analysis", "Git Version Control", "Testing & QA", "Technical Documentation"
  ],
  "Software Engineering": [
    "Agile/Scrum", "Software Design Patterns", "DevOps & CI/CD", "Quality Assurance & Testing", "System Integration", 
    "Project Management", "Clean Code Principles", "Refactoring", "Microservices", "UI/UX Integration", 
    "Mobile Development (Flutter/React Native)", "API Development", "Unit & Integration Testing", "Version Control (Git)", "Requirements Engineering", 
    "Cloud Native Development", "Debugging", "Security-by-Design", "Technical Leadership", "Documentation"
  ],
  "Information Technology": [
    "Systems Administration", "IT Support (Service Desk)", "Cloud Management", "Network Support", "Cybersecurity Basics", 
    "IT Governance (ITIL)", "Database Administration", "Virtualization", "IT Project Management", "Hardware Maintenance", 
    "Scripting (PowerShell/Bash)", "SaaS Management", "Data Backup & Recovery", "IT Policy Drafting", "SLA Management", 
    "User Training", "Inventory Tracking", "Technical Troubleshooting", "Digital Transformation", "Security Auditing"
  ],
  "Data Science and Artificial Intelligence": [
    "Machine Learning (Scikit-learn)", "Deep Learning (TensorFlow/PyTorch)", "Statistical Modeling", "Python/R Programming", "Data Visualization (Power BI/Tableau)", 
    "NLP (Natural Language Processing)", "Computer Vision", "Big Data (Spark/Hadoop)", "SQL & Data Warehousing", "Data Cleaning/ETL", 
    "Predictive Analytics", "A/B Testing", "Time Series Analysis", "Data Mining", "Feature Engineering", 
    "AI Ethics", "Mathematical Optimization", "Cloud AI (AWS SageMaker)", "Model Deployment", "Generative AI Engineering"
  ],
  "Cybersecurity": [
    "Penetration Testing", "Ethical Hacking", "Network Security", "Cryptography", "Incident Response", 
    "Digital Forensics", "Risk Assessment", "SIEM (Security Monitoring)", "Cloud Security", "Identity & Access Management (IAM)", 
    "Vulnerability Management", "Compliance (ISO 27001)", "Malware Analysis", "Security Auditing", "Endpoint Protection", 
    "Scripting for Security", "Firewall & VPN", "Web Application Security", "Social Engineering Awareness", "Governance & Policy"
  ],
  "Business Information Systems": [
    "ERP Management (SAP/Oracle)", "Business Analytics", "Systems Analysis & Design", "Database Management", "E-commerce Strategy", 
    "Business Process Modeling", "Project Management", "Digital Marketing Analytics", "IT Strategy", "Financial Information Systems", 
    "Supply Chain Management IT", "Decision Support Systems", "Data Privacy & Ethics", "CRM Implementation", "BI Reporting", 
    "Web Analytics", "Requirements Gathering", "Corporate Governance", "Audit of IT Systems", "Change Management"
  ],
  "Business Administration": [
    "Strategic Planning", "Organizational Behavior", "Leadership", "HR Management", "Operations Management", 
    "Business Ethics", "Financial Management Basics", "Marketing Management", "Change Management", "Negotiation", 
    "Business Communication", "Entrepreneurship", "Conflict Resolution", "Project Management", "International Business", 
    "Public Relations", "Sales Strategy", "Administrative Management", "Market Analysis", "Team Building"
  ],
  "Accounting": [
    "Financial Reporting", "Auditing", "Cost Accounting", "Taxation", "IFRS Standards", 
    "Accounting Software (QuickBooks/Sage)", "Budgeting", "Forensic Accounting", "Payroll Management", "Internal Controls", 
    "Financial Analysis", "Inventory Accounting", "Accounts Payable/Receivable", "Corporate Governance", "Equity Accounting", 
    "Fixed Asset Management", "Cash Flow Analysis", "Consolidation", "Regulatory Compliance", "Microsoft Excel (Advanced)"
  ],
  "Finance and Banking": [
    "Investment Analysis", "Portfolio Management", "Corporate Finance", "Financial Modeling", "Equity & Debt Markets", 
    "Commercial Banking", "Risk Management", "Credit Analysis", "Derivatives", "International Finance", 
    "Banking Regulations (Central Bank of Jordan)", "Islamic Finance", "Wealth Management", "Asset Valuation", "Fintech Basics", 
    "Market Research", "Capital Budgeting", "Treasury Management", "Financial Statement Analysis", "Economic Forecasting"
  ],
  "Marketing": [
    "Market Research", "Consumer Behavior", "Brand Management", "Marketing Strategy", "Public Relations", 
    "Advertising Planning", "Sales Management", "Product Development", "Media Planning", "B2B Marketing", 
    "Integrated Marketing Communication", "Event Marketing", "Market Segmentation", "Competitive Analysis", "Distribution Strategy", 
    "Pricing Strategies", "Retail Marketing", "Customer Relationship Management (CRM)", "Creative Briefing", "Marketing Ethics"
  ],
  "Digital Marketing": [
    "SEO (Search Engine Optimization)", "SEM (Google Ads)", "Social Media Strategy", "Content Marketing", "Email Automation", 
    "Social Media Analytics", "Copywriting", "PPC Advertising", "Affiliate Marketing", "Influencer Marketing", 
    "Web Analytics (GA4)", "Video Marketing", "Lead Generation", "E-commerce Marketing", "Conversion Rate Optimization (CRO)", 
    "Mobile Marketing", "Digital Branding", "Online Reputation Management", "Paid Social Ads", "Data-Driven Marketing"
  ],
  "Risk Management": [
    "Risk Identification", "Quantitative Risk Analysis", "Enterprise Risk Management (ERM)", "Insurance Principles", "Crisis Management", 
    "Business Continuity Planning", "Credit Risk Management", "Operational Risk", "Market Risk", "Compliance Auditing", 
    "Financial Risk Modeling", "Strategic Risk Analysis", "Legal Risk Management", "Health & Safety Risk", "Internal Audit Support", 
    "Regulatory Reporting", "Disaster Recovery Strategy", "Fraud Detection", "Risk Ethics", "Decision Theory"
  ],
  "Hospitality and Tourism Management": [
    "Hotel Operations", "F&B Management", "Front Office Operations", "Housekeeping Management", "Event & Meeting Planning", 
    "Tourism Marketing", "Customer Service Excellence", "Revenue Management", "Travel Agency Operations", "Sustainable Tourism", 
    "Global Tourism Trends", "Cultural Sensitivity", "Hospitality Law", "E-tourism & Distribution", "Hospitality Accounting", 
    "Human Resources in Hospitality", "Public Relations", "Facility Management", "Catering Management", "Crisis Management in Tourism"
  ],
  "Law": [
    "Legal Research", "Contract Drafting", "Litigation", "Constitutional Law", "Corporate Law", 
    "Criminal Law", "Administrative Law", "Legal Ethics", "Mediation & Arbitration", "Intellectual Property", 
    "Labor Law", "International Law", "Legal Writing", "Case Analysis", "Tort Law", 
    "Human Rights Law", "Family Law", "Court Procedures", "Advocacy", "Commercial Law"
  ],
  "Political Science": [
    "Policy Analysis", "Political Theory", "Comparative Politics", "Public Administration", "International Relations Basics", 
    "Diplomacy", "Electoral Systems", "Political Campaigning", "Legislative Research", "Government Relations", 
    "Public Policy Development", "Political Sociology", "Conflict Resolution", "Middle Eastern Politics", "Political Economy", 
    "Human Rights Studies", "Public Speaking", "Strategic Communication", "Regional Security", "Globalization Studies"
  ],
  "International Relations": [
    "Global Diplomacy", "International Conflict Resolution", "Foreign Policy Analysis", "International Law", "Intercultural Communication", 
    "NGO Management", "Global Governance", "Peace & Security Studies", "International Trade Policy", "Humanitarian Affairs", 
    "Diplomatic Protocol", "Human Rights Advocacy", "Regional Studies", "International Development", "Strategic Planning", 
    "Grant Writing", "Geopolitics", "Intelligence Analysis", "Global Economic Trends", "Lobbying & Advocacy"
  ],
  "English Language and Literature": [
    "Literary Criticism", "Academic Writing", "Linguistics", "Creative Writing", "Cultural Analysis", 
    "Advanced Grammar", "Public Speaking", "Historical Contextualization", "Textual Analysis", "Comparative Literature", 
    "Poetry Analysis", "Drama & Theater Studies", "British & American Literature", "Post-Colonial Studies", "Philology", 
    "Research Methodology", "Content Creation", "Teaching Skills (TEFL Basics)", "Editing & Proofreading", "Rhetoric"
  ],
  "Applied English": [
    "Technical Writing", "Business English", "ESP (English for Specific Purposes)", "Interpretation", "Public Speaking", 
    "Cross-Cultural Communication", "Corporate Training", "Copywriting", "Professional Correspondence", "Linguistic Analysis", 
    "Translation Basics", "Language Teaching", "Office Management (English Environment)", "Meeting Facilitation", "Editing", 
    "Customer Support in English", "Public Relations", "Language Assessment", "Proposal Writing", "Journalistic English"
  ],
  "Translation": [
    "Simultaneous Interpretation", "Consecutive Interpretation", "Legal Translation", "Medical Translation", "Technical Translation", 
    "Localization", "CAT Tools (Trados/MemoQ)", "Subtitling & Dubbing", "Literary Translation", "Terminology Management", 
    "Proofreading & Editing", "Bilingual Proficiency", "Cultural Mediation", "Linguistic Quality Assurance", "Consecutive Note-taking", 
    "Machine Translation Post-editing", "Freelance Business Management", "Media Translation", "Corporate Translation", "Sight Translation"
  ],
  "Arabic Language and Literature": [
    "Arabic Linguistics", "Classical Poetry", "Modern Literature", "Grammar (Nahw/Sarf)", "Prosody (Arud)", 
    "Arabic Calligraphy", "Rhetoric (Balagha)", "Literary Criticism", "Creative Writing", "Editing & Proofreading", 
    "Content Strategy (Arabic)", "Teaching Arabic to Non-Speakers", "Islamic Literature", "Arabic Philology", "Comparative Literature", 
    "Journalistic Arabic", "Public Speaking", "Dialectology", "Manuscript Research", "Script Writing"
  ],
  "French Language": [
    "French Literature", "Grammar & Syntax", "Oral Fluency", "French Translation", "Francophone Culture", 
    "Business French", "Interpretation", "Phonetics", "Linguistics", "Academic Writing", 
    "French History", "Corporate Communication in French", "Tourism French", "Diplomatic French", "Proofreading", 
    "Cross-Cultural Relations", "Teaching French", "French for Specific Purposes", "Literary Analysis", "Language Assessment"
  ],
  "Psychology": [
    "Counseling Techniques", "Psychological Assessment", "Developmental Psychology", "Clinical Psychology", "Research Methods", 
    "Cognitive Behavioral Therapy (CBT) Basics", "Behavioral Modification", "Statistical Analysis (SPSS)", "Social Psychology", "Abnormal Psychology", 
    "Group Therapy Facilitation", "Mental Health Awareness", "Crisis Intervention", "Educational Psychology", "Industrial-Organizational Psychology", 
    "Neuropsychology Basics", "Ethics in Psychology", "Case Reporting", "Patient Interviewing", "Stress Management"
  ],
  "Sociology": [
    "Social Research Methods", "Social Theory", "Demography", "Criminology", "Community Organization", 
    "Qualitative & Quantitative Analysis", "Urban Sociology", "Sociology of Family", "Data Analysis", "Ethnography", 
    "Social Justice Advocacy", "Public Policy Analysis", "Social Stratification", "Gender Studies", "Cultural Anthropology", 
    "Social Change Management", "Human Rights Research", "Public Opinion Polling", "NGO Coordination", "Industrial Sociology"
  ],
  "Social Work": [
    "Case Management", "Counseling", "Child Welfare", "Crisis Intervention", "Community Outreach", 
    "Policy Analysis", "Medical Social Work", "Group Therapy", "Conflict Resolution", "Disability Support", 
    "Humanitarian Aid", "Geriatric Social Work", "Advocacy", "Resource Mobilization", "Mental Health Support", 
    "Addiction Counseling Basics", "Field Research", "Legal Rights Advocacy", "Documentation & Reporting", "Family Therapy"
  ],
  "Journalism and Media": [
    "News Writing", "Investigative Reporting", "Digital Media Production", "Video Editing (Premiere/Final Cut)", "Photojournalism", 
    "Media Law & Ethics", "Broadcast Journalism", "Public Relations", "Social Media Reporting", "Interviewing", 
    "Copywriting", "Podcasting", "Data Journalism", "Mobile Journalism (MoJo)", "Script Writing", 
    "Media Planning", "Web Content Management", "Live Streaming", "Public Speaking", "Audience Analytics"
  ],
  "Mathematics": [
    "Calculus (Advanced)", "Linear Algebra", "Statistical Analysis", "Mathematical Modeling", "Discrete Mathematics", 
    "Topology", "Number Theory", "Numerical Analysis", "Probability Theory", "Actuarial Science Basics", 
    "Differential Equations", "Quantitative Research", "Logical Reasoning", "LaTeX for Scientific Writing", "Mathematical Software (MATLAB/Maple)", 
    "Data Mining Basics", "Operations Research", "Abstract Algebra", "Complex Analysis", "Cryptography Basics"
  ],
  "Physics": [
    "Quantum Mechanics", "Thermodynamics", "Electromagnetism", "Astrophysics", "Laboratory Techniques", 
    "Mathematical Physics", "Optics", "Solid State Physics", "Nuclear Physics", "Computational Physics", 
    "Material Science", "Scientific Research", "Electronics", "Fluid Dynamics", "Particle Physics", 
    "Data Analysis", "Renewable Energy Physics", "Mechanics", "Instrumentation", "Geophysics Basics"
  ],
  "Chemistry": [
    "Organic Chemistry", "Analytical Chemistry", "Inorganic Chemistry", "Physical Chemistry", "Biochemistry", 
    "Laboratory Safety & Protocols", "Instrumental Analysis (HPLC/GC)", "Polymer Chemistry", "Medicinal Chemistry", "Spectroscopy", 
    "Quality Control", "Chemical Synthesis", "Toxicology Basics", "Environmental Chemistry", "Chemical Research", 
    "Industrial Chemistry", "Chromatography", "Molecular Modeling", "Forensic Chemistry", "Documentation"
  ],
  "Biological Sciences": [
    "Genetics", "Microbiology", "Cell Biology", "Molecular Biology", "Ecology", 
    "Physiology", "Botanical Sciences", "Zoology", "Biotechnology", "Bioinformatics", 
    "Lab Research Techniques", "Evolutionary Biology", "Environmental Biology", "Immunology", "Biological Conservation", 
    "Microscopy", "Anatomy", "Histology", "Quality Assurance in Biotech", "Biostatistics"
  ],
  "Geology": [
    "Mineralogy", "Structural Geology", "Petrology", "Seismology", "Hydrogeology", 
    "Environmental Geology", "Mapping & GIS", "Field Exploration", "Paleontology", "Sedimentology", 
    "Mining Geology", "Petroleum Geology", "Earthquake Engineering Basics", "Geochemistry", "Geophysics", 
    "Resource Management", "Drilling Engineering Basics", "Soil Mechanics", "Stratigraphy", "Remote Sensing"
  ],
  "Agriculture": [
    "Crop Management", "Soil Science", "Plant Protection", "Agricultural Economics", "Animal Husbandry", 
    "Irrigation Systems", "Food Safety", "Sustainable Farming", "Greenhouse Management", "Horticulture", 
    "Landscaping", "Plant Breeding", "Agricultural Machinery", "Pest Control", "Agri-Business", 
    "Organic Farming", "Post-Harvest Technology", "Rural Development", "Forestry", "Water Management"
  ],
  "Nutrition and Dietetics": [
    "Clinical Nutrition", "Dietary Planning", "Food Science", "Nutrition Counseling", "Metabolism", 
    "Public Health Nutrition", "Food Safety & Hygiene", "Medical Nutrition Therapy (MNT)", "Sports Nutrition", "Pediatric Nutrition", 
    "Weight Management", "Nutritional Biochemistry", "Community Nutrition", "Menu Planning", "Food Microbiology", 
    "Human Anatomy & Physiology", "Enteral/Parenteral Nutrition", "Diabetes Management", "Eating Disorders Awareness", "Food Industry Regulations"
  ],
  "Special Education": [
    "Individualized Education Programs (IEP)", "Behavioral Modification", "Learning Disabilities Assessment", "Assistive Technology", "Inclusive Education", 
    "Autism Spectrum Support", "Gifted & Talented Education", "Hearing/Visual Impairment Support", "Differentiated Instruction", "Early Intervention", 
    "Sign Language Basics", "Classroom Management", "Speech & Language Basics", "Psychological Testing", "Parental Counseling", 
    "Social Skills Training", "Transition Planning", "Collaboration with Specialists", "Activity Adaptation", "Emotional & Behavioral Disorders Support"
  ],
  "Physical Education": [
    "Sports Coaching", "Exercise Physiology", "Kinesiology", "First Aid & CPR", "Sports Management", 
    "Fitness Training", "Motor Learning", "Anatomy & Biomechanics", "Health Promotion", "Outdoor Education", 
    "Sports Psychology", "Team Sports (Football/Basketball)", "Individual Sports (Swimming/Tennis)", "Gymnastics Instruction", "Athletic Training", 
    "Physical Therapy Basics", "Sports Nutrition", "Recreational Leadership", "Exercise Testing", "Curriculum Design in PE"
  ],
  "Other": [
    "Critical Thinking", "Problem Solving", "Time Management", "Effective Communication", "Adaptability", 
    "Leadership", "Teamwork", "Digital Literacy", "Emotional Intelligence", "Conflict Resolution", 
    "Public Speaking", "Creativity", "Attention to Detail", "Ethics", "Networking", 
    "Project Management", "Decision Making", "Self-Motivation", "Intercultural Competence", "Customer Service"
  ]
};

_MAJOR_SKILLS_LOOKUP: dict[str, list[str]] = {
    str(major).strip().lower(): list(skills)
    for major, skills in MAJOR_SKILLS_2026.items()
}


CACHE_VERSION: Final[int] = 1
DATASET_NAMES: Final[tuple[str, ...]] = (
    "jobs",
    "companies",
    "communities",
    "community_events",
    "volunteering_events",
)
CATALOG_TYPES: Final[set[str]] = set(DATASET_NAMES)
_COSINE_MIN: Final[float] = 0.20
_COSINE_MAX: Final[float] = 0.55

# Display-score settings — applied once at persist time for jobs & companies only.
# Scores below _DISPLAY_FLOOR are never scaled or smoothed.
# If the top raw score is below _DISPLAY_THRESHOLD, it is lifted to _DISPLAY_TARGET
# and all other eligible scores are smoothed along a power curve.
_DISPLAY_DATASETS: Final[frozenset[str]] = frozenset({"jobs", "companies"})
_DISPLAY_FLOOR: Final[float] = 30.0
_DISPLAY_THRESHOLD: Final[float] = 80.0
_DISPLAY_TARGET: Final[float] = 90.0
_DISPLAY_GAMMA: Final[float] = 0.6


def _compute_display_scores(scores: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    """Apply scaling + power-curve smoothing to a sorted list of score dicts.

    Each dict must have ``score_percent`` (float) and ``id`` (str) keys.
    The list is expected to be sorted descending by score_percent.
    Only mutates ``score_percent``; all other keys are left untouched.
    """
    if not scores:
        return scores

    max_raw = float(scores[0]["score_percent"])
    if max_raw <= 0:
        return scores

    # Decide displayed maximum: bump to _DISPLAY_TARGET if below _DISPLAY_THRESHOLD.
    max_display = _DISPLAY_TARGET if max_raw < _DISPLAY_THRESHOLD else max_raw

    result = []
    for entry in scores:
        raw = float(entry["score_percent"])
        if raw < _DISPLAY_FLOOR:
            displayed = raw
        else:
            ratio = raw / max_raw
            displayed = min(max_display * (ratio ** _DISPLAY_GAMMA), 100.0)
        result.append({**entry, "score_percent": round(displayed, 2)})
    return result


@dataclass(frozen=True)
class EmbeddingDataset:
    ids: list[str]
    vectors: np.ndarray


@dataclass(frozen=True)
class CatalogEmbeddingCache:
    model_name: str
    generated_at: str
    embedding_dim: int
    datasets: dict[str, EmbeddingDataset]


_CACHE_MEMO: dict[str, object] = {
    "path": None,
    "mtime": None,
    "cache": None,
}


def normalize_embedding_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = text.replace(",", " ")
    text = text.replace("-", " ")
    text = text.replace("_", " ")
    return " ".join(text.split())


def profile_text_from_major_and_interests(major: str | None, interests: list[str]) -> str:
    major_clean = " ".join((major or "").split())
    major_key = major_clean.lower()
    mapped_skills = _MAJOR_SKILLS_LOOKUP.get(major_key)
    if mapped_skills is None:
        mapped_skills = _MAJOR_SKILLS_LOOKUP.get("other", [])

    combined = " ".join([major_clean, *interests, *mapped_skills])
    return normalize_embedding_text(combined)


def _build_user_profile_text(db: Session, user: User) -> str:
    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is None:
        raise ValueError("User profile does not exist yet")

    interests = list(
        db.scalars(
            select(ProfileInterest.interest)
            .where(ProfileInterest.user_profile_id == profile.id)
            .order_by(ProfileInterest.interest)
        ).all()
    )
    user_text = profile_text_from_major_and_interests(profile.major, interests)
    if not user_text:
        raise ValueError("User profile text is empty after normalization")
    return user_text


@lru_cache(maxsize=2)
def get_sentence_transformer(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


def encode_texts(texts: list[str], model_name: str) -> np.ndarray:
    model = get_sentence_transformer(model_name)
    get_dim = getattr(model, "get_embedding_dimension", None)
    if callable(get_dim):
        dim = int(get_dim())
    else:
        # Backward compatibility with older sentence-transformers releases.
        dim = int(model.get_sentence_embedding_dimension())
    if not texts:
        return np.zeros((0, dim), dtype=np.float32)
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


def save_catalog_embedding_cache(cache: CatalogEmbeddingCache, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "version": CACHE_VERSION,
        "model_name": cache.model_name,
        "generated_at": cache.generated_at,
        "embedding_dim": cache.embedding_dim,
        "datasets": list(cache.datasets.keys()),
    }

    arrays: dict[str, np.ndarray] = {
        "metadata": np.array(json.dumps(metadata), dtype=object),
    }
    for dataset_name, dataset in cache.datasets.items():
        arrays[f"{dataset_name}__ids"] = np.asarray(dataset.ids, dtype=object)
        arrays[f"{dataset_name}__vectors"] = np.asarray(dataset.vectors, dtype=np.float32)

    np.savez_compressed(output_path, **arrays)


def _load_catalog_embedding_cache_uncached(cache_path: Path) -> CatalogEmbeddingCache:
    if not cache_path.exists():
        msg = f"Embedding cache file not found: {cache_path}"
        raise FileNotFoundError(msg)

    with np.load(cache_path, allow_pickle=True) as data:
        metadata_raw = data["metadata"].item()
        metadata = json.loads(metadata_raw)
        if int(metadata.get("version", 0)) != CACHE_VERSION:
            msg = (
                "Embedding cache version mismatch. "
                f"Expected={CACHE_VERSION}, Found={metadata.get('version')}"
            )
            raise ValueError(msg)

        datasets: dict[str, EmbeddingDataset] = {}
        for dataset_name in metadata.get("datasets", []):
            ids = [str(x) for x in data[f"{dataset_name}__ids"].tolist()]
            vectors = np.asarray(data[f"{dataset_name}__vectors"], dtype=np.float32)
            datasets[dataset_name] = EmbeddingDataset(ids=ids, vectors=vectors)

    return CatalogEmbeddingCache(
        model_name=str(metadata["model_name"]),
        generated_at=str(metadata["generated_at"]),
        embedding_dim=int(metadata["embedding_dim"]),
        datasets=datasets,
    )


def load_catalog_embedding_cache(cache_path: str | Path | None = None) -> CatalogEmbeddingCache:
    resolved = Path(cache_path or PROFILE_MATCH_CACHE_PATH).expanduser().resolve()
    mtime = resolved.stat().st_mtime
    if (
        _CACHE_MEMO["cache"] is not None
        and _CACHE_MEMO["path"] == str(resolved)
        and _CACHE_MEMO["mtime"] == mtime
    ):
        return _CACHE_MEMO["cache"]  # type: ignore[return-value]

    loaded = _load_catalog_embedding_cache_uncached(resolved)
    _CACHE_MEMO["path"] = str(resolved)
    _CACHE_MEMO["mtime"] = mtime
    _CACHE_MEMO["cache"] = loaded
    return loaded


def _dataset_scores(ids: list[str], vectors: np.ndarray, user_vector: np.ndarray) -> list[dict[str, float | str]]:
    if vectors.size == 0 or len(ids) == 0:
        return []
    if vectors.shape[1] != user_vector.shape[0]:
        msg = (
            "Embedding dimension mismatch between cached dataset and user profile vector. "
            f"dataset_dim={vectors.shape[1]} user_dim={user_vector.shape[0]}"
        )
        raise ValueError(msg)
    cosine = cosine_similarity(vectors, user_vector.reshape(1, -1)).reshape(-1)
    cosine = np.clip(cosine, 0.0, 1.0)
    # Calibrate MiniLM cosine scores from practical range [0.2, 0.85] into [0, 100].
    calibrated = (cosine - _COSINE_MIN) / (_COSINE_MAX - _COSINE_MIN)
    calibrated = np.clip(calibrated, 0.0, 1.0)
    percentages = calibrated * 100.0
    scores: list[dict[str, float | str]] = [
        {"id": row_id, "score_percent": round(float(score), 2)}
        for row_id, score in zip(ids, percentages, strict=False)
    ]
    scores.sort(key=lambda item: float(item["score_percent"]), reverse=True)
    return scores


def compute_catalog_match_scores_for_user(
    db: Session,
    user: User,
    *,
    cache_path: str | Path | None = None,
) -> dict[str, object]:
    user_text = _build_user_profile_text(db, user)
    cache = load_catalog_embedding_cache(cache_path)
    user_vector = encode_texts([user_text], cache.model_name)[0]

    result: dict[str, object] = {
        "model_name": cache.model_name,
        "profile_text": user_text,
    }
    for dataset_name in DATASET_NAMES:
        dataset = cache.datasets.get(dataset_name)
        if dataset is None:
            result[dataset_name] = []
            continue
        result[dataset_name] = _dataset_scores(dataset.ids, dataset.vectors, user_vector)
    return result


def _empty_scores_payload() -> dict[str, object]:
    payload: dict[str, object] = {"model_name": "", "profile_text": ""}
    for dataset_name in DATASET_NAMES:
        payload[dataset_name] = []
    return payload


def get_persisted_catalog_match_scores_for_user(db: Session, user: User) -> dict[str, object] | None:
    rows = list(
        db.scalars(
            select(UserCatalogMatchScore)
            .where(UserCatalogMatchScore.user_id == user.id)
            .order_by(
                UserCatalogMatchScore.catalog_type.asc(),
                UserCatalogMatchScore.score_percent.desc(),
            )
        ).all()
    )
    if not rows:
        return None

    result = _empty_scores_payload()
    result["model_name"] = rows[0].model_name
    result["profile_text"] = rows[0].profile_text
    for row in rows:
        if row.catalog_type not in CATALOG_TYPES:
            continue
        dataset_scores = cast(list[dict[str, float | str]], result[row.catalog_type])
        dataset_scores.append(
            {
                "id": str(row.item_id),
                "score_percent": round(float(row.score_percent), 2),
            }
        )
    return result


def persist_catalog_match_scores_for_user(
    db: Session,
    user: User,
    *,
    cache_path: str | Path | None = None,
) -> dict[str, object]:
    computed = compute_catalog_match_scores_for_user(db, user, cache_path=cache_path)
    model_name = str(computed["model_name"])
    profile_text = str(computed["profile_text"])

    db.execute(delete(UserCatalogMatchScore).where(UserCatalogMatchScore.user_id == user.id))
    saved_counts: dict[str, int] = {name: 0 for name in DATASET_NAMES}
    for dataset_name in DATASET_NAMES:
        dataset_scores = computed.get(dataset_name, [])
        if not isinstance(dataset_scores, list):
            continue
        if dataset_name in _DISPLAY_DATASETS:
            dataset_scores = _compute_display_scores(dataset_scores)
        for row in dataset_scores:
            item_id_raw = row.get("id")
            if item_id_raw is None:
                continue
            score = float(row.get("score_percent", 0.0))
            db.add(
                UserCatalogMatchScore(
                    user_id=user.id,
                    catalog_type=dataset_name,
                    item_id=UUID(str(item_id_raw)),
                    score_percent=round(score, 2),
                    model_name=model_name,
                    profile_text=profile_text,
                )
            )
            saved_counts[dataset_name] += 1
    db.commit()
    total_saved = sum(saved_counts.values())
    print(
        "[profile-match] persisted "
        f"user_id={user.id} total={total_saved} "
        + " ".join([f"{name}={saved_counts[name]}" for name in DATASET_NAMES]),
        flush=True,
    )
    return computed


def get_or_create_persisted_catalog_match_scores_for_user(
    db: Session,
    user: User,
    *,
    cache_path: str | Path | None = None,
) -> dict[str, object]:
    existing = get_persisted_catalog_match_scores_for_user(db, user)
    if existing is None:
        return persist_catalog_match_scores_for_user(db, user, cache_path=cache_path)

    expected_text = _build_user_profile_text(db, user)
    cache = load_catalog_embedding_cache(cache_path)
    if (
        str(existing.get("profile_text", "")) != expected_text
        or str(existing.get("model_name", "")) != cache.model_name
    ):
        return persist_catalog_match_scores_for_user(db, user, cache_path=cache_path)

    persisted_counts = dict(
        db.execute(
            select(UserCatalogMatchScore.catalog_type, func.count(UserCatalogMatchScore.id))
            .where(UserCatalogMatchScore.user_id == user.id)
            .group_by(UserCatalogMatchScore.catalog_type)
        ).all()
    )
    for dataset_name in DATASET_NAMES:
        persisted_count = int(persisted_counts.get(dataset_name, 0))
        dataset = cache.datasets.get(dataset_name)
        cache_count = len(dataset.ids) if dataset is not None else 0
        if persisted_count != cache_count:
            print(
                "[profile-match] refresh-needed "
                f"user_id={user.id} reason=count_mismatch dataset={dataset_name} "
                f"persisted={persisted_count} cache={cache_count}",
                flush=True,
            )
            return persist_catalog_match_scores_for_user(db, user, cache_path=cache_path)

    print(
        "[profile-match] using-persisted "
        f"user_id={user.id} model={existing.get('model_name', '')}",
        flush=True,
    )
    return existing
