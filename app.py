import os
import json
import hashlib
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pps-profile-secret-2026')

APP_PASSWORD = os.environ.get('APP_PASSWORD', 'PureProfile2026')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Luther1985')
DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_db():
    if not DATABASE_URL:
        return None
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS profile_results (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            taken_date DATE NOT NULL,
            taken_year INTEGER NOT NULL,
            disc_d INTEGER,
            disc_i INTEGER,
            disc_s INTEGER,
            disc_c INTEGER,
            motiv_achievement INTEGER,
            motiv_affiliation INTEGER,
            motiv_security INTEGER,
            motiv_autonomy INTEGER,
            motiv_service INTEGER,
            motiv_growth INTEGER,
            primary_disc VARCHAR(50),
            secondary_disc VARCHAR(50),
            primary_motiv VARCHAR(50),
            character_match VARCHAR(255),
            character_show VARCHAR(255),
            full_results JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"DB init error: {e}")

# ── SCORING ENGINE ──────────────────────────────────────────────────────────────

def score_responses(answers):
    """
    answers: dict of { "q1": "A", "q2": "C", ... }
    Each question maps its options to DISC/Motiv scores.
    Returns normalized 0-100 scores for D, I, S, C and 6 motivators.
    """
    disc = {'D': 0, 'I': 0, 'S': 0, 'C': 0}
    motiv = {
        'Achievement': 0, 'Affiliation': 0, 'Security': 0,
        'Autonomy': 0, 'Service': 0, 'Growth': 0
    }

    scoring_map = get_scoring_map()

    for q_key, choice in answers.items():
        q_num = q_key  # e.g. "q1"
        if q_num in scoring_map and choice in scoring_map[q_num]:
            scores = scoring_map[q_num][choice]
            for dimension, value in scores.items():
                if dimension in disc:
                    disc[dimension] += value
                elif dimension in motiv:
                    motiv[dimension] += value

    # Normalize DISC to 0-100
    disc_qs = 28  # questions contributing to DISC
    motiv_qs = 16  # questions contributing to motivators
    max_per_disc = disc_qs * 3  # max possible per dimension
    max_per_motiv = motiv_qs * 3

    disc_norm = {k: min(100, round((v / max_per_disc) * 100)) for k, v in disc.items()}
    motiv_norm = {k: min(100, round((v / max_per_motiv) * 100)) for k, v in motiv.items()}

    return disc_norm, motiv_norm


