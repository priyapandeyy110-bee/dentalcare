"""Curated dental knowledge used by the offline rule engine and as grounding
context for the Gemini prompts.

Everything here is general patient education -- the kind of information a
clinic would print on a leaflet. It is deliberately conservative: it never
names a diagnosis, and every path ends in "see a dentist".
"""

DISCLAIMER = (
    "This is general information from an automated assistant, not a medical "
    "diagnosis. Only a qualified dentist can diagnose and treat dental problems "
    "after an examination."
)

EMERGENCY_NOTICE = (
    "Some of what you described can worsen quickly. Please contact the clinic "
    "or your nearest emergency dental service now rather than waiting."
)

# --- FAQ -------------------------------------------------------------------
# keyword tuples -> answer. Matched case-insensitively against the question.
FAQ_ENTRIES = [
    {
        "keywords": ("brush", "brushing", "toothbrush"),
        "title": "How often should I brush?",
        "answer": (
            "Brush twice a day, for two minutes each time, with a soft-bristled brush "
            "and fluoride toothpaste. Angle the brush about 45 degrees towards the gum "
            "line and use small circular strokes rather than hard scrubbing -- scrubbing "
            "wears enamel and irritates gums. Brush last thing at night and one other "
            "time, and spit rather than rinse so the fluoride stays on your teeth."
        ),
    },
    {
        "keywords": ("floss", "flossing", "interdental"),
        "title": "Do I really need to floss?",
        "answer": (
            "Yes. A toothbrush cleans about three of the five surfaces of each tooth; "
            "flossing or an interdental brush cleans the two surfaces between teeth, "
            "where most cavities between teeth and most gum inflammation start. Clean "
            "between your teeth once a day, ideally before brushing at night. Bleeding "
            "in the first week is common if you are new to it, but bleeding that "
            "continues beyond about two weeks should be checked."
        ),
    },
    {
        "keywords": ("sensitiv", "cold water", "hot drink", "ice cream"),
        "title": "Why are my teeth sensitive?",
        "answer": (
            "Sensitivity to cold, heat or sweetness usually means dentine -- the layer "
            "under the enamel -- is exposed. Common reasons include gum recession, "
            "enamel wear from acidic food and drink, aggressive brushing, grinding, a "
            "cracked filling, or decay. A desensitising toothpaste used twice a day for "
            "two to four weeks helps many people, but sensitivity that is sharp, "
            "lingering, or that wakes you at night needs an examination, because that "
            "pattern can point to a problem inside the tooth."
        ),
    },
    {
        "keywords": ("toothache", "tooth hurt", "tooth pain", "pain in tooth", "hurts"),
        "title": "Why does my tooth hurt?",
        "answer": (
            "Tooth pain has many possible causes -- decay, a deep filling, a crack, an "
            "exposed root, gum infection, or pressure from grinding or a wisdom tooth. "
            "The pattern matters: a brief twinge with cold is different from a deep, "
            "throbbing ache that keeps you awake, and different again from pain with "
            "facial swelling. Until you are seen, you can rinse with warm salt water, "
            "keep the area clean, avoid very hot or cold food, and use the pain relief "
            "you normally tolerate. Do not place aspirin directly against the gum -- it "
            "burns the tissue. Pain with swelling or fever should be seen the same day."
        ),
    },
    {
        "keywords": ("gum bleed", "bleeding gum", "blood when brush", "gingivitis", "gums bleed"),
        "title": "My gums bleed when I brush",
        "answer": (
            "Gums that bleed are usually inflamed from plaque sitting at the gum line -- "
            "healthy gums do not bleed. The instinct is to brush that area less, but "
            "that makes it worse. Clean gently and thoroughly along the gum line twice a "
            "day and clean between the teeth daily; bleeding often settles within one to "
            "two weeks. If it continues past that, or if your gums are receding, your "
            "teeth feel loose, or you have persistent bad taste, book a check-up and a "
            "professional cleaning."
        ),
    },
    {
        "keywords": ("bad breath", "halitosis", "mouth smell"),
        "title": "What causes bad breath?",
        "answer": (
            "Most persistent bad breath starts in the mouth: bacteria on the back of the "
            "tongue, plaque between teeth, gum inflammation, an untreated cavity, or a "
            "dry mouth. Clean the back of your tongue daily, clean between the teeth, "
            "drink water regularly, and limit smoking and alcohol. If it persists after "
            "two weeks of good cleaning, have it checked -- gum disease and decay are the "
            "usual findings, and occasionally the cause is in the sinuses, throat, or "
            "stomach rather than the mouth."
        ),
    },
    {
        "keywords": ("whiten", "bleach", "stain", "discolor", "discolour", "yellow"),
        "title": "How can I whiten my teeth?",
        "answer": (
            "Surface staining from tea, coffee, smoking or red wine usually responds to a "
            "professional scale and polish. Deeper colour change can be treated with "
            "supervised whitening, either in the clinic or with custom trays to use at "
            "home. Whitening only works on natural tooth structure -- fillings, crowns "
            "and veneers keep their original shade. Over-the-counter kits and charcoal "
            "pastes are often abrasive and can damage enamel, so have any whitening "
            "assessed first, especially if a single tooth has darkened, which can mean "
            "the nerve inside is affected."
        ),
    },
    {
        "keywords": ("check-up", "checkup", "how often dentist", "visit dentist", "see a dentist"),
        "title": "How often should I see a dentist?",
        "answer": (
            "For most adults with healthy teeth and gums, every six months. Your dentist "
            "may set a shorter interval -- three or four months -- if you have gum "
            "disease, a high cavity rate, diabetes, dry mouth, or if you smoke. Children "
            "and people in orthodontic treatment usually need more frequent visits. "
            "Between visits, book sooner if you have pain, swelling, bleeding that does "
            "not settle, a broken tooth or filling, or a sore that has not healed in two "
            "weeks."
        ),
    },
    {
        "keywords": ("wisdom tooth", "wisdom teeth", "third molar"),
        "title": "Do wisdom teeth need to be removed?",
        "answer": (
            "Not always. A wisdom tooth that comes through in a good position, is easy to "
            "clean and does not cause problems can usually stay. Removal is considered "
            "when the tooth is repeatedly infected, is decayed or decaying the tooth in "
            "front, is trapped at an angle, or is causing pain and swelling. The decision "
            "is made from an examination plus an X-ray."
        ),
    },
    {
        "keywords": ("root canal", "rct", "nerve treatment"),
        "title": "What is a root canal treatment?",
        "answer": (
            "A root canal treats a tooth whose inner pulp -- the nerve and blood supply -- "
            "has become infected or irreversibly inflamed, usually from deep decay, a "
            "crack, or trauma. The dentist removes the infected pulp, cleans and shapes "
            "the canals, and seals them; the tooth is then usually restored with a crown "
            "because it becomes more brittle. It is done under local anaesthetic and is "
            "generally no more uncomfortable than a filling. The alternative to treating "
            "it is normally extraction."
        ),
    },
    {
        "keywords": ("cavity", "caries", "decay", "hole in tooth", "filling"),
        "title": "What is a cavity and how is it treated?",
        "answer": (
            "A cavity is a hole formed when acid produced by plaque bacteria dissolves "
            "enamel, usually where sugar is frequent and cleaning is difficult. Very "
            "early decay can sometimes be remineralised with fluoride and better "
            "cleaning. Once a hole has formed, the decay is removed and the tooth is "
            "restored with a filling. Left alone, decay spreads towards the nerve, which "
            "is when pain and root canal treatment or extraction follow. How often you "
            "eat sugar matters more than how much."
        ),
    },
    {
        "keywords": ("knocked out", "avulsed", "broken tooth", "chipped", "trauma", "broke my tooth"),
        "title": "A tooth has been knocked out or broken",
        "answer": (
            "This is urgent. For a knocked-out adult tooth, hold it by the crown, never "
            "the root; if it is dirty rinse it briefly in milk or saline; and if you can, "
            "place it back into the socket and bite gently on a clean cloth. If you "
            "cannot, keep it in milk or in saliva -- never in water -- and get to a "
            "dentist within the hour, because the chance of saving it drops sharply after "
            "that. Never replant a baby tooth. For a broken tooth, keep any fragment, "
            "rinse with warm water, and be seen the same day."
        ),
    },
    {
        "keywords": ("swelling", "swollen", "abscess", "pus"),
        "title": "My face or gum is swollen",
        "answer": (
            "Facial or gum swelling usually means infection, and it needs to be seen "
            "promptly -- the same day. Seek emergency care immediately if the swelling is "
            "spreading, closing your eye, affecting the floor of your mouth or your neck, "
            "or if you have fever, difficulty swallowing, difficulty breathing, or cannot "
            "open your mouth properly. Warm salt-water rinses may ease discomfort, but "
            "they do not treat the infection, and painkillers hide how fast it is moving."
        ),
    },
    {
        "keywords": ("braces", "aligner", "orthodontic", "crooked teeth"),
        "title": "How do braces and aligners work?",
        "answer": (
            "Both apply light, continuous force to move teeth through bone into a planned "
            "position. Fixed braces are bonded to the teeth and adjusted at each visit; "
            "clear aligners are a series of removable trays changed every one to two "
            "weeks and must be worn 20 to 22 hours a day to work. Treatment typically "
            "takes 6 to 24 months depending on the case. Cleaning matters more than usual "
            "during treatment, because plaque around brackets causes permanent white "
            "marks, and retainers afterwards are what stop the teeth drifting back."
        ),
    },
    {
        "keywords": ("pregnan", "expecting a baby"),
        "title": "Dental care during pregnancy",
        "answer": (
            "Routine dental care is safe and recommended during pregnancy, and gums "
            "commonly become more inflamed and bleed more because of hormonal changes, so "
            "cleaning matters more than usual. The second trimester is the most "
            "comfortable time for non-urgent treatment. Tell your dentist you are "
            "pregnant and how many weeks -- it affects choices about X-rays, which are "
            "avoided unless necessary and shielded when needed, and about medication. "
            "Urgent infection is always treated, because untreated infection carries more "
            "risk than the treatment does."
        ),
    },
    {
        "keywords": ("child", "kid", "baby tooth", "first visit", "toddler"),
        "title": "Dental care for children",
        "answer": (
            "Start cleaning as soon as the first tooth appears, with a smear of fluoride "
            "toothpaste, and bring your child for a first visit by their first birthday "
            "or within six months of the first tooth. Supervise brushing until about age "
            "seven. Avoid sugary drinks in bottles and at bedtime. Baby teeth still "
            "matter -- they hold space for adult teeth and decay in them causes pain and "
            "infection, so they are treated rather than ignored."
        ),
    },
    {
        "keywords": ("grind", "bruxism", "clench", "jaw pain", "tmj", "jaw click"),
        "title": "Jaw pain, clicking and grinding",
        "answer": (
            "Jaw ache, clicking, headaches around the temples, and worn or sensitive "
            "teeth often come from clenching or grinding, which is frequently "
            "stress-related and happens at night. A custom night guard protects the teeth "
            "and usually eases the muscle pain. Softer food during a flare-up, warm "
            "compresses, avoiding wide yawning and chewing gum, and managing stress all "
            "help. A jaw that locks open or closed should be assessed promptly."
        ),
    },
    {
        "keywords": ("implant", "missing tooth", "denture", "bridge"),
        "title": "Replacing a missing tooth",
        "answer": (
            "The three usual options are an implant, a bridge, or a denture. An implant "
            "is a titanium post placed in the bone with a crown on top; it does not "
            "involve the neighbouring teeth but needs enough bone and several months to "
            "integrate. A bridge is fixed and faster but is supported by the teeth on "
            "either side, which have to be prepared. A denture is removable and the least "
            "invasive and least expensive. Which suits you depends on the bone, the "
            "neighbouring teeth, your general health and your budget."
        ),
    },
    {
        "keywords": ("extraction", "tooth removed", "socket", "dry socket", "after removal"),
        "title": "Aftercare once a tooth is removed",
        "answer": (
            "Bite firmly on the gauze for 30 to 60 minutes. For the first 24 hours do not "
            "rinse, spit forcefully, smoke, drink through a straw, or exercise hard -- "
            "all of these dislodge the clot that is healing the socket. Eat soft, cool "
            "food and keep the rest of your mouth clean. From the next day, rinse gently "
            "with warm salt water several times daily. Some oozing and swelling for a day "
            "or two is normal. Contact the clinic if bleeding does not stop with firm "
            "pressure, if pain worsens sharply after about three days with a bad taste "
            "(this suggests a dry socket), or if you develop fever."
        ),
    },
    {
        "keywords": ("smoke", "smoking", "tobacco", "gutkha", "pan masala", "quit"),
        "title": "Smoking, tobacco and your mouth",
        "answer": (
            "Tobacco in any form -- smoked or chewed -- is the single biggest avoidable "
            "risk to your mouth. It drives gum disease and tooth loss, stains teeth, "
            "causes bad breath, slows healing after treatment, lowers the success rate of "
            "implants, and is the leading cause of oral cancer. Chewed tobacco and areca "
            "nut products also cause oral submucous fibrosis, which progressively limits "
            "mouth opening. Any white or red patch, lump, or ulcer that has not healed in "
            "two weeks should be examined without delay."
        ),
    },
    {
        "keywords": ("ulcer", "mouth sore", "canker"),
        "title": "Mouth ulcers",
        "answer": (
            "Most mouth ulcers are minor, come from a bite, a sharp tooth or filling, "
            "stress or a run-down period, and heal within 7 to 14 days. A warm salt-water "
            "rinse, avoiding spicy and acidic food, and a protective gel help with the "
            "discomfort. Have an ulcer examined if it has not healed in two weeks, if it "
            "keeps returning in the same place, if it is unusually large or painless, or "
            "if you also have a white or red patch -- those are the ones that need "
            "ruling out properly."
        ),
    },
    {
        "keywords": ("dry mouth", "xerostomia", "no saliva"),
        "title": "Dry mouth",
        "answer": (
            "Saliva protects teeth, so a persistently dry mouth raises the risk of decay "
            "and gum problems sharply. Common causes are medication (many blood pressure, "
            "antidepressant and antihistamine drugs), dehydration, mouth breathing, "
            "smoking, and some medical conditions. Sip water often, chew sugar-free gum "
            "to stimulate flow, avoid alcohol-based mouthwashes and caffeine, and ask "
            "your dentist about high-fluoride toothpaste and saliva substitutes. Do not "
            "stop a prescribed medicine without speaking to your doctor."
        ),
    },
    {
        "keywords": ("cost", "price", "fee", "charge", "expensive", "insurance", "payment"),
        "title": "What will treatment cost?",
        "answer": (
            "Cost depends on the procedure, the materials and how many visits are needed, "
            "so a reliable figure comes only after an examination. The clinic gives you a "
            "written treatment plan with itemised charges before any work begins, and you "
            "can see every invoice and payment in the Billing section of your account. "
            "Ask the front desk about payment options and whether your insurance covers "
            "the planned treatment."
        ),
    },
]

