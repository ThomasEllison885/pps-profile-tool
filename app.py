import os
import json
import random
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import psycopg2
from psycopg2.extras import RealDictCursor
from hub_auth import configure_session, exchange_sso_code, hub_login_url, HUB_PUBLIC_URL

app = Flask(__name__)
_secret = os.environ.get('SECRET_KEY', '').strip()
if not _secret:
    raise RuntimeError(
        'SECRET_KEY env var is not set. In Render: Environment → add SECRET_KEY '
        '(or use generateValue in render.yaml).'
    )
app.secret_key = _secret
configure_session(app)

HUB_URL = os.environ.get('HUB_URL', HUB_PUBLIC_URL).rstrip('/')
INTERNAL_API_KEY_VAL = os.environ.get('INTERNAL_API_KEY', '').strip()
if not INTERNAL_API_KEY_VAL:
    print(
        'WARNING: INTERNAL_API_KEY is not set — profile tool will deploy but '
        'hub sign-in will fail until you add the same key used on pps-hub.'
    )

DATABASE_URL = os.environ.get('DATABASE_URL', '')


@app.route('/health')
def health():
    """Lightweight health check for Render; also surfaces missing auth config."""
    return jsonify({
        'ok': True,
        'hub_url': HUB_URL,
        'sso_configured': bool(INTERNAL_API_KEY_VAL),
        'database_configured': bool(DATABASE_URL),
    })