def get_scoring_map():
    """
    Maps each question number to answer options and their dimensional scores.
    Format: { 'q1': { 'A': {'D': 3, 'I': 0, ...}, 'B': {...}, ... } }
    Higher = stronger signal for that dimension.
    """
    return {
        # ── DISC SCENARIO QUESTIONS (q1–q28) ──
        'q1': {  # Deadline pressure
            'A': {'D': 3, 'I': 1, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'C': {'D': 1, 'I': 0, 'S': 3, 'C': 0},
            'D': {'D': 0, 'I': 0, 'S': 1, 'C': 3},
        },
        'q2': {  # New team member
            'A': {'D': 1, 'I': 3, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
            'C': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'D': {'D': 0, 'I': 1, 'S': 1, 'C': 3},
        },
        'q3': {  # Conflict with coworker
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 2, 'S': 1, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 0},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q4': {  # Leading a project
            'A': {'D': 3, 'I': 1, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 3, 'S': 0, 'C': 0},
            'C': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q5': {  # Unexpected change
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'B': {'D': 1, 'I': 3, 'S': 0, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
            'D': {'D': 0, 'I': 0, 'S': 1, 'C': 3},
        },
        'q6': {  # Presenting to client
            'A': {'D': 2, 'I': 3, 'S': 0, 'C': 0},
            'B': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'C': {'D': 0, 'I': 1, 'S': 2, 'C': 3},
            'D': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
        },
        'q7': {  # Receiving critical feedback
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
            'C': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
            'D': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
        },
        'q8': {  # Team celebration
            'A': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'B': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'C': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q9': {  # Problem-solving approach
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 0, 'S': 1, 'C': 3},
            'C': {'D': 1, 'I': 3, 'S': 0, 'C': 0},
            'D': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
        },
        'q10': {  # Disagreeing with manager
            'A': {'D': 3, 'I': 1, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
            'C': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
            'D': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
        },
        'q11': {  # Planning a complex job
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 0, 'S': 2, 'C': 3},
            'C': {'D': 1, 'I': 3, 'S': 0, 'C': 0},
            'D': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
        },
        'q12': {  # When a project stalls
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 3, 'S': 0, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 0},
            'D': {'D': 0, 'I': 0, 'S': 0, 'C': 3},
        },
        'q13': {  # New process introduced
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 0},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q14': {  # Working alone vs. team
            'A': {'D': 2, 'I': 0, 'S': 0, 'C': 3},
            'B': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'C': {'D': 3, 'I': 1, 'S': 0, 'C': 0},
            'D': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
        },
        'q15': {  # High-stakes mistake
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 1, 'C': 3},
            'D': {'D': 1, 'I': 3, 'S': 0, 'C': 0},
        },
        'q16': {  # Motivating others
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 3, 'S': 0, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 0},
            'D': {'D': 0, 'I': 0, 'S': 0, 'C': 3},
        },
        'q17': {  # Meeting style
            'A': {'D': 3, 'I': 1, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q18': {  # Ambiguous instructions
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 2, 'S': 1, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q19': {  # Recognizing team win
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'C': {'D': 1, 'I': 1, 'S': 3, 'C': 0},
            'D': {'D': 0, 'I': 0, 'S': 1, 'C': 3},
        },
        'q20': {  # Difficult client
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 3, 'S': 0, 'C': 0},
            'C': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q21': {  # Balancing quality and speed
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 0, 'S': 1, 'C': 3},
            'C': {'D': 1, 'I': 3, 'S': 0, 'C': 0},
            'D': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
        },
        'q22': {  # Onboarding new hire
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'C': {'D': 0, 'I': 1, 'S': 3, 'C': 0},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q23': {  # Under stress
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 3, 'S': 0, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 0},
            'D': {'D': 0, 'I': 0, 'S': 0, 'C': 3},
        },
        'q24': {  # End of week reflection
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'C': {'D': 1, 'I': 0, 'S': 3, 'C': 0},
            'D': {'D': 0, 'I': 1, 'S': 0, 'C': 3},
        },
        'q25': {  # Scope change on a job
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 0},
            'B': {'D': 0, 'I': 2, 'S': 1, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
            'D': {'D': 1, 'I': 0, 'S': 0, 'C': 3},
        },
        'q26': {  # Giving critical feedback
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 2, 'S': 1, 'C': 0},
            'C': {'D': 1, 'I': 0, 'S': 3, 'C': 0},
            'D': {'D': 0, 'I': 1, 'S': 0, 'C': 3},
        },
        'q27': {  # Ideal work day
            'A': {'D': 3, 'I': 0, 'S': 0, 'C': 1},
            'B': {'D': 0, 'I': 3, 'S': 1, 'C': 0},
            'C': {'D': 1, 'I': 1, 'S': 3, 'C': 0},
            'D': {'D': 0, 'I': 0, 'S': 1, 'C': 3},
        },
        'q28': {  # Representing the company
            'A': {'D': 3, 'I': 1, 'S': 0, 'C': 0},
            'B': {'D': 1, 'I': 3, 'S': 0, 'C': 0},
            'C': {'D': 0, 'I': 0, 'S': 3, 'C': 1},
            'D': {'D': 0, 'I': 1, 'S': 1, 'C': 3},
        },

        # ── MOTIVATORS/VALUES QUESTIONS (q29–q44) ──
        'q29': {  # What drives you most
            'A': {'Achievement': 3},
            'B': {'Affiliation': 3},
            'C': {'Security': 3},
            'D': {'Autonomy': 3},
        },
        'q30': {  # Choosing a project
            'A': {'Growth': 3},
            'B': {'Achievement': 2},
            'C': {'Service': 3},
            'D': {'Security': 2},
        },
        'q31': {  # What makes work meaningful
            'A': {'Service': 3},
            'B': {'Achievement': 2},
            'C': {'Growth': 2},
            'D': {'Affiliation': 3},
        },
        'q32': {  # Recognition style
            'A': {'Achievement': 3},
            'B': {'Affiliation': 2},
            'C': {'Autonomy': 3},
            'D': {'Service': 2},
        },
        'q33': {  # Career priority
            'A': {'Growth': 3},
            'B': {'Security': 3},
            'C': {'Achievement': 2},
            'D': {'Autonomy': 2},
        },
        'q34': {  # Team vs. solo
            'A': {'Affiliation': 3},
            'B': {'Autonomy': 3},
            'C': {'Achievement': 1},
            'D': {'Service': 2},
        },
        'q35': {  # When you feel most energized
            'A': {'Achievement': 3},
            'B': {'Service': 3},
            'C': {'Growth': 2},
            'D': {'Affiliation': 2},
        },
        'q36': {  # Loyalty driver
            'A': {'Security': 3},
            'B': {'Affiliation': 3},
            'C': {'Growth': 2},
            'D': {'Achievement': 1},
        },
        'q37': {  # How you define success
            'A': {'Achievement': 3},
            'B': {'Service': 3},
            'C': {'Affiliation': 2},
            'D': {'Autonomy': 2},
        },
        'q38': {  # Handling routine work
            'A': {'Security': 3},
            'B': {'Growth': 3},
            'C': {'Autonomy': 2},
            'D': {'Achievement': 1},
        },
        'q39': {  # Feedback preference
            'A': {'Growth': 3},
            'B': {'Achievement': 2},
            'C': {'Security': 2},
            'D': {'Affiliation': 3},
        },
        'q40': {  # What you protect most
            'A': {'Autonomy': 3},
            'B': {'Affiliation': 3},
            'C': {'Security': 2},
            'D': {'Service': 2},
        },
        'q41': {  # Why you go above and beyond
            'A': {'Achievement': 3},
            'B': {'Service': 3},
            'C': {'Affiliation': 2},
            'D': {'Growth': 2},
        },
        'q42': {  # Work environment preference
            'A': {'Security': 3},
            'B': {'Autonomy': 3},
            'C': {'Affiliation': 2},
            'D': {'Growth': 2},
        },
        'q43': {  # What you'd change about work
            'A': {'Autonomy': 3},
            'B': {'Growth': 3},
            'C': {'Service': 2},
            'D': {'Security': 1},
        },
        'q44': {  # Long-term vision
            'A': {'Achievement': 3},
            'B': {'Service': 3},
            'C': {'Security': 2},
            'D': {'Growth': 3},
        },
    }


def determine_profile(disc, motiv):
    """Determine primary/secondary DISC type and primary motivator."""
    primary_disc = max(disc, key=disc.get)
    sorted_disc = sorted(disc.items(), key=lambda x: x[1], reverse=True)
    secondary_disc = sorted_disc[1][0] if sorted_disc[1][1] >= 35 else None
    primary_motiv = max(motiv, key=motiv.get)
    return primary_disc, secondary_disc, primary_motiv


def get_character_match(primary_disc, secondary_disc, primary_motiv):
    """Match to TV/movie character based on DISC profile."""
    characters = {
        ('D', 'I'): ('Harvey Specter', 'Suits', 'Commanding and charismatic — you push hard for results but know how to work a room. You lead from the front and expect the same from everyone around you.'),
        ('D', 'C'): ('Lisbeth Salander', 'The Girl with the Dragon Tattoo', 'Intensely driven and methodical — you solve problems others can\'t and you do it your way. You don\'t need validation; results speak for themselves.'),
        ('D', 'S'): ('Ned Stark', 'Game of Thrones', 'You lead with conviction and protect what matters. Decisive under pressure, you never waver on your values even when it costs you.'),
        ('D', None): ('Miranda Priestly', 'The Devil Wears Prada', 'Razor-focused and results-driven. You set the standard, expect excellence, and don\'t waste time explaining yourself twice.'),
        ('I', 'D'): ('Tony Stark', 'Iron Man / Avengers', 'Brilliant, bold, and impossible to ignore. You thrive in the spotlight and push everyone around you to think bigger.'),
        ('I', 'S'): ('Leslie Knope', 'Parks and Recreation', 'Enthusiastic, caring, and relentlessly optimistic. You bring people together and make them believe in the mission as much as you do.'),
        ('I', 'C'): ('Sherlock Holmes', 'Sherlock (BBC)', 'Exceptionally perceptive and expressive — you can read a room and a problem simultaneously. Your confidence can read as arrogance, but your accuracy usually proves you right.'),
        ('I', None): ('Michael Scott', 'The Office', 'Your energy is contagious and your heart is always in the right place. You want everyone to love being here — and most of the time, they do.'),
        ('S', 'I'): ('Ted Lasso', 'Ted Lasso', 'Warm, steady, and deeply committed to the people around you. You lead through trust and your team would run through a wall for you.'),
        ('S', 'C'): ('Samwise Gamgee', 'The Lord of the Rings', 'The most dependable person in any room. You\'re not chasing the spotlight — you\'re making sure the mission gets done and nobody gets left behind.'),
        ('S', 'D'): ('Captain America', 'Marvel / Avengers', 'Principled, loyal, and steady under fire. You lead by example and hold the line even when it\'s hard. People follow you because they trust you completely.'),
        ('S', None): ('Meredith Grey', 'Grey\'s Anatomy', 'Calm in chaos, loyal under pressure. You process deeply before responding, and when you commit to someone or something, it\'s total.'),
        ('C', 'D'): ('Walter White', 'Breaking Bad', 'Meticulous and driven — a dangerous combination when pointed in the right direction. You don\'t guess; you know. And you don\'t stop until it\'s right.'),
        ('C', 'I'): ('Hermione Granger', 'Harry Potter', 'Precise, prepared, and surprisingly warm once you trust someone. You\'ve done the research others skipped and you\'re not shy about it.'),
        ('C', 'S'): ('Atticus Finch', 'To Kill a Mockingbird', 'Thoughtful, principled, and thorough. You weigh every angle before acting and your steadiness makes people feel safe in uncertain situations.'),
        ('C', None): ('Spock', 'Star Trek', 'Logic-first, always. You trust data over gut and precision over speed. Others may not always understand your methods, but they rarely argue with your results.'),
    }

    key = (primary_disc, secondary_disc)
    if key in characters:
        return characters[key]

    # Fallback to primary only
    fallback_key = (primary_disc, None)
    if fallback_key in characters:
        return characters[fallback_key]

    return ('A True Original', 'Across Many Stories', 'Your profile is uniquely balanced — you adapt naturally to what the situation demands.')