GREETING_RESPONSE = (
    "Hello! I am the clinic dental assistant. I can answer general questions "
    "about teeth and gums, help you make sense of symptoms, suggest a daily "
    "care routine, and walk you through booking an appointment. What would you "
    "like help with?"
)

OUT_OF_SCOPE_RESPONSE = (
    "I can only help with dental and oral-health topics, and with using this "
    "clinic system. For anything medical beyond the mouth, please speak to your "
    "doctor. Is there something about your teeth, gums or an appointment I can "
    "help with?"
)

FALLBACK_RESPONSE = (
    "I do not have specific information on that. The safest answer is to have it "
    "looked at -- you can book an appointment from the Appointments page, or call "
    "the clinic. If you can describe what you are feeling, where it is, and how "
    "long it has been going on, I can give you more useful general guidance."
)

GREETING_WORDS = (
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "namaste", "hii", "helo",
)

APPOINTMENT_KEYWORDS = (
    "appointment", "book", "booking", "slot", "schedule", "reschedule",
    "cancel", "availability", "available", "timing", "when can i come",
)

APPOINTMENT_GUIDE = (
    "To book an appointment: open **Appointments -> Book appointment**, choose a "
    "dentist, pick a date, and the system shows only the slots that are actually "
    "free for that dentist on that day. Add the reason for your visit and anything "
    "you are feeling, then confirm -- you will get a reference number and a "
    "reminder before the visit.\n\n"
    "From **My appointments** you can reschedule or cancel any upcoming booking. "
    "Please give at least 24 hours notice when you cancel so the slot can go to "
    "someone else. If you are in pain today, choose *Emergency* as the reason or "
    "call the clinic directly."
)