def _redirect_strip_code():
    parsed = urllib.parse.urlparse(request.url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs.pop('code', None)
    qs.pop('token', None)
    flat = [(k, v) for k, vals in qs.items() for v in vals]
    new_query = urllib.parse.urlencode(flat)
    target = request.path + (f'?{new_query}' if new_query else '')
    return redirect(target)


def _ensure_auth():
    code = (request.args.get('code') or request.args.get('token') or '').strip()
    if code and not session.get('authenticated'):
        user_info = exchange_sso_code(code)
        if user_info:
            session.permanent = True
            session['authenticated'] = True
            session['user_key'] = user_info.get('user_key', '')
            session['display_name'] = user_info.get('display_name', '')
            session['role'] = user_info.get('role', '')
            if user_info.get('role') == 'admin':
                session['admin'] = True
            return _redirect_strip_code()
    if not session.get('authenticated'):
        return redirect(hub_login_url(request.url))
    return None


def _is_admin():
    return session.get('admin') or session.get('role') == 'admin'

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


# ── QUESTIONS ──────────────────────────────────────────────────────────────────

def get_raw_questions():
    """
    Returns questions with options as dicts {text, scores} so we can shuffle
    order while keeping scoring attached to the text, not the letter.
    """
    return [
        # ── PART 1: BEHAVIORAL STYLE (DISC) ──
        {
            'id': 'q1', 'section': 'Behavioral Style',
            'text': "It's Thursday afternoon and your manager just moved a major deadline to Friday morning. You still have a full day's worth of work left. How do you actually respond?",
            'options': [
                {'text': "You immediately cut out anything non-essential, set a hard plan, and start executing. You'll figure out the rest when you get there.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
                {'text': "You send a message to the team letting everyone know what's happening and rallying anyone who can help get it done together.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You take a breath, reorganize your task list carefully, and work steadily through the night if needed — no shortcuts.", 'scores': {'D': 1, 'I': 0, 'S': 3, 'C': 0}},
                {'text': "You flag the risk back to your manager with a clear summary of what can realistically be finished by morning, and what can't.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
            ]
        },
        {
            'id': 'q2', 'section': 'Behavioral Style',
            'text': "A new team member joins who clearly has experience but seems hesitant to speak up in group settings. You notice this in their first week. What do you do?",
            'options': [
                {'text': "You give them space to warm up on their own — you don't want to put them on the spot.", 'scores': {'D': 0, 'I': 0, 'S': 3, 'C': 1}},
                {'text': "You find a natural moment to pull them aside and ask what kind of environment they work best in.", 'scores': {'D': 0, 'I': 1, 'S': 2, 'C': 3}},
                {'text': "You put them on a small piece of a project right away so they can prove themselves and build confidence through results.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
                {'text': "You personally introduce them around, make sure they feel included in conversations, and keep the energy welcoming.", 'scores': {'D': 1, 'I': 3, 'S': 0, 'C': 0}},
            ]
        },
        {
            'id': 'q3', 'section': 'Behavioral Style',
            'text': "A coworker keeps missing deadlines that directly affect your work. You've let it slide twice. It happens again. How do you handle it?",
            'options': [
                {'text': "You document the pattern and bring it to your manager with specifics — dates, impacts, and a proposed solution.", 'scores': {'D': 1, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "You try to understand what's going on in their world first — maybe there's something affecting their performance you don't know about.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 0}},
                {'text': "You address it directly and privately — clearly, not harshly. You tell them what you need and what happens if it continues.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
                {'text': "You have an honest but casual conversation and try to find a system that works better for both of you going forward.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
            ]
        },
        {
            'id': 'q4', 'section': 'Behavioral Style',
            'text': "You're put in charge of a cross-functional project with a team of five people, none of whom report to you. How do you lead?",
            'options': [
                {'text': "You start by having one-on-ones with each person to understand their working style before deciding how to structure things.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 0}},
                {'text': "You build a detailed project plan, assign tasks based on each person's strengths, and create a shared tracker so nothing falls through the cracks.", 'scores': {'D': 1, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "You define roles and expectations up front, establish a clear timeline, and hold weekly check-ins to make sure everyone stays on track.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
                {'text': "You call a kickoff meeting to get energy up, make sure everyone knows why the project matters, and keep the momentum high throughout.", 'scores': {'D': 0, 'I': 3, 'S': 0, 'C': 0}},
            ]
        },
        {
            'id': 'q5', 'section': 'Behavioral Style',
            'text': "You've been working a certain way for two years. Your company announces a major process change that affects your entire workflow — effective immediately. Your honest first reaction is:",
            'options': [
                {'text': "Caution. You want to understand the new process thoroughly before committing to it so you don't make mistakes.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "Excitement. Change means new opportunity — you're already thinking about how to leverage it.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
                {'text': "Frustration. You'll adapt, but changing something that was working fine wastes energy and creates unnecessary disruption.", 'scores': {'D': 1, 'I': 0, 'S': 3, 'C': 0}},
                {'text': "Curiosity. You want to understand why the change is happening before you decide how you feel about it.", 'scores': {'D': 0, 'I': 3, 'S': 0, 'C': 1}},
            ]
        },
        {
            'id': 'q6', 'section': 'Behavioral Style',
            'text': "You're presenting a proposal to an important client who is skeptical and asking hard questions. How do you show up?",
            'options': [
                {'text': "Warm and engaging — you make them feel heard, build a real connection, and use their skepticism as an opportunity to earn trust.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "Precise and prepared — you have data for every concern and you walk them through the logic methodically.", 'scores': {'D': 1, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "Steady and reassuring — you project calm confidence and make sure they feel like they're in good hands.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 0}},
                {'text': "Confident and direct — you've done the work, you know the answer, and you're not going to hedge.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
            ]
        },
        {
            'id': 'q7', 'section': 'Behavioral Style',
            'text': "Your manager gives you critical feedback on a project you put real effort into. They say your approach missed the mark. Your gut reaction is:",
            'options': [
                {'text': "You feel it personally at first, but push through it — you genuinely want to improve and use it as fuel.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You listen fully, thank them for the feedback, and reflect on it privately before responding.", 'scores': {'D': 0, 'I': 0, 'S': 3, 'C': 1}},
                {'text': "You want to understand their reasoning — if you agree, you act on it; if you don't, you'll respectfully push back with evidence.", 'scores': {'D': 1, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "You ask for specifics immediately and start mentally rebuilding — you'd rather know than not know.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
            ]
        },
        {
            'id': 'q8', 'section': 'Behavioral Style',
            'text': "Your team just hit a major milestone — a big win by anyone's measure. How do you want to celebrate?",
            'options': [
                {'text': "A written recognition that captures what was achieved and how — something tangible that reflects the quality of the work.", 'scores': {'D': 1, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "Acknowledge it, mark the moment, and then get focused on what's next — winning is good but it shouldn't slow momentum.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 0}},
                {'text': "A genuine, personal acknowledgment of each person's contribution — a team dinner or something where everyone feels seen.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 0}},
                {'text': "Make it a real event. Bring the team together, share the story, make people feel the weight of what they accomplished.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
            ]
        },
        {
            'id': 'q9', 'section': 'Behavioral Style',
            'text': "You're handed a problem that nobody on your team has solved before. There's no playbook. How do you approach it?",
            'options': [
                {'text': "You research everything you can find, map out the variables, and build a solution based on evidence.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "You get the right people in a room and work through it together — someone has encountered something similar before.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You start moving immediately — test something, see what happens, and iterate from there.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
                {'text': "You think it through on your own first, build a hypothesis, and then pressure-test it before committing.", 'scores': {'D': 1, 'I': 0, 'S': 3, 'C': 0}},
            ]
        },
        {
            'id': 'q10', 'section': 'Behavioral Style',
            'text': "You strongly disagree with a decision your manager just made. You think it's the wrong call. What do you do?",
            'options': [
                {'text': "You share your perspective once clearly, and if they still go the other direction, you commit and execute.", 'scores': {'D': 1, 'I': 0, 'S': 3, 'C': 0}},
                {'text': "You build the strongest case you can with data and present it. If they still disagree, you document your concern and move forward.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "You say something — respectfully but directly. You can't pretend to agree with something you think is wrong.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
                {'text': "You ask for a conversation, share your concerns with context, and try to understand their thinking before pushing back.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
            ]
        },
        {
            'id': 'q11', 'section': 'Behavioral Style',
            'text': "You're planning a complex job with a lot of moving pieces, multiple vendors, and a hard deadline. Where do you start?",
            'options': [
                {'text': "You pull everyone together early to align on scope, roles, and timeline before anyone starts moving independently.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You identify the critical path — what absolutely cannot be late — and build your plan around protecting those things.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
                {'text': "You assign clear ownership to each workstream and set up a system to track progress without needing constant check-ins.", 'scores': {'D': 1, 'I': 0, 'S': 3, 'C': 0}},
                {'text': "You build a comprehensive plan with every dependency mapped before you start — surprises are the enemy.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
            ]
        },
        {
            'id': 'q12', 'section': 'Behavioral Style',
            'text': "A project you're running has stalled. Nobody is moving, momentum is dead, and the deadline is still real. What do you do?",
            'options': [
                {'text': "You diagnose the root cause first — what specifically is stalling and why — then build a recovery plan.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "You energize the team — get people together, reset the vision, remind them why this matters, rebuild momentum through people.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You have quiet conversations with key people, understand what's blocking them, and remove obstacles systematically.", 'scores': {'D': 1, 'I': 1, 'S': 3, 'C': 0}},
                {'text': "You call it out directly — name the problem, reassign if needed, and force momentum back into the work.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 0}},
            ]
        },
        {
            'id': 'q13', 'section': 'Behavioral Style',
            'text': "Your company rolls out a new process for something you've been doing your own way for years. Your way works. The new way is unproven. How do you handle it?",
            'options': [
                {'text': "You give it a fair shot — change can be good, you stay open and follow the new process with full effort.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You raise your concerns through the right channel but adapt in the meantime — you're not going to fight every battle.", 'scores': {'D': 1, 'I': 0, 'S': 3, 'C': 0}},
                {'text': "You implement it as directed, track the results, and bring data back if the old way was clearly better.", 'scores': {'D': 0, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "You ask the questions nobody else is asking about why this change was made and what problem it's actually solving.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 1}},
            ]
        },
        {
            'id': 'q14', 'section': 'Behavioral Style',
            'text': "You have a full day of deep, focused work ahead. Your ideal setup is:",
            'options': [
                {'text': "Near your team, even if you're not actively collaborating — energy in the room keeps you moving.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "Wherever you can get things done fastest — environment matters less than having a clear list and the authority to act on it.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 0}},
                {'text': "Alone — door closed, no interruptions, headphones in. You do your best thinking without other people's noise.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "In a space with low-level ambient activity — enough to keep energy up without being pulled into conversations.", 'scores': {'D': 1, 'I': 1, 'S': 3, 'C': 0}},
            ]
        },
        {
            'id': 'q15', 'section': 'Behavioral Style',
            'text': "You make a high-stakes mistake that affects a client. It was your call and it didn't go right. What happens next?",
            'options': [
                {'text': "You pull the right people in, take responsibility, and get everyone focused on the solution rather than who's at fault.", 'scores': {'D': 1, 'I': 3, 'S': 0, 'C': 0}},
                {'text': "You analyze exactly what went wrong so you can prevent it from ever happening again — the fix and the lesson matter equally.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "You make sure the client knows they're not alone in it — you communicate clearly and keep them informed every step of the way.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 0}},
                {'text': "You own it immediately, go directly to the client, and focus every ounce of energy on fixing it — no excuses.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 0}},
            ]
        },
        {
            'id': 'q16', 'section': 'Behavioral Style',
            'text': "Someone on your team is struggling with motivation. They're capable but disengaged. How do you get them back?",
            'options': [
                {'text': "You make sure they understand how their work connects to the bigger mission — meaning drives engagement.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 0}},
                {'text': "You have a direct conversation about performance expectations and what needs to change — you don't let it drift.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
                {'text': "You give them a project that plays to their strengths — something they can own and succeed at quickly.", 'scores': {'D': 1, 'I': 3, 'S': 0, 'C': 0}},
                {'text': "You genuinely invest in understanding what's going on personally — people don't check out for no reason.", 'scores': {'D': 0, 'I': 0, 'S': 3, 'C': 1}},
            ]
        },
        {
            'id': 'q17', 'section': 'Behavioral Style',
            'text': "You need to run an important team meeting. What does your ideal version of that meeting look like?",
            'options': [
                {'text': "A structured discussion with time for every voice — especially the quieter ones who have important things to say.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 1}},
                {'text': "Prepared agenda shared in advance, enough time to work through each item thoughtfully without rushing anyone.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "Short, focused, outcomes-first — everyone knows what they're walking away with and nothing goes longer than it needs to.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
                {'text': "Interactive and collaborative — room for real conversation, ideas on the table, energy in the room.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
            ]
        },
        {
            'id': 'q18', 'section': 'Behavioral Style',
            'text': "You receive a task with vague instructions and no clear definition of success. What do you do?",
            'options': [
                {'text': "You want specific parameters before you start — clarity upfront prevents rework later.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "You reach out to whoever assigned it, align on what success looks like, and then move forward with confidence.", 'scores': {'D': 1, 'I': 3, 'S': 0, 'C': 0}},
                {'text': "You ask enough questions to understand the intent, then figure out the best path to get there.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 1}},
                {'text': "You make assumptions, start working, and course-correct as you get feedback — waiting for clarity kills time.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 0}},
            ]
        },
        {
            'id': 'q19', 'section': 'Behavioral Style',
            'text': "Your team just delivered an excellent result on a major project. How do you want that recognized?",
            'options': [
                {'text': "A note that captures the specifics — what was excellent, why it mattered, and what it means going forward.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "Personal acknowledgment from someone who actually understands what went into it — not generic praise.", 'scores': {'D': 1, 'I': 0, 'S': 3, 'C': 0}},
                {'text': "The whole team celebrated together — not just an email, but a real moment where everyone feels the win.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "A clear acknowledgment from leadership that the work was excellent — public recognition that reflects the quality.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
            ]
        },
        {
            'id': 'q20', 'section': 'Behavioral Style',
            'text': "You're dealing with a difficult client who is being unreasonable and increasingly combative. How do you handle it?",
            'options': [
                {'text': "You de-escalate — find the emotional root of what's driving their frustration and address that first.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You stay calm and composed regardless of their tone — professionalism under pressure is how you earn their respect.", 'scores': {'D': 0, 'I': 0, 'S': 3, 'C': 1}},
                {'text': "You document everything, stick to the contract, and protect your team from taking the brunt of their behavior.", 'scores': {'D': 1, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "You address the behavior directly and professionally — you respect them as a client, but you won't be treated poorly.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
            ]
        },
        {
            'id': 'q21', 'section': 'Behavioral Style',
            'text': "You're facing a trade-off: deliver something good now, or take more time to make it great. The client hasn't specified.",
            'options': [
                {'text': "Take the extra time — your name is on the work and 'good enough' isn't what you're known for.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "Assess what 'great' actually requires and whether it's worth the additional time and cost before deciding.", 'scores': {'D': 1, 'I': 1, 'S': 0, 'C': 3}},
                {'text': "Ask the client — they might not care about the difference, or the delay might genuinely matter to them.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "Deliver now — done beats perfect, and a fast result builds client confidence more than a delayed one.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 0}},
            ]
        },
        {
            'id': 'q22', 'section': 'Behavioral Style',
            'text': "You're onboarding a new hire to your team. What do you prioritize in their first two weeks?",
            'options': [
                {'text': "Making sure they feel genuinely welcomed — relationships are the foundation of everything else here.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "Getting them into real work as quickly as possible — they'll learn more by doing than by shadowing.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 0}},
                {'text': "Thorough orientation to how things work — your systems, your standards, your expectations — before they touch anything.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "Introducing them to the right people and making sure they understand how their role connects to the bigger picture.", 'scores': {'D': 1, 'I': 1, 'S': 3, 'C': 0}},
            ]
        },
        {
            'id': 'q23', 'section': 'Behavioral Style',
            'text': "You're under serious pressure — multiple things are blowing up at once. What does your honest behavior look like?",
            'options': [
                {'text': "You triage hard — make a list of everything, sort by actual urgency, and work your way down systematically.", 'scores': {'D': 1, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "You lean on your people — communicate what's happening and distribute the load.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You lock in — noise gets filtered out, decisions get made fast, and you push through until it's done.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 0}},
                {'text': "You get quiet — process internally, slow down before you speed up, make sure you're not making reactive decisions.", 'scores': {'D': 0, 'I': 0, 'S': 3, 'C': 1}},
            ]
        },
        {
            'id': 'q24', 'section': 'Behavioral Style',
            'text': "At the end of a hard week, what does 'I did a good job this week' feel like to you?",
            'options': [
                {'text': "The team had a good week and you contributed to making that happen.", 'scores': {'D': 0, 'I': 1, 'S': 3, 'C': 0}},
                {'text': "You hit your targets — you can point to specific results that moved things forward.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
                {'text': "You did the work right — thoroughly, carefully, with integrity. No corners cut.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "You made a real difference for at least one person — a client, a teammate, someone who needed you.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
            ]
        },
        {
            'id': 'q25', 'section': 'Behavioral Style',
            'text': "Mid-project, a client requests a significant scope change that wasn't in the original plan. How do you respond?",
            'options': [
                {'text': "You review the contract, document the change request, and make sure the impact to timeline and budget is clearly agreed on before anything moves.", 'scores': {'D': 0, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "You keep the relationship intact while being honest about what the change means — transparency keeps trust.", 'scores': {'D': 0, 'I': 2, 'S': 3, 'C': 0}},
                {'text': "You assess quickly, give them an honest answer about what it will take, and make a decision about how to proceed.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
                {'text': "You explore what they're really trying to solve — sometimes the actual need is different from the requested change.", 'scores': {'D': 1, 'I': 3, 'S': 0, 'C': 1}},
            ]
        },
        {
            'id': 'q26', 'section': 'Behavioral Style',
            'text': "You need to give someone direct critical feedback about their performance. How do you approach it?",
            'options': [
                {'text': "You lead with genuine care for the person, create safety in the conversation, and then address the behavior specifically.", 'scores': {'D': 0, 'I': 2, 'S': 3, 'C': 0}},
                {'text': "You frame it as a growth conversation — you want them to leave motivated to improve, not demoralized.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "You prepare thoroughly — specific examples, clear impact, and a defined expectation going forward. Nothing vague.", 'scores': {'D': 1, 'I': 0, 'S': 0, 'C': 3}},
                {'text': "Directly and without delay — address the specific behavior, what it costs, and what needs to change.", 'scores': {'D': 3, 'I': 0, 'S': 0, 'C': 1}},
            ]
        },
        {
            'id': 'q27', 'section': 'Behavioral Style',
            'text': "Describe your ideal workday — not what you think it should be, but what actually energizes you:",
            'options': [
                {'text': "Deep focus time to think, research, and produce work you're genuinely proud of — where the standard was met or exceeded.", 'scores': {'D': 0, 'I': 0, 'S': 1, 'C': 3}},
                {'text': "Real conversations with people, collaboration on ideas, and the energy that comes from working shoulder-to-shoulder.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "A mix of strategic decisions, autonomous execution, and visible progress — you moved the ball forward on things that matter.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
                {'text': "A steady, focused day where you made meaningful progress on quality work without chaos or unnecessary interruptions.", 'scores': {'D': 1, 'I': 0, 'S': 3, 'C': 1}},
            ]
        },
        {
            'id': 'q28', 'section': 'Behavioral Style',
            'text': "You're representing PPS at a client meeting or industry event. What impression do you naturally make?",
            'options': [
                {'text': "Warm and engaging — you make real connections quickly and people remember the conversation more than the pitch.", 'scores': {'D': 0, 'I': 3, 'S': 1, 'C': 0}},
                {'text': "Thorough and credible — you've done your homework and it shows. You can answer the hard questions.", 'scores': {'D': 0, 'I': 1, 'S': 0, 'C': 3}},
                {'text': "Confident and decisive — you project credibility through directness and a clear command of the subject.", 'scores': {'D': 3, 'I': 1, 'S': 0, 'C': 0}},
                {'text': "Calm and trustworthy — you listen more than you talk, and when you do speak, people feel like they're in good hands.", 'scores': {'D': 0, 'I': 0, 'S': 3, 'C': 1}},
            ]
        },

        # ── PART 2: MOTIVATORS & VALUES ──
        {
            'id': 'q29', 'section': 'Motivators & Values',
            'text': "If everything at PPS was going perfectly — great team, strong work — which of these would matter most to you personally?",
            'options': [
                {'text': "Having significant ownership over how you do your job without needing constant approval.", 'scores': {'Autonomy': 3}},
                {'text': "Knowing your role, your compensation, and your future here are stable and predictable.", 'scores': {'Security': 3}},
                {'text': "Seeing real, measurable results from your work — knowing the numbers moved because of what you did.", 'scores': {'Achievement': 3}},
                {'text': "Being part of a team where you genuinely trust and enjoy the people around you.", 'scores': {'Affiliation': 3}},
            ]
        },
        {
            'id': 'q30', 'section': 'Motivators & Values',
            'text': "You're choosing between two projects. Which do you pick?",
            'options': [
                {'text': "A project that directly helps a client through a difficult situation — the work genuinely matters to someone.", 'scores': {'Service': 3}},
                {'text': "A well-scoped project with a proven approach — lower risk, reliable execution, and a clean result.", 'scores': {'Security': 3}},
                {'text': "A high-visibility project with a clear deliverable where your contribution will be obvious and measurable.", 'scores': {'Achievement': 2}},
                {'text': "A project that will stretch your skills significantly — you'll probably struggle at first, but you'll be better for it.", 'scores': {'Growth': 3}},
            ]
        },
        {
            'id': 'q31', 'section': 'Motivators & Values',
            'text': "At the end of the day, what makes work feel meaningful to you?",
            'options': [
                {'text': "The relationships — with your team, your clients, the people you work alongside every day.", 'scores': {'Affiliation': 3}},
                {'text': "The personal growth — you learned something, got better at something, or handled something you couldn't have before.", 'scores': {'Growth': 2}},
                {'text': "The feeling of finishing something well and knowing the outcome was better because of your involvement.", 'scores': {'Achievement': 2}},
                {'text': "Knowing that what you did made someone's life — a client's property, a resident's home — genuinely better.", 'scores': {'Service': 3}},
            ]
        },
        {
            'id': 'q32', 'section': 'Motivators & Values',
            'text': "Which form of recognition actually lands for you?",
            'options': [
                {'text': "Genuine appreciation from the people you worked with — a personal 'thank you' from a teammate or client.", 'scores': {'Service': 2}},
                {'text': "Being given more freedom in how you work — trusted to figure out your own best path.", 'scores': {'Autonomy': 3}},
                {'text': "Public acknowledgment — your name attached to a clear win, in front of the right people.", 'scores': {'Achievement': 3}},
                {'text': "Being trusted with more responsibility — someone thinks highly enough of you to give you harder things.", 'scores': {'Growth': 2}},
            ]
        },
        {
            'id': 'q33', 'section': 'Motivators & Values',
            'text': "If you're thinking five years ahead, which of these matters most to you at PPS?",
            'options': [
                {'text': "You have significant ownership over your domain — you're the one calling the shots in your area.", 'scores': {'Autonomy': 2}},
                {'text': "You're in a stable, secure position — a clear role, fair compensation, and a company you trust to be here long-term.", 'scores': {'Security': 3}},
                {'text': "You've built a reputation for excellent work — people know it, you've earned a track record.", 'scores': {'Achievement': 2}},
                {'text': "You've grown significantly — new skills, a broader role, a meaningfully different level of capability than today.", 'scores': {'Growth': 3}},
            ]
        },
        {
            'id': 'q34', 'section': 'Motivators & Values',
            'text': "When you do your best work, what conditions are usually in place?",
            'options': [
                {'text': "You know the work matters — someone is counting on you and what you produce will genuinely help them.", 'scores': {'Service': 2}},
                {'text': "You have clear ownership and latitude to decide how to get it done without constant check-ins.", 'scores': {'Autonomy': 3}},
                {'text': "There's a clear standard to hit and you know what excellent looks like.", 'scores': {'Achievement': 1}},
                {'text': "You're working closely with people you like and respect — the collaboration is real, not just coordinated.", 'scores': {'Affiliation': 3}},
            ]
        },
        {
            'id': 'q35', 'section': 'Motivators & Values',
            'text': "What kind of day leaves you feeling energized rather than drained?",
            'options': [
                {'text': "A day where the team was clicking — good conversations, real collaboration, work that felt human.", 'scores': {'Affiliation': 2}},
                {'text': "A day where someone's problem got solved because of you — a client, a teammate, someone who needed what you had.", 'scores': {'Service': 3}},
                {'text': "A day where you finished something meaningful and can look back at what you produced with genuine satisfaction.", 'scores': {'Achievement': 3}},
                {'text': "A day where you figured something out — learned something new, cracked a hard problem, got a little better.", 'scores': {'Growth': 2}},
            ]
        },
        {
            'id': 'q36', 'section': 'Motivators & Values',
            'text': "What makes you stay at a company long-term?",
            'options': [
                {'text': "The work — what you're doing matters, and you're genuinely proud of being part of it.", 'scores': {'Service': 2}},
                {'text': "Growth — you're getting better here. The day you stop growing is the day you start thinking about the door.", 'scores': {'Growth': 3}},
                {'text': "The people — you've built real relationships and you'd miss them more than you'd miss anything else.", 'scores': {'Affiliation': 3}},
                {'text': "Stability — you know what you have, you trust the company to treat you fairly, and you don't have to worry about the future.", 'scores': {'Security': 3}},
            ]
        },
        {
            'id': 'q37', 'section': 'Motivators & Values',
            'text': "How do you personally define success in your career?",
            'options': [
                {'text': "The freedom to build your work the way you believe it should be built — your fingerprints on what you've created.", 'scores': {'Autonomy': 2}},
                {'text': "A team that trusts you, values you, and that you'd go to bat for — and vice versa.", 'scores': {'Affiliation': 2}},
                {'text': "Knowing that your work genuinely helped people — a real difference in the lives of clients or your community.", 'scores': {'Service': 3}},
                {'text': "A track record of hitting goals, delivering results, and building a reputation for getting things done.", 'scores': {'Achievement': 3}},
            ]
        },
        {
            'id': 'q38', 'section': 'Motivators & Values',
            'text': "You've been doing the same task the same way for a year. It's efficient but not challenging. How do you feel about it?",
            'options': [
                {'text': "Fine with it as long as it's contributing to something meaningful — routine work that matters is still worthwhile.", 'scores': {'Service': 2}},
                {'text': "Willing, but you'd like to at least own the method — if you have to do the same thing, let it be your version.", 'scores': {'Autonomy': 2}},
                {'text': "Comfortable — routine means reliability, you're not wasting energy relearning, and the output is consistent.", 'scores': {'Security': 3}},
                {'text': "Restless — you're ready for the next level. This has become too easy and you want something harder.", 'scores': {'Growth': 3}},
            ]
        },
        {
            'id': 'q39', 'section': 'Motivators & Values',
            'text': "What kind of feedback actually makes you better?",
            'options': [
                {'text': "Feedback tied to outcomes — how did what I do affect the result? Give me the connection to performance.", 'scores': {'Achievement': 2}},
                {'text': "Feedback that's personal and relational — not a performance review format, but a real conversation between people who trust each other.", 'scores': {'Affiliation': 3}},
                {'text': "Specific, growth-oriented feedback — here's what you did well, here's the gap, here's how to close it.", 'scores': {'Growth': 3}},
                {'text': "Consistent feedback over time — not just a review, but an ongoing conversation about how I'm doing and where I stand.", 'scores': {'Security': 2}},
            ]
        },
        {
            'id': 'q40', 'section': 'Motivators & Values',
            'text': "If you had to protect one thing about how you work, what would it be?",
            'options': [
                {'text': "Your purpose — knowing that what you're doing matters beyond just completing tasks.", 'scores': {'Service': 2}},
                {'text': "Your stability — knowing what to expect and not being surprised by constant change.", 'scores': {'Security': 2}},
                {'text': "Your autonomy — the ability to decide how you approach your work without being micromanaged.", 'scores': {'Autonomy': 3}},
                {'text': "Your relationships — the trust and connection you've built with the people around you.", 'scores': {'Affiliation': 3}},
            ]
        },
        {
            'id': 'q41', 'section': 'Motivators & Values',
            'text': "When you go above and beyond what's expected, what's usually driving it?",
            'options': [
                {'text': "Growth — doing more than expected is how you stretch yourself and improve faster.", 'scores': {'Growth': 2}},
                {'text': "The impact — someone's experience will be meaningfully better if you do this right.", 'scores': {'Service': 3}},
                {'text': "Personal pride — you set a standard for yourself and it's non-negotiable.", 'scores': {'Achievement': 3}},
                {'text': "The team — you don't want to be the weak link and you care about pulling your weight for the people around you.", 'scores': {'Affiliation': 2}},
            ]
        },
        {
            'id': 'q42', 'section': 'Motivators & Values',
            'text': "What kind of work environment brings out your best?",
            'options': [
                {'text': "Collaborative and social — the energy of working with people who are invested in each other's success.", 'scores': {'Affiliation': 2}},
                {'text': "Challenging and growth-oriented — the work is hard, the standards are high, and you're always getting better.", 'scores': {'Growth': 2}},
                {'text': "Autonomous and flexible — you own your domain, set your own pace, and deliver on your terms.", 'scores': {'Autonomy': 3}},
                {'text': "Stable and predictable — clear roles, consistent expectations, and an environment you can count on.", 'scores': {'Security': 3}},
            ]
        },
        {
            'id': 'q43', 'section': 'Motivators & Values',
            'text': "If you could change one thing about how you work at PPS, what would it be?",
            'options': [
                {'text': "More predictability — clearer expectations and fewer surprises.", 'scores': {'Security': 1}},
                {'text': "More visibility into the impact of my work — I want to see how what I do connects to what clients experience.", 'scores': {'Service': 2}},
                {'text': "More autonomy over my process — trust me to get there my way.", 'scores': {'Autonomy': 3}},
                {'text': "More opportunities to develop — harder problems, bigger scope, real growth.", 'scores': {'Growth': 3}},
            ]
        },
        {
            'id': 'q44', 'section': 'Motivators & Values',
            'text': "When you imagine yourself at your best — doing the work you were built to do — what does it look like?",
            'options': [
                {'text': "You've grown into something bigger than you were — you're capable of things today that you couldn't do before.", 'scores': {'Growth': 3}},
                {'text': "You're helping someone who genuinely needed you — the work you did made their situation meaningfully better.", 'scores': {'Service': 3}},
                {'text': "You're in a stable, trusted role where you're delivering consistent, excellent work for a company you believe in.", 'scores': {'Security': 2}},
                {'text': "You're operating at the peak of your capability — hitting hard goals, building a legacy of excellent results.", 'scores': {'Achievement': 3}},
            ]
        },
    ]


def get_questions_shuffled(seed=None):
    """Return questions with answer options shuffled, using a seed for consistency per session."""
    questions = get_raw_questions()
    rng = random.Random(seed)
    result = []
    for q in questions:
        opts = list(q['options'])
        rng.shuffle(opts)
        # Assign letters A-D to shuffled options
        letters = ['A', 'B', 'C', 'D']
        labeled = [(letters[i], opts[i]) for i in range(len(opts))]
        result.append({
            'id': q['id'],
            'section': q['section'],
            'text': q['text'],
            'options': labeled,  # (letter, {text, scores})
        })
    return result


def score_responses(answers, questions):
    """
    answers: { 'q1': 'B', 'q2': 'A', ... }
    questions: shuffled question list with scoring attached to each option
    """
    disc = {'D': 0, 'I': 0, 'S': 0, 'C': 0}
    motiv = {'Achievement': 0, 'Affiliation': 0, 'Security': 0, 'Autonomy': 0, 'Service': 0, 'Growth': 0}

    q_map = {q['id']: q for q in questions}

    for q_id, chosen_letter in answers.items():
        if q_id not in q_map:
            continue
        q = q_map[q_id]
        for letter, opt in q['options']:
            if letter == chosen_letter:
                for dim, val in opt['scores'].items():
                    if dim in disc:
                        disc[dim] += val
                    elif dim in motiv:
                        motiv[dim] += val
                break

    # Normalize to 0-100
    disc_max = 28 * 3
    motiv_max = 16 * 3
    disc_norm = {k: min(100, round((v / disc_max) * 100)) for k, v in disc.items()}
    motiv_norm = {k: min(100, round((v / motiv_max) * 100)) for k, v in motiv.items()}
    return disc_norm, motiv_norm


def determine_profile(disc, motiv):
    primary_disc = max(disc, key=disc.get)
    sorted_disc = sorted(disc.items(), key=lambda x: x[1], reverse=True)
    secondary_disc = sorted_disc[1][0] if sorted_disc[1][1] >= 35 else None
    primary_motiv = max(motiv, key=motiv.get)
    return primary_disc, secondary_disc, primary_motiv


def get_character_match(primary_disc, secondary_disc, primary_motiv):
    characters = {
        ('D', 'I'): ('Harvey Specter', 'Suits', 'Commanding and charismatic — you push hard for results but know how to work a room. You lead from the front and expect the same from everyone around you.'),
        ('D', 'C'): ('Frank Underwood', 'House of Cards', "Methodical, strategic, and relentlessly driven. You think several moves ahead and execute with precision. You don't need people to like you — you need them to respect you."),
        ('D', 'S'): ('Ned Stark', 'Game of Thrones', "You lead with conviction and protect what matters. Decisive under pressure, you never waver on your values even when it costs you."),
        ('D', None): ('Miranda Priestly', 'The Devil Wears Prada', "Razor-focused and results-driven. You set the standard, expect excellence, and don't waste time explaining yourself twice."),
        ('I', 'D'): ('Tony Stark', 'Iron Man / Avengers', "Brilliant, bold, and impossible to ignore. You thrive in the spotlight and push everyone around you to think bigger."),
        ('I', 'S'): ('Ted Lasso', 'Ted Lasso', "Enthusiastic, caring, and relentlessly optimistic. You bring people together and make them believe in the mission as much as you do."),
        ('I', 'C'): ('Sherlock Holmes', 'Sherlock (BBC)', "Exceptionally perceptive and expressive — you can read a room and a problem simultaneously. Your confidence can read as arrogance, but your accuracy usually proves you right."),
        ('I', None): ('Leslie Knope', 'Parks and Recreation', "Your energy is contagious and your heart is always in the right place. You want everyone to love being here — and most of the time, they do."),
        ('S', 'I'): ('Ted Lasso', 'Ted Lasso', "Warm, steady, and deeply committed to the people around you. You lead through trust and your team would run through a wall for you."),
        ('S', 'C'): ('Samwise Gamgee', 'The Lord of the Rings', "The most dependable person in any room. You're not chasing the spotlight — you're making sure the mission gets done and nobody gets left behind."),
        ('S', 'D'): ('Captain America', 'Marvel / Avengers', "Principled, loyal, and steady under fire. You lead by example and hold the line even when it's hard. People follow you because they trust you completely."),
        ('S', None): ('Meredith Grey', "Grey's Anatomy", "Calm in chaos, loyal under pressure. You process deeply before responding, and when you commit to someone or something, it's total."),
        ('C', 'D'): ('Walter White', 'Breaking Bad', "Meticulous and driven — a dangerous combination when pointed in the right direction. You don't guess; you know. And you don't stop until it's right."),
        ('C', 'I'): ('Hermione Granger', 'Harry Potter', "Precise, prepared, and surprisingly warm once you trust someone. You've done the research others skipped and you're not shy about it."),
        ('C', 'S'): ('Raymond Holt', 'Brooklyn Nine-Nine', "Exacting standards, unshakeable composure, and quietly indispensable. You do everything right without needing credit. Your steadiness makes everyone around you better."),
        ('C', None): ('Spock', 'Star Trek', "Logic-first, always. You trust data over gut and precision over speed. Others may not always understand your methods, but they rarely argue with your results."),
    }
    key = (primary_disc, secondary_disc)
    if key in characters:
        return characters[key]
    return characters.get((primary_disc, None), ('A True Original', 'Across Many Stories', 'Your profile is uniquely balanced — you adapt naturally to what each situation demands.'))


def build_full_report(disc, motiv, primary_disc, secondary_disc, primary_motiv):
    profiles = {
        'D': {
            'label': 'Decisive', 'tagline': 'You drive toward results. Fast.',
            'strengths': ['Takes initiative and acts without needing consensus', 'Performs well under pressure and tight deadlines', 'Cuts through ambiguity to get things moving', 'Holds high standards for self and others', 'Comfortable making unpopular decisions when necessary'],
            'blind_spots': ["Can come across as blunt or dismissive of others' input", 'May move too fast and miss important details', 'Tendency to steamroll rather than collaborate', 'Can underestimate the emotional impact of direct communication', 'May struggle to slow down when the team needs more time'],
            'energizers': ['Clear goals with measurable outcomes', 'Authority to make decisions without excessive approval', 'Competitive environments where winning matters', 'Autonomy to execute without micromanagement', 'Solving problems that require quick decisive action'],
            'drainers': ['Slow decision-making processes or committee thinking', 'Repetitive routine work with no challenge', 'Being second-guessed after a decision is made', 'Long-winded meetings without clear outcomes', 'Working with people who avoid accountability'],
            'comm_style': "Be direct and brief. Lead with the bottom line — what you need and by when. Skip the backstory unless asked. Use bullet points in writing. They respect candor and will lose interest in anything that feels like a preamble.",
            'conflict_style': "Moves toward conflict rather than away from it. Addresses issues head-on, sometimes before the other person is ready. Best approached with facts, not feelings. Don't expect them to tiptoe — and don't tiptoe around them.",
            'main_question': 'WHAT needs to happen and WHEN?',
        },
        'I': {
            'label': 'Interactive', 'tagline': 'You energize every room you walk into.',
            'strengths': ['Builds rapport and trust quickly with new people', 'Communicates with enthusiasm that gets others on board', 'Creates a positive team culture naturally', 'Thinks creatively and brings fresh ideas to problems', 'Inspires others to believe in the mission'],
            'blind_spots': ['May over-promise and under-deliver on details', 'Can lose focus mid-task when something more interesting appears', 'Sensitive to criticism, even when constructive', 'May rely too heavily on charm in situations that need data', 'Can dominate conversations without realizing it'],
            'energizers': ['Collaborative work with people you genuinely like', 'Recognition and positive feedback for contributions', 'Creative projects with room to put your mark on things', 'Variety — different tasks, different people, different challenges', 'High-energy environments where things are always moving'],
            'drainers': ['Isolated work with no human interaction', 'Rigid environments with no flexibility or creativity', "Being dismissed or ignored in group settings", 'Detailed, repetitive administrative work', "Environments where relationships don't matter"],
            'comm_style': "Start warm — ask about them before jumping to business. Be expressive and enthusiastic. They respond to energy. Keep written communication friendly, not clinical. Give them room to talk and share ideas; don't rush to the point.",
            'conflict_style': "Avoids conflict initially by turning on the charm. When conflict does arise, they want to talk it through emotionally. Acknowledge how they feel first before addressing the issue. Never dismiss or minimize their perspective — they'll shut down.",
            'main_question': 'WHO is involved and how will they feel about it?',
        },
        'S': {
            'label': 'Stabilizing', 'tagline': 'You are the steady force everyone leans on.',
            'strengths': ['Deeply loyal and consistent — shows up every time', 'Excellent listener who makes others feel heard', 'Keeps the team grounded during high-pressure situations', 'Builds deep trust through reliability over time', 'Mediates conflict and keeps relationships intact'],
            'blind_spots': ['Avoids conflict to the point of letting issues fester', 'May say yes to too much to keep the peace', 'Resistant to change, even when change is needed', 'Can be hard to read — emotions stay internal', 'May not advocate strongly enough for their own needs'],
            'energizers': ["Clear expectations and a stable, predictable environment", 'Working with a team that trusts and values each other', "Knowing the 'why' behind what they're being asked to do", 'Meaningful work that helps real people', 'Recognition that acknowledges their reliability, not just results'],
            'drainers': ['Sudden changes without explanation or context', 'Environments with constant conflict or instability', 'Being pushed to make fast decisions without time to process', 'Feeling like their contributions go unnoticed', 'Unclear roles or shifting expectations'],
            'comm_style': "Take time to connect before getting to business. Ask their opinion and wait for it — don't rush them to answer. Warm, sincere written communication. Always explain the 'why' behind requests. Follow up with them personally after difficult conversations.",
            'conflict_style': "Avoids conflict at almost any cost. When conflict is unavoidable, go slow, be warm, and lead with the relationship. Make it clear you value them before addressing the issue. Don't expect an immediate emotional reaction — they process privately.",
            'main_question': 'WHY are we doing this and how does it affect the team?',
        },
        'C': {
            'label': 'Cautious', 'tagline': 'You get it right when everyone else gets it close.',
            'strengths': ['Produces work of consistently high quality', 'Anticipates problems before they happen', 'Builds systems and processes that prevent errors', 'Asks the questions others are afraid to ask', 'Holds the standard when everyone else wants to cut corners'],
            'blind_spots': ['Can get paralyzed by the need for more information', 'May come across as overly critical or impossible to please', 'Reluctant to share opinions without rock-solid evidence', 'Can struggle to move fast when the situation demands it', 'May isolate during stress instead of asking for help'],
            'energizers': ['Problems with clear right answers that reward thoroughness', 'High-quality standards that actually matter', 'Time to research and think before acting', 'Working with competent people who respect precision', 'Environments where accuracy is valued over speed'],
            'drainers': ["Being asked to 'just guess' or skip proper process", 'Working with people who are careless or sloppy', 'Environments with no standards or accountability', 'Constant interruptions that break focus', 'Being criticized publicly rather than privately'],
            'comm_style': "Be factual, detailed, and organized. They respect people who have done their homework. Don't rush them. Written follow-ups are welcome. Ask specific questions. Avoid vague requests — define exactly what you need and by when.",
            'conflict_style': "Withdraws and analyzes during conflict. May appear cold or detached but is actually processing deeply. Give them time and space. Present facts, not emotions. They will respond better to a written outline of the issue than a face-to-face confrontation.",
            'main_question': 'HOW will this be done and is it being done correctly?',
        },
    }
    motiv_profiles = {
        'Achievement': "You are driven by results, progress, and the satisfaction of reaching a goal. You measure your own success — and you hold yourself to a high standard. Recognizing your wins matters to you, but only when they're actually earned.",
        'Affiliation': "You are motivated by relationships, belonging, and the bonds built through shared work. The strength of your team and the quality of your connections mean as much to you as the outcome itself.",
        'Security': "Stability and reliability fuel you. You perform at your best when expectations are clear, the environment is predictable, and the ground under you feels solid. Uncertainty is your biggest enemy.",
        'Autonomy': "You need ownership. When you're given the freedom to decide how to do something, you bring your best. Micromanagement shuts you down faster than anything else.",
        'Service': "Impact is your currency. Knowing that your work genuinely helps someone — a client, a resident, a teammate — is what makes the effort worth it. You're not in it for yourself.",
        'Growth': "You are never finished becoming. Learning new skills, taking on harder challenges, and pushing past what you've already mastered is what keeps you engaged. Stagnation is the enemy.",
    }
    return {
        'disc_profile': profiles[primary_disc],
        'motiv_description': motiv_profiles[primary_motiv],
        'primary_disc': primary_disc,
        'secondary_disc': secondary_disc,
        'primary_motiv': primary_motiv,
    }


# ── ROUTES ──────────────────────────────────────────────────────────────────────

@app.route('/')
def root():
    if session.get('authenticated'):
        return redirect(url_for('index'))
    return redirect(hub_login_url(url_for('index', _external=True)))


@app.route('/login', methods=['GET', 'POST'])
def login():
    return redirect(hub_login_url(url_for('index', _external=True)))


@app.route('/profile')
def index():
    auth_resp = _ensure_auth()
    if auth_resp:
        return auth_resp
    return render_template('index.html')


@app.route('/take-test')
def take_test():
    auth_resp = _ensure_auth()
    if auth_resp:
        return auth_resp
    seed = session.get('test_seed') or random.randint(1, 999999)
    session['test_seed'] = seed
    questions = get_questions_shuffled(seed)
    # Split into pages of ~11 questions
    pages = [questions[i:i+11] for i in range(0, len(questions), 11)]
    return render_template('test.html', pages=pages, total=len(questions))


@app.route('/submit', methods=['POST'])
def submit():
    if not session.get('authenticated'):
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.get_json()
    name = data.get('name', '').strip()
    answers = data.get('answers', {})
    if not name or len(answers) < 44:
        return jsonify({'error': 'Incomplete submission'}), 400

    seed = session.get('test_seed', 42)
    questions = get_questions_shuffled(seed)

    disc, motiv = score_responses(answers, questions)
    primary_disc, secondary_disc, primary_motiv = determine_profile(disc, motiv)
    character, show, character_desc = get_character_match(primary_disc, secondary_disc, primary_motiv)
    report = build_full_report(disc, motiv, primary_disc, secondary_disc, primary_motiv)

    today = datetime.now().date()
    year = today.year
    full_results = {
        'disc': disc, 'motiv': motiv,
        'primary_disc': primary_disc, 'secondary_disc': secondary_disc,
        'primary_motiv': primary_motiv,
        'character': character, 'show': show, 'character_desc': character_desc,
        'report': report,
    }

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
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            ''', (name, today, year, disc['D'], disc['I'], disc['S'], disc['C'],
                  motiv['Achievement'], motiv['Affiliation'], motiv['Security'],
                  motiv['Autonomy'], motiv['Service'], motiv['Growth'],
                  primary_disc, secondary_disc, primary_motiv,
                  character, show, json.dumps(full_results)))
            session['last_result_id'] = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"DB save error: {e}")

    session['last_result'] = full_results
    session.pop('test_seed', None)
    return jsonify({'redirect': url_for('results')})


@app.route('/results')
def results():
    auth_resp = _ensure_auth()
    if auth_resp:
        return auth_resp
    result = session.get('last_result')
    if not result:
        return redirect(url_for('index'))
    return render_template('results.html', result=result)


@app.route('/history')
def history():
    auth_resp = _ensure_auth()
    if auth_resp:
        return auth_resp
    name = request.args.get('name', '').strip()
    if not _is_admin():
        name = session.get('display_name', '').strip()
    rows = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            if name:
                cur.execute('SELECT * FROM profile_results WHERE LOWER(name) = LOWER(%s) ORDER BY taken_date DESC', (name,))
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
    auth_resp = _ensure_auth()
    if auth_resp:
        return auth_resp
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
    if not _is_admin() and row['name'].lower() != session.get('display_name', '').lower():
        return redirect(url_for('history'))
    result = row['full_results']
    if isinstance(result, str):
        result = json.loads(result)
    return render_template('results.html', result=result, from_history=True,
                           taken_date=row['taken_date'], taken_name=row['name'])


@app.route('/admin')
def admin():
    auth_resp = _ensure_auth()
    if auth_resp:
        return auth_resp
    if not _is_admin():
        return redirect(url_for('index'))
    year_filter = request.args.get('year', str(datetime.now().year))
    rows, years = [], []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT DISTINCT taken_year FROM profile_results ORDER BY taken_year DESC')
            years = [r['taken_year'] for r in cur.fetchall()]
            cur.execute('''SELECT id, name, taken_date, disc_d, disc_i, disc_s, disc_c,
                          primary_disc, secondary_disc, primary_motiv, character_match, character_show
                   FROM profile_results WHERE taken_year = %s ORDER BY name, taken_date DESC''', (year_filter,))
            rows = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin DB error: {e}")
    return render_template('admin.html', rows=rows, years=years, selected_year=int(year_filter))



@app.route('/admin/export-csv')
def export_csv():
    auth_resp = _ensure_auth()
    if auth_resp:
        return auth_resp
    if not _is_admin():
        return redirect(url_for('index'))
    import csv
    import io as _io
    from flask import Response
    rows = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''SELECT id, name, taken_date, taken_year,
                disc_d, disc_i, disc_s, disc_c,
                motiv_achievement, motiv_affiliation, motiv_security,
                motiv_autonomy, motiv_service, motiv_growth,
                primary_disc, secondary_disc, primary_motiv,
                character_match, character_show, created_at
                FROM profile_results ORDER BY taken_date DESC''')
            rows = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"CSV export error: {e}")

    output = _io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Name', 'Date Taken', 'Year',
        'D Score', 'I Score', 'S Score', 'C Score',
        'Achievement', 'Affiliation', 'Security', 'Autonomy', 'Service', 'Growth',
        'Primary DISC', 'Secondary DISC', 'Primary Motivator',
        'Character Match', 'Character Show', 'Created At'
    ])
    for r in rows:
        writer.writerow([
            r['id'], r['name'], r['taken_date'], r['taken_year'],
            r['disc_d'], r['disc_i'], r['disc_s'], r['disc_c'],
            r['motiv_achievement'], r['motiv_affiliation'], r['motiv_security'],
            r['motiv_autonomy'], r['motiv_service'], r['motiv_growth'],
            r['primary_disc'], r['secondary_disc'], r['primary_motiv'],
            r['character_match'], r['character_show'], r['created_at']
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=pps_profiles_{datetime.now().strftime("%Y%m%d")}.csv'}
    )

@app.route('/logout')
def logout():
    session.clear()
    nxt = request.args.get('next', '').strip()
    if nxt.startswith('http://') or nxt.startswith('https://'):
        return redirect(nxt)
    return redirect(hub_login_url())


if __name__ == '__main__':
    app.run(debug=True)