def build_full_report(disc, motiv, primary_disc, secondary_disc, primary_motiv):
    """Build the full narrative report based on scores."""

    profiles = {
        'D': {
            'label': 'Decisive',
            'tagline': 'You drive toward results. Fast.',
            'strengths': [
                'Takes initiative and acts without needing consensus',
                'Performs well under pressure and tight deadlines',
                'Cuts through ambiguity to get things moving',
                'Holds high standards for self and others',
                'Comfortable making unpopular decisions when necessary',
            ],
            'blind_spots': [
                'Can come across as blunt or dismissive of others\' input',
                'May move too fast and miss important details',
                'Tendency to steamroll rather than collaborate',
                'Can underestimate the emotional impact of direct communication',
                'May struggle to slow down when the team needs more time',
            ],
            'energizers': [
                'Clear goals with measurable outcomes',
                'Authority to make decisions without excessive approval',
                'Competitive environments where winning matters',
                'Autonomy to execute without micromanagement',
                'Solving problems that require quick decisive action',
            ],
            'drainers': [
                'Slow decision-making processes or committee thinking',
                'Repetitive routine work with no challenge',
                'Being second-guessed after a decision is made',
                'Long-winded meetings without clear outcomes',
                'Working with people who avoid accountability',
            ],
            'comm_style': 'Be direct and brief. Lead with the bottom line — what you need and by when. Skip the backstory unless asked. Use bullet points in writing. They respect candor and will lose interest in anything that feels like a preamble.',
            'conflict_style': 'Moves toward conflict rather than away from it. Addresses issues head-on, sometimes before the other person is ready. Best approached with facts, not feelings. Don\'t expect them to tiptoe — and don\'t tiptoe around them.',
            'main_question': 'WHAT needs to happen and WHEN?',
        },
        'I': {
            'label': 'Interactive',
            'tagline': 'You energize every room you walk into.',
            'strengths': [
                'Builds rapport and trust quickly with new people',
                'Communicates with enthusiasm that gets others on board',
                'Creates a positive team culture naturally',
                'Thinks creatively and brings fresh ideas to problems',
                'Inspires others to believe in the mission',
            ],
            'blind_spots': [
                'May over-promise and under-deliver on details',
                'Can lose focus mid-task when something more interesting appears',
                'Sensitive to criticism, even when constructive',
                'May rely too heavily on charm in situations that need data',
                'Can dominate conversations without realizing it',
            ],
            'energizers': [
                'Collaborative work with people you genuinely like',
                'Recognition and positive feedback for contributions',
                'Creative projects with room to put your mark on things',
                'Variety — different tasks, different people, different challenges',
                'High-energy environments where things are always moving',
            ],
            'drainers': [
                'Isolated work with no human interaction',
                'Rigid environments with no flexibility or creativity',
                'Being dismissed or ignored in group settings',
                'Detailed, repetitive administrative work',
                'Environments where relationships don\'t matter',
            ],
            'comm_style': 'Start warm — ask about them before jumping to business. Be expressive and enthusiastic. They respond to energy. Keep written communication friendly, not clinical. Give them room to talk and share ideas; don\'t rush to the point.',
            'conflict_style': 'Avoids conflict initially by turning on the charm. When conflict does arise, they want to talk it through emotionally. Acknowledge how they feel first before addressing the issue. Never dismiss or minimize their perspective — they\'ll shut down.',
            'main_question': 'WHO is involved and how will they feel about it?',
        },
        'S': {
            'label': 'Stabilizing',
            'tagline': 'You are the steady force everyone leans on.',
            'strengths': [
                'Deeply loyal and consistent — shows up every time',
                'Excellent listener who makes others feel heard',
                'Keeps the team grounded during high-pressure situations',
                'Builds deep trust through reliability over time',
                'Mediates conflict and keeps relationships intact',
            ],
            'blind_spots': [
                'Avoids conflict to the point of letting issues fester',
                'May say yes to too much to keep the peace',
                'Resistant to change, even when change is needed',
                'Can be hard to read — emotions stay internal',
                'May not advocate strongly enough for their own needs',
            ],
            'energizers': [
                'Clear expectations and a stable, predictable environment',
                'Working with a team that trusts and values each other',
                'Knowing the "why" behind what they\'re being asked to do',
                'Meaningful work that helps real people',
                'Recognition that acknowledges their reliability, not just results',
            ],
            'drainers': [
                'Sudden changes without explanation or context',
                'Environments with constant conflict or instability',
                'Being pushed to make fast decisions without time to process',
                'Feeling like their contributions go unnoticed',
                'Unclear roles or shifting expectations',
            ],
            'comm_style': 'Take time to connect before getting to business. Ask their opinion and wait for it — don\'t rush them to answer. Warm, sincere written communication. Always explain the "why" behind requests. Follow up with them personally after difficult conversations.',
            'conflict_style': 'Avoids conflict at almost any cost. When conflict is unavoidable, go slow, be warm, and lead with the relationship. Make it clear you value them before addressing the issue. Don\'t expect an immediate emotional reaction — they process privately.',
            'main_question': 'WHY are we doing this and how does it affect the team?',
        },
        'C': {
            'label': 'Cautious',
            'tagline': 'You get it right when everyone else gets it close.',
            'strengths': [
                'Produces work of consistently high quality',
                'Anticipates problems before they happen',
                'Builds systems and processes that prevent errors',
                'Asks the questions others are afraid to ask',
                'Holds the standard when everyone else wants to cut corners',
            ],
            'blind_spots': [
                'Can get paralyzed by the need for more information',
                'May come across as overly critical or impossible to please',
                'Reluctant to share opinions without rock-solid evidence',
                'Can struggle to move fast when the situation demands it',
                'May isolate during stress instead of asking for help',
            ],
            'energizers': [
                'Problems with clear right answers that reward thoroughness',
                'High-quality standards that actually matter',
                'Time to research and think before acting',
                'Working with competent people who respect precision',
                'Environments where accuracy is valued over speed',
            ],
            'drainers': [
                'Being asked to "just guess" or skip proper process',
                'Working with people who are careless or sloppy',
                'Environments with no standards or accountability',
                'Constant interruptions that break focus',
                'Being criticized publicly rather than privately',
            ],
            'comm_style': 'Be factual, detailed, and organized. They respect people who have done their homework. Don\'t rush them. Written follow-ups are welcome. Ask specific questions. Avoid vague requests — define exactly what you need and by when.',
            'conflict_style': 'Withdraws and analyzes during conflict. May appear cold or detached but is actually processing deeply. Give them time and space. Present facts, not emotions. They will respond better to a written outline of the issue than a face-to-face confrontation.',
            'main_question': 'HOW will this be done and is it being done correctly?',
        },
    }

    motiv_profiles = {
        'Achievement': 'You are driven by results, progress, and the satisfaction of reaching a goal. You measure your own success — and you hold yourself to a high standard. Recognizing your wins matters to you, but only when they\'re actually earned.',
        'Affiliation': 'You are motivated by relationships, belonging, and the bonds built through shared work. The strength of your team and the quality of your connections mean as much to you as the outcome itself.',
        'Security': 'Stability and reliability fuel you. You perform at your best when expectations are clear, the environment is predictable, and the ground under you feels solid. Uncertainty is your biggest enemy.',
        'Autonomy': 'You need ownership. When you\'re given the freedom to decide how to do something, you bring your best. Micromanagement shuts you down faster than anything else.',
        'Service': 'Impact is your currency. Knowing that your work genuinely helps someone — a client, a resident, a teammate — is what makes the effort worth it. You\'re not in it for yourself.',
        'Growth': 'You are never finished becoming. Learning new skills, taking on harder challenges, and pushing past what you\'ve already mastered is what keeps you engaged. Stagnation is the enemy.',
    }

    disc_profile = profiles[primary_disc]
    motiv_description = motiv_profiles[primary_motiv]

    return {
        'disc_profile': disc_profile,
        'motiv_description': motiv_description,
        'primary_disc': primary_disc,
        'secondary_disc': secondary_disc,
        'primary_motiv': primary_motiv,
    }