# --- Symptom rules ---------------------------------------------------------
# Each entry drives the offline symptom analyser. base_urgency indexes
# ROUTINE / SOON / URGENT / EMERGENCY (0-3) and is the floor for that symptom
# on its own; pain level, swelling, fever and red flags escalate from there.
SYMPTOM_RULES = {
    "tooth_pain": {
        "label": "Tooth pain",
        "areas": ["Tooth decay", "Deep or failing filling", "Inflammation of the tooth pulp", "Cracked tooth"],
        "advice": [
            "Rinse with warm salt water two or three times a day.",
            "Avoid very hot, very cold and sugary food on that side.",
            "Take the pain relief you normally tolerate, following the packet instructions.",
            "Never place aspirin or clove oil directly on the gum -- it burns the tissue.",
        ],
        "base_urgency": 1,
    },
    "sensitivity": {
        "label": "Tooth sensitivity",
        "areas": ["Exposed dentine", "Gum recession", "Enamel wear or erosion", "Early decay"],
        "advice": [
            "Use a desensitising toothpaste twice daily and do not rinse it away.",
            "Switch to a soft brush and use gentle circular strokes.",
            "Cut back on acidic drinks, and wait an hour after them before brushing.",
        ],
        "base_urgency": 0,
    },
    "gum_bleeding": {
        "label": "Bleeding gums",
        "areas": ["Gum inflammation (gingivitis)", "Plaque and tartar at the gum line", "Gum disease"],
        "advice": [
            "Keep cleaning the area gently but thoroughly -- stopping makes it worse.",
            "Clean between the teeth once a day with floss or an interdental brush.",
            "Book a professional cleaning if bleeding continues beyond two weeks.",
        ],
        "base_urgency": 0,
    },
    "swelling": {
        "label": "Swelling",
        "areas": ["Dental infection or abscess", "Spreading gum infection"],
        "advice": [
            "Do not apply heat to the outside of the face.",
            "Keep upright and stay hydrated.",
            "Do not rely on painkillers to wait this out -- swelling needs to be examined.",
        ],
        "base_urgency": 2,
    },
    "bad_breath": {
        "label": "Persistent bad breath",
        "areas": ["Tongue coating", "Gum inflammation", "Untreated decay", "Dry mouth"],
        "advice": [
            "Clean the back of the tongue daily with a brush or scraper.",
            "Clean between the teeth every day.",
            "Drink water through the day and limit smoking and alcohol.",
        ],
        "base_urgency": 0,
    },
    "discoloration": {
        "label": "Tooth discoloration",
        "areas": ["Surface staining", "Enamel changes", "Darkening of a single tooth after injury"],
        "advice": [
            "Cut down on tea, coffee, red wine and tobacco.",
            "Have a professional clean before considering any whitening.",
            "A single tooth that darkens on its own should always be examined.",
        ],
        "base_urgency": 0,
    },
    "loose_tooth": {
        "label": "Loose or shifting tooth",
        "areas": ["Advanced gum disease", "Bone loss around the tooth", "Injury"],
        "advice": [
            "Avoid wobbling the tooth with your tongue or fingers.",
            "Eat softer food and chew on the other side.",
            "An adult tooth that has become loose needs prompt assessment.",
        ],
        "base_urgency": 2,
    },
    "jaw_pain": {
        "label": "Jaw pain or clicking",
        "areas": ["Jaw joint strain", "Clenching or grinding", "Muscle tension"],
        "advice": [
            "Eat softer food for a few days and avoid chewing gum.",
            "Apply a warm compress to the side of the face for 10 to 15 minutes.",
            "Avoid opening wide; support your jaw when you yawn.",
        ],
        "base_urgency": 1,
    },
    "broken_tooth": {
        "label": "Broken or chipped tooth",
        "areas": ["Fractured tooth", "Lost filling or crown", "Exposed dentine or pulp"],
        "advice": [
            "Keep any fragment in milk and bring it with you.",
            "Rinse gently with warm water.",
            "Cover a sharp edge with sugar-free gum or dental wax to protect your tongue.",
        ],
        "base_urgency": 2,
    },
    "mouth_ulcer": {
        "label": "Mouth ulcer or sore",
        "areas": ["Minor trauma from a sharp tooth or filling", "Aphthous ulcer", "Irritation"],
        "advice": [
            "Rinse with warm salt water and avoid spicy or acidic food.",
            "A protective gel from a pharmacy eases the discomfort.",
            "Any ulcer still present after two weeks must be examined.",
        ],
        "base_urgency": 0,
    },
    "dry_mouth": {
        "label": "Dry mouth",
        "areas": ["Reduced saliva flow", "Medication side effect", "Mouth breathing or dehydration"],
        "advice": [
            "Sip water regularly through the day.",
            "Chew sugar-free gum to stimulate saliva.",
            "Avoid alcohol-based mouthwash, caffeine and tobacco.",
        ],
        "base_urgency": 0,
    },
    "bleeding_after_extraction": {
        "label": "Bleeding after an extraction",
        "areas": ["Disturbed blood clot in the socket", "Delayed healing"],
        "advice": [
            "Bite firmly on clean, damp gauze for a full 30 minutes without checking.",
            "Stay upright and keep calm; avoid rinsing, spitting and straws.",
            "If bleeding continues after two rounds of firm pressure, contact the clinic now.",
        ],
        "base_urgency": 2,
    },
}