# ── ROUTES ──────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('authenticated'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        pwd = request.form.get('password', '')
        if pwd == APP_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        elif pwd == ADMIN_PASSWORD:
            session['authenticated'] = True
            session['admin'] = True
            return redirect(url_for('admin'))
        else:
            error = 'Incorrect password. Please try again.'
    return render_template('login.html', error=error)


@app.route('/profile')
def index():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('index.html')


@app.route('/take-test')
def take_test():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return render_template('test.html', questions=get_questions())


@app.route('/submit', methods=['POST'])
def submit():
    if not session.get('authenticated'):
        return redirect(url_for('login'))

    data = request.get_json()
    name = data.get('name', '').strip()
    answers = data.get('answers', {})

    if not name or len(answers) < 44:
        return jsonify({'error': 'Incomplete submission'}), 400

    disc, motiv = score_responses(answers)
    primary_disc, secondary_disc, primary_motiv = determine_profile(disc, motiv)
    character, show, character_desc = get_character_match(primary_disc, secondary_disc, primary_motiv)
    report = build_full_report(disc, motiv, primary_disc, secondary_disc, primary_motiv)

    today = datetime.now().date()
    year = today.year

    full_results = {
        'disc': disc,
        'motiv': motiv,
        'primary_disc': primary_disc,
        'secondary_disc': secondary_disc,
        'primary_motiv': primary_motiv,
        'character': character,
        'show': show,
        'character_desc': character_desc,
        'report': report,
    }

    # Save to DB
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO profile_results
                (name, taken_date, taken_year, disc_d, disc_i, disc_s, disc_c,
                 motiv_achievement, motiv_affiliation, motiv_security, motiv_autonomy,
                 motiv_service, motiv_growth, primary_disc, secondary_disc, primary_motiv,
                 character_match, character_show, full_results)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                name, today, year,
                disc['D'], disc['I'], disc['S'], disc['C'],
                motiv['Achievement'], motiv['Affiliation'], motiv['Security'],
                motiv['Autonomy'], motiv['Service'], motiv['Growth'],
                primary_disc, secondary_disc, primary_motiv,
                character, show, json.dumps(full_results)
            ))
            result_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
            session['last_result_id'] = result_id
    except Exception as e:
        print(f"DB save error: {e}")

    session['last_result'] = full_results
    return jsonify({'redirect': url_for('results')})


@app.route('/results')
def results():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    result = session.get('last_result')
    if not result:
        return redirect(url_for('index'))
    return render_template('results.html', result=result)


@app.route('/history')
def history():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    name = request.args.get('name', '').strip()
    rows = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            if name:
                cur.execute(
                    'SELECT * FROM profile_results WHERE LOWER(name) = LOWER(%s) ORDER BY taken_date DESC',
                    (name,)
                )
            else:
                cur.execute('SELECT DISTINCT LOWER(name) as name FROM profile_results ORDER BY name')
            rows = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"DB history error: {e}")
    return render_template('history.html', rows=rows, searched_name=name)


@app.route('/history/<int:result_id>')
def view_result(result_id):
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    row = None
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM profile_results WHERE id = %s', (result_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"DB view error: {e}")
    if not row:
        return redirect(url_for('history'))
    result = row['full_results']
    if isinstance(result, str):
        result = json.loads(result)
    return render_template('results.html', result=result, from_history=True,
                           taken_date=row['taken_date'], taken_name=row['name'])