# Phrases in a free-text description that escalate urgency on their own.
RED_FLAG_PHRASES = {
    "difficulty breathing": "Difficulty breathing",
    "cannot breathe": "Difficulty breathing",
    "trouble breathing": "Difficulty breathing",
    "difficulty swallowing": "Difficulty swallowing",
    "cannot swallow": "Difficulty swallowing",
    "cant swallow": "Difficulty swallowing",
    "swelling under my tongue": "Swelling in the floor of the mouth",
    "floor of my mouth": "Swelling in the floor of the mouth",
    "eye is closing": "Swelling spreading towards the eye",
    "cannot open my mouth": "Restricted mouth opening",
    "cant open my mouth": "Restricted mouth opening",
    "knocked out": "Tooth knocked out",
    "fell out": "Tooth knocked out",
    "high fever": "Fever with dental symptoms",
    "bleeding wont stop": "Bleeding that will not stop",
    "bleeding will not stop": "Bleeding that will not stop",
    "uncontrolled bleeding": "Bleeding that will not stop",
    "spreading": "Spreading swelling",
    "numbness in my lip": "Altered sensation in the lip or chin",
}

CARE_TIPS_BASE = [
    "Brush twice daily for two minutes with a fluoride toothpaste.",
    "Clean between your teeth once a day with floss or an interdental brush.",
    "Spit after brushing instead of rinsing, so the fluoride keeps working.",
    "Drink water after sugary or acidic food and drink.",
]

DIET_TIPS_BASE = [
    "Keep sugary food and drink to mealtimes -- frequency matters more than quantity.",
    "Choose water or plain milk between meals instead of juice or soft drinks.",
    "Crunchy vegetables, cheese and nuts are tooth-friendly snacks.",
    "Wait an hour after acidic food or drink before brushing.",
]

WARNING_SIGNS_BASE = [
    "Gums that bleed for more than two weeks despite good cleaning.",
    "Pain that wakes you at night or lingers after hot or cold food.",
    "Any facial or gum swelling -- this needs same-day attention.",
    "A mouth ulcer or patch that has not healed in two weeks.",
    "A tooth that feels loose, or a bite that suddenly feels different.",
]