@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    year_filter = request.args.get('year', str(datetime.now().year))
    rows = []
    years = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT DISTINCT taken_year FROM profile_results ORDER BY taken_year DESC')
            years = [r['taken_year'] for r in cur.fetchall()]
            cur.execute(
                '''SELECT id, name, taken_date, disc_d, disc_i, disc_s, disc_c,
                          primary_disc, secondary_disc, primary_motiv, character_match, character_show
                   FROM profile_results WHERE taken_year = %s ORDER BY name, taken_date DESC''',
                (year_filter,)
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin DB error: {e}")
    return render_template('admin.html', rows=rows, years=years, selected_year=int(year_filter))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def get_questions():
    return [
        # ── DISC SCENARIOS ──
        {
            'id': 'q1',
            'section': 'DISC',
            'text': "It's Thursday afternoon and your manager just moved a major deadline to Friday morning. You still have a full day's worth of work left. How do you actually respond?",
            'options': [
                ('A', "You immediately cut out anything non-essential, set a hard plan, and start executing. You'll figure out the rest when you get there."),
                ('B', "You send a message to the team letting everyone know what's happening and rallying anyone who can help get it done together."),
                ('C', "You take a breath, reorganize your task list carefully, and work steadily through the night if needed — no shortcuts."),
                ('D', "You flag the risk back to your manager with a clear summary of what can realistically be finished by morning, and what can't."),
            ]
        },
        {
            'id': 'q2',
            'section': 'DISC',
            'text': "A new team member joins who clearly has experience but seems hesitant to speak up in group settings. You notice this in their first week. What do you do?",
            'options': [
                ('A', "You give them space to warm up on their own — you don't want to put them on the spot."),
                ('B', "You find a natural moment to pull them aside and ask what kind of environment they work best in."),
                ('C', "You put them on a small piece of a project right away so they can prove themselves and build confidence through results."),
                ('D', "You personally introduce them around, make sure they feel included in conversations, and keep the energy welcoming."),
            ]
        },
        {
            'id': 'q3',
            'section': 'DISC',
            'text': "A coworker keeps missing deadlines that directly affect your work. You've let it slide twice. It happens again. How do you handle it?",
            'options': [
                ('A', "You address it directly and privately — clearly, not harshly. You tell them what you need and what happens if it continues."),
                ('B', "You try to understand what's going on in their world first — maybe there's something affecting their performance you don't know about."),
                ('C', "You document the pattern and bring it to your manager with specifics — dates, impacts, and a proposed solution."),
                ('D', "You have an honest but casual conversation and try to find a system that works better for both of you going forward."),
            ]
        },
        {
            'id': 'q4',
            'section': 'DISC',
            'text': "You're put in charge of a cross-functional project with a team of five people, none of whom report to you. How do you lead?",
            'options': [
                ('A', "You define roles and expectations up front, establish a clear timeline, and hold weekly check-ins to make sure everyone stays on track."),
                ('B', "You call a kickoff meeting to get energy up, make sure everyone knows why the project matters, and keep the momentum high throughout."),
                ('C', "You start by having one-on-ones with each person to understand their working style before deciding how to structure things."),
                ('D', "You build a detailed project plan, assign tasks based on each person's strengths, and create a shared tracker so nothing falls through the cracks."),
            ]
        },
        {
            'id': 'q5',
            'section': 'DISC',
            'text': "You've been working a certain way for two years. Your company announces a major process change that affects your entire workflow — effective immediately. Your honest first reaction is:",
            'options': [
                ('A', "Frustration. You'll adapt, but changing something that was working fine wastes energy and creates unnecessary disruption."),
                ('B', "Curiosity. You want to understand why the change is happening before you decide how you feel about it."),
                ('C', "Excitement. Change means new opportunity — you're already thinking about how to leverage it."),
                ('D', "Caution. You want to understand the new process thoroughly before committing to it so you don't make mistakes."),
            ]
        },
        {
            'id': 'q6',
            'section': 'DISC',
            'text': "You're presenting a proposal to an important client who is skeptical and asking hard questions. How do you show up?",
            'options': [
                ('A', "Confident and direct — you've done the work, you know the answer, and you're not going to hedge."),
                ('B', "Warm and engaging — you make them feel heard, build a real connection, and use their skepticism as an opportunity to earn trust."),
                ('C', "Precise and prepared — you have data for every concern and you walk them through the logic methodically."),
                ('D', "Steady and reassuring — you project calm confidence and make sure they feel like they're in good hands."),
            ]
        },
        {
            'id': 'q7',
            'section': 'DISC',
            'text': "Your manager gives you critical feedback on a project you put real effort into. They say your approach missed the mark. Your gut reaction is:",
            'options': [
                ('A', "You ask for specifics immediately and start mentally rebuilding — you'd rather know than not know."),
                ('B', "You listen fully, thank them for the feedback, and reflect on it privately before responding."),
                ('C', "You feel it personally at first, but push through it — you genuinely want to improve and use it as fuel."),
                ('D', "You want to understand their reasoning — if you agree, you act on it; if you don't, you'll respectfully push back with evidence."),
            ]
        },
        {
            'id': 'q8',
            'section': 'DISC',
            'text': "Your team just hit a major milestone — a big win by anyone's measure. How do you want to celebrate?",
            'options': [
                ('A', "Acknowledge it, mark the moment, and then get focused on what's next — winning is good but it shouldn't slow momentum."),
                ('B', "Make it a real event. Bring the team together, share the story, make people feel the weight of what they accomplished."),
                ('C', "A genuine, personal acknowledgment of each person's contribution — a team dinner or something where everyone feels seen."),
                ('D', "A written recognition that captures what was achieved and how — something tangible that reflects the quality of the work."),
            ]
        },
        {
            'id': 'q9',
            'section': 'DISC',
            'text': "You're handed a problem that nobody on your team has solved before. There's no playbook. How do you approach it?",
            'options': [
                ('A', "You start moving immediately — test something, see what happens, and iterate from there."),
                ('B', "You research everything you can find, map out the variables, and build a solution based on evidence."),
                ('C', "You get the right people in a room and work through it together — someone has encountered something similar before."),
                ('D', "You think it through on your own first, build a hypothesis, and then pressure-test it before committing."),
            ]
        },
        {
            'id': 'q10',
            'section': 'DISC',
            'text': "You strongly disagree with a decision your manager just made. You think it's the wrong call. What do you do?",
            'options': [
                ('A', "You say something — respectfully but directly. You can't pretend to agree with something you think is wrong."),
                ('B', "You ask for a conversation, share your concerns with context, and try to understand their thinking before pushing back."),
                ('C', "You share your perspective once clearly, and if they still go the other direction, you commit and execute."),
                ('D', "You build the strongest case you can with data and present it. If they still disagree, you document your concern and move forward."),
            ]
        },
        {
            'id': 'q11',
            'section': 'DISC',
            'text': "You're planning a complex job with a lot of moving pieces, multiple vendors, and a hard deadline. Where do you start?",
            'options': [
                ('A', "You identify the critical path — what absolutely cannot be late — and build your plan around protecting those things."),
                ('B', "You pull everyone together early to align on scope, roles, and timeline before anyone starts moving independently."),
                ('C', "You build a comprehensive plan with every dependency mapped before you start — surprises are the enemy."),
                ('D', "You assign clear ownership to each workstream and set up a system to track progress without needing constant check-ins."),
            ]
        },
        {
            'id': 'q12',
            'section': 'DISC',
            'text': "A project you're running has stalled. Nobody is moving, momentum is dead, and the deadline is still real. What do you do?",
            'options': [
                ('A', "You call it out directly in the team — name the problem, reassign if needed, and force momentum back into the work."),
                ('B', "You energize the team. Get people together, reset the vision, remind them why this matters, and rebuild momentum through people."),
                ('C', "You have quiet conversations with key people, understand what's blocking them, and remove obstacles systematically."),
                ('D', "You diagnose the root cause first — what specifically is stalling and why — then build a recovery plan before you start moving people around."),
            ]
        },
        {
            'id': 'q13',
            'section': 'DISC',
            'text': "Your company rolls out a new process for something you've been doing your own way for years. Your way works. The new way is unproven. How do you handle it?",
            'options': [
                ('A', "You implement it as directed, track the results, and bring data back if the old way was clearly better."),
                ('B', "You ask the questions nobody else is asking about why this change was made and what problem it's actually solving."),
                ('C', "You give it a fair shot. Change can be good — you stay open and follow the new process with full effort."),
                ('D', "You raise your concerns through the right channel but adapt in the meantime — you're not going to fight every battle."),
            ]
        },
        {
            'id': 'q14',
            'section': 'DISC',
            'text': "You have a full day of deep, focused work ahead. Your ideal setup is:",
            'options': [
                ('A', "Alone — door closed, no interruptions, headphones in. You do your best thinking without other people's noise."),
                ('B', "In a coffee shop or open space with low-level ambient activity — enough to keep energy up without being pulled into conversations."),
                ('C', "Near your team, even if you're not actively collaborating. Energy in the room keeps you moving."),
                ('D', "Wherever you can get things done fastest. Environment matters less than having a clear list and the authority to act on it."),
            ]
        },
        {
            'id': 'q15',
            'section': 'DISC',
            'text': "You make a high-stakes mistake that affects a client. It was your call and it didn't go right. What happens next?",
            'options': [
                ('A', "You own it immediately, go directly to the client, and focus every ounce of energy on fixing it — no excuses."),
                ('B', "You make sure the client knows they're not alone in it. You communicate clearly and keep them informed every step of the way."),
                ('C', "You analyze exactly what went wrong so you can prevent it from ever happening again — the fix and the lesson matter equally."),
                ('D', "You pull the right people in, take responsibility, and get everyone focused on the solution rather than who's at fault."),
            ]
        },
        {
            'id': 'q16',
            'section': 'DISC',
            'text': "Someone on your team is struggling with motivation. They're capable but disengaged. How do you get them back?",
            'options': [
                ('A', "You have a direct conversation about performance expectations and what needs to change — you don't let it drift."),
                ('B', "You genuinely invest in understanding what's going on personally. People don't check out for no reason."),
                ('C', "You give them a project that plays to their strengths — something they can own and succeed at quickly."),
                ('D', "You make sure they understand how their work connects to the bigger mission. Meaning drives engagement."),
            ]
        },
        {
            'id': 'q17',
            'section': 'DISC',
            'text': "You need to run an important team meeting. What does your ideal version of that meeting look like?",
            'options': [
                ('A', "Short, focused, outcomes-first. Everyone knows what they're walking away with and nothing goes longer than it needs to."),
                ('B', "Interactive and collaborative — room for real conversation, ideas on the table, energy in the room."),
                ('C', "Prepared agenda shared in advance, enough time to work through each item thoughtfully without rushing anyone."),
                ('D', "A structured discussion with time for every voice — especially the quieter ones who have important things to say."),
            ]
        },
        {
            'id': 'q18',
            'section': 'DISC',
            'text': "You receive a task with vague instructions and no clear definition of success. What do you do?",
            'options': [
                ('A', "You make assumptions, start working, and course-correct as you get feedback — waiting for clarity kills time."),
                ('B', "You ask enough questions to understand the intent, then figure out the best path to get there."),
                ('C', "You want specific parameters before you start — clarity upfront prevents rework later."),
                ('D', "You reach out to whoever assigned it, align on what success looks like, and then move forward with confidence."),
            ]
        },
        {
            'id': 'q19',
            'section': 'DISC',
            'text': "Your team just delivered an excellent result on a major project. How do you want that recognized?",
            'options': [
                ('A', "A clear acknowledgment from leadership that the work was excellent — public recognition that reflects the quality."),
                ('B', "The whole team celebrated together — not just an email, but a real moment where everyone feels the win."),
                ('C', "Personal acknowledgment from someone who actually understands what went into it — not generic praise."),
                ('D', "A note that captures the specifics — what was excellent, why it mattered, and what it means going forward."),
            ]
        },
        {
            'id': 'q20',
            'section': 'DISC',
            'text': "You're dealing with a difficult client who is being unreasonable and increasingly combative. How do you handle it?",
            'options': [
                ('A', "You address the behavior directly and professionally — you respect them as a client, but you won't be treated poorly."),
                ('B', "You de-escalate. Find the emotional root of what's driving their frustration and address that first."),
                ('C', "You stay calm and composed regardless of their tone — professionalism under pressure is how you earn their respect."),
                ('D', "You document everything, stick to the contract, and protect your team from taking the brunt of their behavior."),
            ]
        },
        {
            'id': 'q21',
            'section': 'DISC',
            'text': "You're facing a trade-off: deliver something good now, or take more time to make it great. The client hasn't specified. You:",
            'options': [
                ('A', "Deliver now — done beats perfect, and a fast result builds client confidence more than a delayed one."),
                ('B', "Ask the client. They might not care about the difference, or the delay might genuinely matter to them."),
                ('C', "Take the extra time. Your name is on the work and 'good enough' isn't what you're known for."),
                ('D', "Assess what 'great' actually requires and whether it's worth the additional time and cost before deciding."),
            ]
        },
        {
            'id': 'q22',
            'section': 'DISC',
            'text': "You're onboarding a new hire to your team. What do you prioritize in their first two weeks?",
            'options': [
                ('A', "Getting them into real work as quickly as possible — they'll learn more by doing than by shadowing."),
                ('B', "Making sure they feel genuinely welcomed — relationships are the foundation of everything else here."),
                ('C', "Thorough orientation to how things work — your systems, your standards, your expectations — before they touch anything."),
                ('D', "Introducing them to the right people and making sure they understand how their role connects to the bigger picture."),
            ]
        },
        {
            'id': 'q23',
            'section': 'DISC',
            'text': "You're under serious pressure — multiple things are blowing up at once, everyone wants something from you, and the day is running out. What does your honest behavior look like?",
            'options': [
                ('A', "You lock in. Noise gets filtered out, decisions get made fast, and you push through until it's done."),
                ('B', "You lean on your people. You communicate what's happening and distribute the load — you're not carrying it alone."),
                ('C', "You get quiet. You process internally, slow down before you speed up, and make sure you're not making reactive decisions."),
                ('D', "You triage hard. You make a list of everything, sort it by actual urgency, and work your way down systematically."),
            ]
        },
        {
            'id': 'q24',
            'section': 'DISC',
            'text': "At the end of a hard week, what does 'I did a good job this week' feel like to you?",
            'options': [
                ('A', "You hit your targets. You can point to specific results that moved things forward."),
                ('B', "You made a real difference for at least one person — a client, a teammate, someone who needed you."),
                ('C', "The team had a good week and you contributed to making that happen."),
                ('D', "You did the work right — thoroughly, carefully, with integrity. No corners cut."),
            ]
        },
        {
            'id': 'q25',
            'section': 'DISC',
            'text': "Mid-project, a client requests a significant scope change that wasn't in the original plan. How do you respond?",
            'options': [
                ('A', "You assess quickly, give them an honest answer about what it will take, and make a decision about how to proceed."),
                ('B', "You explore what they're really trying to solve — sometimes the actual need is different from the requested change."),
                ('C', "You review the contract, document the change request, and make sure the impact to timeline and budget is clearly agreed on before anything moves."),
                ('D', "You keep the relationship intact while being honest about what the change means — transparency keeps trust."),
            ]
        },
        {
            'id': 'q26',
            'section': 'DISC',
            'text': "You need to give someone direct critical feedback about their performance. This is a conversation you can't avoid. How do you approach it?",
            'options': [
                ('A', "Directly and without delay. You address the specific behavior, what it costs, and what needs to change. You don't soften it to the point it gets lost."),
                ('B', "You lead with genuine care for the person, create safety in the conversation, and then address the behavior specifically."),
                ('C', "You prepare thoroughly — specific examples, clear impact, and a defined expectation going forward. Nothing vague."),
                ('D', "You frame it as a growth conversation. You want them to leave motivated to improve, not demoralized."),
            ]
        },
        {
            'id': 'q27',
            'section': 'DISC',
            'text': "Describe your ideal workday — not what you think it should be, but what actually energizes you:",
            'options': [
                ('A', "A mix of strategic decisions, autonomous execution, and visible progress. You want to feel like you moved the ball forward on things that matter."),
                ('B', "Real conversations with people, collaboration on ideas, and the energy that comes from working shoulder-to-shoulder with a good team."),
                ('C', "A steady, focused day where you made meaningful progress on quality work without chaos or unnecessary interruptions."),
                ('D', "Deep focus time to think, research, and produce work you're genuinely proud of — where the standard was met or exceeded."),
            ]
        },
        {
            'id': 'q28',
            'section': 'DISC',
            'text': "You're representing PPS at a client meeting or industry event. What impression do you naturally make?",
            'options': [
                ('A', "Confident and decisive. You project credibility through directness and a clear command of the subject."),
                ('B', "Warm and engaging. You make real connections quickly and people remember the conversation more than the pitch."),
                ('C', "Calm and trustworthy. You listen more than you talk, and when you do speak, people feel like they're in good hands."),
                ('D', "Thorough and credible. You've done your homework and it shows — you can answer the hard questions."),
            ]
        },

        # ── MOTIVATORS/VALUES SCENARIOS ──
        {
            'id': 'q29',
            'section': 'Motivators',
            'text': "If everything at PPS was going perfectly — great team, strong work — which of these would matter most to you personally?",
            'options': [
                ('A', "Seeing real, measurable results from your work. Knowing the numbers moved because of what you did."),
                ('B', "Being part of a team where you genuinely trust and enjoy the people around you."),
                ('C', "Knowing your role, your compensation, and your future here are stable and predictable."),
                ('D', "Having significant ownership over how you do your job without needing constant approval."),
            ]
        },
        {
            'id': 'q30',
            'section': 'Motivators',
            'text': "You're choosing between two projects. Which do you pick?",
            'options': [
                ('A', "A project that will stretch your skills significantly — you'll probably struggle at first, but you'll be better for it."),
                ('B', "A high-visibility project with a clear deliverable where your contribution will be obvious and measurable."),
                ('C', "A project that directly helps a client through a difficult situation — the work genuinely matters to someone."),
                ('D', "A well-scoped project with a proven approach — lower risk, reliable execution, and a clean result."),
            ]
        },
        {
            'id': 'q31',
            'section': 'Motivators',
            'text': "At the end of the day, what makes work feel meaningful to you?",
            'options': [
                ('A', "Knowing that what you did made someone's life — a client's property, a resident's home — genuinely better."),
                ('B', "The feeling of finishing something well and knowing the outcome was better because of your involvement."),
                ('C', "The personal growth — you learned something, got better at something, or handled something you couldn't have handled before."),
                ('D', "The relationships — with your team, your clients, the people you work alongside every day."),
            ]
        },
        {
            'id': 'q32',
            'section': 'Motivators',
            'text': "Which form of recognition actually lands for you?",
            'options': [
                ('A', "Public acknowledgment — your name attached to a clear win, in front of the right people."),
                ('B', "Being trusted with more responsibility — someone thinks highly enough of you to give you harder things."),
                ('C', "Genuine appreciation from the people you worked with — a personal 'thank you' from a teammate or client."),
                ('D', "Being given more freedom in how you work — trusted to figure out your own best path."),
            ]
        },
        {
            'id': 'q33',
            'section': 'Motivators',
            'text': "If you're thinking five years ahead, which of these matters most to you at PPS?",
            'options': [
                ('A', "You've grown significantly — new skills, a broader role, a meaningfully different level of capability than you have today."),
                ('B', "You're in a stable, secure position — a clear role, fair compensation, and a company you trust to be here long-term."),
                ('C', "You've built a reputation for excellent work — and people know it. You've earned a track record."),
                ('D', "You have significant ownership over your domain — you're the one calling the shots in your area."),
            ]
        },
        {
            'id': 'q34',
            'section': 'Motivators',
            'text': "When you do your best work, what conditions are usually in place?",
            'options': [
                ('A', "You're working closely with people you like and respect — the collaboration is real, not just coordinated."),
                ('B', "You have clear ownership and latitude to decide how to get it done without constant check-ins."),
                ('C', "There's a clear standard to hit and you know what excellent looks like."),
                ('D', "You know the work matters — someone is counting on you and what you produce will genuinely help them."),
            ]
        },
        {
            'id': 'q35',
            'section': 'Motivators',
            'text': "What kind of day leaves you feeling energized rather than drained?",
            'options': [
                ('A', "A day where you finished something meaningful and can look back at what you produced with genuine satisfaction."),
                ('B', "A day where someone's problem got solved because of you — a client, a teammate, someone who needed what you had."),
                ('C', "A day where you figured something out — learned something new, cracked a hard problem, got a little better."),
                ('D', "A day where the team was clicking — good conversations, real collaboration, work that felt human."),
            ]
        },
        {
            'id': 'q36',
            'section': 'Motivators',
            'text': "What makes you stay at a company long-term?",
            'options': [
                ('A', "Stability — you know what you have, you trust the company to treat you fairly, and you don't have to worry about the future."),
                ('B', "The people — you've built real relationships and you'd miss them more than you'd miss anything else."),
                ('C', "Growth — you're getting better here. The day you stop growing is the day you start thinking about the door."),
                ('D', "The work — what you're doing matters, and you're genuinely proud of being part of it."),
            ]
        },
        {
            'id': 'q37',
            'section': 'Motivators',
            'text': "How do you personally define success in your career?",
            'options': [
                ('A', "A track record of hitting goals, delivering results, and building a reputation for getting things done."),
                ('B', "Knowing that your work genuinely helped people — that you made a real difference in the lives of clients or your community."),
                ('C', "A team that trusts you, values you, and that you'd go to bat for — and vice versa."),
                ('D', "The freedom to build your work the way you believe it should be built — your fingerprints on what you've created."),
            ]
        },
        {
            'id': 'q38',
            'section': 'Motivators',
            'text': "You've been doing the same task the same way for a year. It's efficient but not challenging. How do you feel about it?",
            'options': [
                ('A', "Comfortable. Routine means reliability — you're not wasting energy relearning, and the output is consistent."),
                ('B', "Restless. You're ready for the next level — this has become too easy and you want something harder."),
                ('C', "Willing, but you'd like to at least own the method — if you have to do the same thing, let it be your version."),
                ('D', "Fine with it as long as it's contributing to something meaningful. Routine work that matters is still worthwhile."),
            ]
        },
        {
            'id': 'q39',
            'section': 'Motivators',
            'text': "What kind of feedback actually makes you better?",
            'options': [
                ('A', "Specific, growth-oriented feedback — here's what you did well, here's the gap, here's how to close it."),
                ('B', "Feedback tied to outcomes — how did what I did affect the result? Give me the connection to performance."),
                ('C', "Consistent feedback over time — not just a review, but an ongoing conversation about how I'm doing and where I stand."),
                ('D', "Feedback that's personal and relational — not a performance review format, but a real conversation between people who trust each other."),
            ]
        },
        {
            'id': 'q40',
            'section': 'Motivators',
            'text': "If you had to protect one thing about how you work, what would it be?",
            'options': [
                ('A', "Your autonomy — the ability to decide how you approach your work without being micromanaged."),
                ('B', "Your relationships — the trust and connection you've built with the people around you."),
                ('C', "Your stability — knowing what to expect and not being surprised by constant change."),
                ('D', "Your purpose — knowing that what you're doing matters beyond just completing tasks."),
            ]
        },
        {
            'id': 'q41',
            'section': 'Motivators',
            'text': "When you go above and beyond what's expected, what's usually driving it?",
            'options': [
                ('A', "Personal pride — you set a standard for yourself and it's non-negotiable."),
                ('B', "The impact — someone's experience will be meaningfully better if you do this right."),
                ('C', "The team — you don't want to be the weak link and you care about pulling your weight for the people around you."),
                ('D', "Growth — doing more than expected is how you stretch yourself and improve faster."),
            ]
        },
        {
            'id': 'q42',
            'section': 'Motivators',
            'text': "What kind of work environment brings out your best?",
            'options': [
                ('A', "Stable and predictable — clear roles, consistent expectations, and an environment you can count on."),
                ('B', "Autonomous and flexible — you own your domain, set your own pace, and deliver on your terms."),
                ('C', "Collaborative and social — the energy of working with people who are invested in each other's success."),
                ('D', "Challenging and growth-oriented — the work is hard, the standards are high, and you're always getting better."),
            ]
        },
        {
            'id': 'q43',
            'section': 'Motivators',
            'text': "If you could change one thing about how you work at PPS, what would it be?",
            'options': [
                ('A', "More autonomy over my process — trust me to get there my way."),
                ('B', "More opportunities to develop — harder problems, bigger scope, real growth."),
                ('C', "More visibility into the impact of my work — I want to see how what I do connects to what clients experience."),
                ('D', "More predictability — clearer expectations and fewer surprises."),
            ]
        },
        {
            'id': 'q44',
            'section': 'Motivators',
            'text': "When you imagine yourself at your best — doing the work you were built to do — what does it look like?",
            'options': [
                ('A', "You're operating at the peak of your capability — hitting hard goals, building a legacy of excellent results."),
                ('B', "You're helping someone who genuinely needed you. The work you did made their situation meaningfully better."),
                ('C', "You're in a stable, trusted role where you're delivering consistent, excellent work for a company you believe in."),
                ('D', "You've grown into something bigger than you were — you're capable of things today that you couldn't do before."),
            ]
        },
    ]


if __name__ == '__main__':
    app.run(debug=True)

@app.route('/')
def root():
    from flask import redirect, url_for
    return redirect(url_for('login'))
